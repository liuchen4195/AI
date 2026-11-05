from openai import AsyncOpenAI
import os
import dotenv
from model import TOOLS
import json
from tools import tools_map
import copy
from tracks import Tracks
from trace import TraceRecorder, sanitize_error
import uuid
import asyncio
from dataclasses import dataclass


# 配置环境
dotenv.load_dotenv()
api_key = os.getenv("OPENAI_API_KEY", "").strip()
model_name = os.getenv("OPENAI_MODEL", "").strip()
base_url = os.getenv("BASE_URL", "").strip()

if not api_key:
    raise RuntimeError("请先设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先设置 OPENAI_MODEL")
if not base_url:
    raise RuntimeError("请先设置 BASE_URL")


# 单轮对话允许的最大模型请求次数
MAX_MODEL_ROUNDS = 10


@dataclass
class RunResult:
    """一次完整 Tool Calling 闭环的结构化结果。"""
    ok: bool
    answer: str | None
    trace: dict


#裁剪消息历史
def trim(messages, max_rounds):
    if not messages:
        return []
    if max_rounds < 0:
        raise ValueError("max_rounds 不能小于0")

    system = messages[0]
    dialogue = messages[1:]

    if max_rounds == 0:
        return [system]
    keep = max_rounds * 2
    return [system.copy(), *dialogue[-keep:]]


class UserService:
    def __init__(self, persist_tracks=True):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        # Web 端使用自己的 data/web_sessions 存储，关闭 CLI 的 tracks 追加
        self.persist_tracks = persist_tracks
        self.tracks = Tracks("data/tracks.json")

    #模型请求
    async def send(self,messages):
        response = await self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=TOOLS,
            #让模型自主决定是否调工具
            tool_choice="auto",
            #允许模型同轮提出多个工具调用
            parallel_tool_calls=True
        )
        return response

    #异步的 Tool Calling 受控循环
    async def run(self, messages, user_messages, recorder=None):
        """异步方法，跑一次完整工具闭环，返回 RunResult。"""
        recorder = recorder or TraceRecorder(user_messages)
        trace = recorder.trace

        messages = trim(copy.deepcopy(messages), max_rounds=5)
        #记录起始位置
        start_index = len(messages)
        messages.append({
            "role": "user",
            "content": user_messages
        })

        #最多循环 MAX_MODEL_ROUNDS 轮
        for i in range(MAX_MODEL_ROUNDS):
            print(f"第 {i + 1} 次调用模型")
            model_started = recorder.begin_model_request()
            try:
                # 调用模型
                result = await self.send(messages)
            except Exception as e:
                print("模型调用失败：", e)
                recorder.finish_model_request(model_started, usage=None, ok=False)
                recorder.finish(
                    "failed",
                    "model_request_failed",
                    {
                        "type": "model_request_failed",
                        "message": "模型服务调用失败，请稍后重试",
                        "stage": "model_request",
                        "round": i + 1,
                    },
                )
                return RunResult(False, None, trace)

            # 记录模型请求耗时与 usage（没有 usage 时保持“未返回”）
            recorder.finish_model_request(
                model_started,
                usage=getattr(result, "usage", None),
                ok=True,
            )

            message = result.choices[0].message
            tool_calls = message.tool_calls

            if tool_calls:
                # 1. 先拿到 assistant 消息的字典
                assistant_dict = message.model_dump(exclude_none=True)
                # 2.强制确保 content 字段存在且为字符串
                if "content" not in assistant_dict or assistant_dict.get("content") is None:
                    assistant_dict["content"] = ""
                messages.append(assistant_dict)

                # 3.记录本轮工具调用，再并发执行
                round_entry = recorder.begin_tool_round(tool_calls)
                results = await asyncio.gather(
                    *[
                        self._execute_tool(tool, call_entry, recorder)
                        for tool, call_entry in zip(
                            tool_calls, round_entry["calls"]
                        )
                    ],
                    return_exceptions=True,
                )
                recorder.finish_tool_round(round_entry)

                # 4. 按 tool_call_id 追加 tool 消息
                for tool, res in zip(tool_calls, results):
                    if isinstance(res, Exception):
                        # _execute_tool 已捕获工具异常；这里只兜底未预期异常
                        res = {"ok": False, "error": "tool_failed"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool.id,
                        "content": json.dumps(res, ensure_ascii=False),
                    })
            else:
                answer = message.content or ""
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                })

                if not answer.strip():
                    recorder.finish(
                        "failed",
                        "empty_answer",
                        {
                            "type": "empty_answer",
                            "message": "模型未返回最终回答",
                            "stage": "final_answer",
                            "round": i + 1,
                        },
                    )
                    return RunResult(False, None, trace)

                if self.persist_tracks:
                    self.tracks.save({
                        "id": uuid.uuid4().hex[:12],
                        "tracks": messages[start_index:],
                    })

                recorder.finish(
                    "partial" if recorder.has_tool_errors() else "success",
                    "completed",
                )
                return RunResult(True, answer, trace)

        recorder.finish(
            "failed",
            "max_model_rounds",
            {
                "type": "max_model_rounds",
                "message": f"模型在 {MAX_MODEL_ROUNDS} 轮内未给出最终回答",
                "stage": "model_loop",
                "round": MAX_MODEL_ROUNDS,
            },
        )
        return RunResult(False, None, trace)

    async def _execute_tool(self, tool, call_entry, recorder):
        """执行单个工具并写入轨迹；工具异常转成模型可读的失败结果。"""
        recorder.start_tool_call(call_entry)

        try:
            res = await self.run_tools(tool)
        except Exception as e:
            error_type, error_message = sanitize_error(e)
            res = {"ok": False, "error": "tool_failed"}
            recorder.finish_tool_call(
                call_entry,
                res,
                error_type,
                error_message,
            )
            return res

        if isinstance(res, dict) and res.get("status") == "error":
            recorder.finish_tool_call(
                call_entry,
                res,
                "tool_reported_error",
                res.get("message") or "工具返回错误",
            )
        else:
            recorder.finish_tool_call(call_entry, res)
        return res

    # 异步工具执行方法
    async def run_tools(self, tool):
        print("tool id：", tool.id)
        print("tool 名称：", tool.function.name)
        print("tool 参数：", tool.function.arguments)

        # 判断模型想调用的工具是否存在
        curr_tool = tools_map.get(tool.function.name)
        if not curr_tool:
            raise RuntimeError("访问的工具不存在！")

        # 解析模型生成的参数
        try:
            args = json.loads(tool.function.arguments)
        except json.decoder.JSONDecodeError as e:
            raise RuntimeError("参数解析失败:", e)

        # 校验参数
        try:
            args = curr_tool["args"].model_validate(args)
        except Exception as e:
            raise RuntimeError("参数校验未通过!")

        # 调用工具，获取工具结果
        try:
            tool_res = await curr_tool["function"](**args.model_dump())
            print(tool_res)
            return tool_res
        except Exception as e:
            raise RuntimeError("工具执行失败:", e)

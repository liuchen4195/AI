from openai import AsyncOpenAI
import os
import dotenv
from model import TOOLS
import json
from tools import tools_map
import copy
from tracks import Tracks
import uuid
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone


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


# 工具名称 -> 用途说明，轨迹展示时直接复用工具合同里的描述
TOOL_DESCRIPTIONS = {
    item["function"]["name"]: item["function"].get("description", "")
    for item in TOOLS
}

# 单轮对话允许的最大模型请求次数
MAX_MODEL_ROUNDS = 10


@dataclass
class RunResult:
    """一次完整 Tool Calling 闭环的结构化结果。"""
    ok: bool
    answer: str | None
    trace: dict


def _utc_now_iso():
    """返回毫秒级 UTC 时间，例如 2026-11-05T09:30:12.123Z。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _parse_arguments(raw_arguments):
    """把模型返回的参数 JSON 字符串转成对象；解析失败时保留原始字符串。"""
    try:
        return json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        return raw_arguments


def _derive_execution_mode(rounds):
    """只根据真实工具轮次推导调用方式，不根据工具名称猜测。"""
    if not rounds:
        return "none"
    if len(rounds) == 1:
        return "parallel" if rounds[0]["call_count"] > 1 else "serial"
    if any(item["call_count"] > 1 for item in rounds):
        return "mixed"
    return "serial"


class BasicTraceRecorder:
    """
    步骤 1 的基础轨迹记录器。

    目前只记录轮次、调用、参数、结果、状态和整体耗时；
    工具级计时、Token 统计、错误脱敏和完整测试由步骤 2 的 trace.py 补全。
    """

    def __init__(self, question):
        self._started_perf = time.perf_counter()
        self.trace = {
            "trace_id": uuid.uuid4().hex[:12],
            "question": question,
            "status": "running",
            "stop_reason": None,
            "started_at": _utc_now_iso(),
            "finished_at": None,
            "duration_ms": None,
            "model_requests": 0,
            "tool_calls": 0,
            "tool_rounds": 0,
            "execution_mode": "none",
            "tokens": {
                "input": None,
                "output": None,
                "total": None,
                "complete": False,
                "reported_requests": 0,
                "total_requests": 0,
            },
            "rounds": [],
            "error": None,
        }

    def begin_model_request(self):
        self.trace["model_requests"] += 1
        self.trace["tokens"]["total_requests"] += 1

    def begin_tool_round(self, tool_calls):
        self.trace["tool_rounds"] += 1
        call_count = len(tool_calls)
        mode = "parallel" if call_count > 1 else "single"
        round_entry = {
            "round": len(self.trace["rounds"]) + 1,
            "mode": mode,
            "call_count": call_count,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "calls": [],
        }
        for tool in tool_calls:
            round_entry["calls"].append({
                "call_id": tool.id,
                "name": tool.function.name,
                "description": TOOL_DESCRIPTIONS.get(tool.function.name, "未知工具"),
                "arguments": _parse_arguments(tool.function.arguments),
                "result": None,
                "status": "running",
                "error_type": None,
                "error_message": None,
                "execution": "parallel" if call_count > 1 else "serial",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
            })
        self.trace["tool_calls"] += call_count
        self.trace["rounds"].append(round_entry)
        return round_entry

    def finish_tool_call(self, call_entry, result, error_type=None, error_message=None):
        call_entry["result"] = result
        if error_type:
            call_entry["status"] = "error"
            call_entry["error_type"] = error_type
            call_entry["error_message"] = error_message
        else:
            call_entry["status"] = "success"

    def finish(self, status, stop_reason, error=None):
        self.trace["status"] = status
        self.trace["stop_reason"] = stop_reason
        self.trace["error"] = error
        self.trace["finished_at"] = _utc_now_iso()
        self.trace["duration_ms"] = int(
            round((time.perf_counter() - self._started_perf) * 1000)
        )
        self.trace["execution_mode"] = _derive_execution_mode(self.trace["rounds"])
        return self.trace


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
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        # 轨迹对象
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
        recorder = recorder or BasicTraceRecorder(user_messages)
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
            recorder.begin_model_request()
            try:
                # 调用模型
                result = await self.send(messages)
            except Exception as e:
                print("模型调用失败：", e)
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
                    *[self.run_tools(tool) for tool in tool_calls],
                    return_exceptions=True,
                )

                # 4. 按 tool_call_id 追加 tool 消息
                for tool, call_entry, res in zip(
                    tool_calls, round_entry["calls"], results
                ):
                    if isinstance(res, Exception):
                        res = {"ok": False, "error": "tool_failed"}
                        recorder.finish_tool_call(
                            call_entry,
                            res,
                            "tool_failed",
                            "工具执行失败",
                        )
                    elif isinstance(res, dict) and res.get("status") == "error":
                        recorder.finish_tool_call(
                            call_entry,
                            res,
                            "tool_reported_error",
                            res.get("message") or "工具返回错误",
                        )
                    else:
                        recorder.finish_tool_call(call_entry, res)

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

                self.tracks.save({
                    "id": uuid.uuid4().hex[:12],
                    "tracks": messages[start_index:],
                })

                has_tool_error = any(
                    call["status"] == "error"
                    for item in trace["rounds"]
                    for call in item["calls"]
                )
                recorder.finish(
                    "partial" if has_tool_error else "success",
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

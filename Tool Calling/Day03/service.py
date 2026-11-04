from openai import OpenAI
import os
import dotenv
from model import TOOLS
import json
from tools import tools_map
import copy
from tracks import Tracks
import uuid
import asyncio


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
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        # 轨迹对象
        self.tracks = Tracks("data/tracks.json")

    #模型请求
    def send(self,messages):
        response = self.client.chat.completions.create(
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
    async def run(self, messages, user_messages):
        """异步方法，跑一次完整工具闭环"""
        messages = trim(copy.deepcopy(messages), max_rounds=5)
        #记录起始位置
        start_index = len(messages)
        messages.append({
            "role": "user",
            "content": user_messages
        })
        # print("截取之后的消息列表")
        # for message in messages:
        #     print(message)

        #最多循环 10 轮
        for i in range(10):
            print(f"第 {i + 1} 次调用模型")
            try:
                # 调用模型
                result = self.send(messages)
            except Exception as e:
                print("模型调用失败：", e)
                return None

            message = result.choices[0].message
            tool_calls = message.tool_calls

            if tool_calls:
                # 1. 先拿到 assistant 消息的字典
                assistant_dict = message.model_dump(exclude_none=True)
                # 2.强制确保 content 字段存在且为字符串
                if "content" not in assistant_dict or assistant_dict.get("content") is None:
                    assistant_dict["content"] = ""
                messages.append(assistant_dict)
                # 4. 后面才是并发执行工具、追加 tool 消息
                results = await asyncio.gather(
                    *[self.run_tools(tool) for tool in tool_calls],
                    return_exceptions=True,
                )
                for tool, res in zip(tool_calls, results):
                    if isinstance(res, Exception):
                        res = {"ok": False, "error": "tool_failed"}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool.id,
                        "content": json.dumps(res, ensure_ascii=False),
                    })
            else:
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                })
                self.tracks.save({
                    "id": uuid.uuid4().hex[:12],
                    "tracks": messages[start_index:],
                })
                return message.content

        raise RuntimeError("达到最大轮数，未得到最终回答")

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


















# -*- coding: utf-8 -*-
"""Day01 会议室只读助手主程序。

职责划分：
- query_room()          只读工具：查询固定的虚构会议室数据；
- ROOM_TOOL             工具合同：告诉模型工具名称、用途和参数 Schema；
- execute_tool_call()   安全执行：白名单 -> JSON -> 字段 -> 业务校验 -> 执行；
- run_room_assistant()  受控循环：模型提出调用 -> 执行 -> 回传 -> 最终回答；
- create_client()       读取 Week 8 的 OPENAI_API_KEY / OPENAI_MODEL 配置。

运行方式（在仓库根目录）：
    python "6.Tool Calling与阶段项目/examples/day01_room_assistant.py"
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

# --------------------------------------------------------------------------
# 1. 只读工具：固定的虚构会议室数据
# --------------------------------------------------------------------------
ROOMS = {
    "晨曦会议室": {"location": "A座1层 A101", "capacity": 6},
    "星河会议室": {"location": "B座2层 B201", "capacity": 12},
    "远航会议室": {"location": "B座3层 B301", "capacity": 20},
}


def query_room(room_name: str) -> dict:
    """按完整名称查询会议室；只读，不创建预约。"""
    room = ROOMS.get(room_name)
    if room is None:
        # 业务失败：工具正常执行但没有对应数据
        return {"ok": False, "error": "room_not_found"}
    return {"ok": True, "room_name": room_name, **room}


# --------------------------------------------------------------------------
# 2. 工具合同：提供给模型的使用说明
# --------------------------------------------------------------------------
ROOM_TOOL = {
    "type": "function",
    "function": {
        "name": "query_room",
        "description": "查询固定会议室的位置和容量；只读，不创建预约。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "enum": ["晨曦会议室", "星河会议室", "远航会议室"],
                    "description": "需要查询的完整会议室名称",
                }
            },
            "required": ["room_name"],
            "additionalProperties": False,
        },
    },
}

# --------------------------------------------------------------------------
# 3. 安全执行：白名单 + 参数校验 + 异常兜底
# --------------------------------------------------------------------------
TOOL_REGISTRY = {
    "query_room": query_room,
}

# 会议室名称的业务上限
MAX_ROOM_NAME_LENGTH = 20


def execute_tool_call(tool_call) -> dict:
    """把模型的调用请求当作不可信输入，校验全部通过后才执行工具。"""
    # 1. 白名单：只执行注册表里登记过的工具
    tool_name = tool_call.function.name
    tool_function = TOOL_REGISTRY.get(tool_name)
    if tool_function is None:
        return {"ok": False, "error": "tool_not_allowed"}

    # 2. 参数字符串 -> Python 数据；禁止 eval()
    try:
        arguments = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "invalid_json"}

    # 3. 字段校验：必须恰好只有 room_name 一个字段
    if not isinstance(arguments, dict) or set(arguments) != {"room_name"}:
        return {"ok": False, "error": "invalid_arguments"}

    # 4. 类型与业务校验：非空字符串且不超过长度上限
    room_name = arguments["room_name"]
    if not isinstance(room_name, str):
        return {"ok": False, "error": "invalid_room_name"}

    room_name = room_name.strip()
    if not room_name or len(room_name) > MAX_ROOM_NAME_LENGTH:
        return {"ok": False, "error": "invalid_room_name"}

    # 5. 全部校验通过后才执行真正的 Python 函数
    try:
        return tool_function(room_name=room_name)
    except Exception:
        return {"ok": False, "error": "tool_failed"}


# --------------------------------------------------------------------------
# 4. 客户端配置：复用 Week 8 的环境变量
# --------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "涉及公司会议室的位置、容量和设备信息时必须使用工具查询；"
    "一般概念可以直接回答。"
)

# 最多处理 4 轮模型响应，防止模型反复调用工具
MAX_ROUNDS = 4


def create_client() -> tuple:
    """读取并检查 Week 8 配置，创建一次客户端供多轮复用。"""
    load_dotenv()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model_name = (os.getenv("OPENAI_MODEL") or "").strip()
    base_url = (os.getenv("BASE_URL") or "").strip() or None

    if not api_key:
        raise RuntimeError("请先配置 OPENAI_API_KEY")
    if not model_name:
        raise RuntimeError("请先配置 OPENAI_MODEL")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0, max_retries=2)
    return client, model_name


# --------------------------------------------------------------------------
# 5. 受控循环：完整 Tool Calling 闭环
# --------------------------------------------------------------------------
def run_room_assistant(client, model_name: str, user_text: str) -> str:
    """接收用户问题，完成“模型提出调用 -> 程序执行 -> 结果回传 -> 最终回答”。"""
    loop_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for round_number in range(1, MAX_ROUNDS + 1):
        print(f"第 {round_number} 轮：请求模型")

        # 每一轮都把当前完整消息和可用工具发送给模型
        response = client.chat.completions.create(
            model=model_name,
            messages=loop_messages,
            tools=[ROOM_TOOL],
            tool_choice="auto",
            parallel_tool_calls=False,
        )
        assistant_message = response.choices[0].message

        # 先把包含 tool_calls 的 assistant 消息追加进列表
        loop_messages.append(assistant_message.model_dump(exclude_none=True))

        tool_calls = assistant_message.tool_calls or []
        if not tool_calls:
            # 没有工具调用时，正常情况应该已经得到最终文字回答
            if not assistant_message.content:
                raise RuntimeError("模型没有返回工具调用或最终回答")
            return assistant_message.content

        # 本课关闭并行调用，每轮只处理第一条工具请求
        tool_call = tool_calls[0]
        print("模型请求调用：", tool_call.function.name)

        # 白名单、参数校验和安全执行
        result = execute_tool_call(tool_call)

        # 用原始调用编号回传结果，供下一轮模型继续判断
        loop_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
        print("工具执行完成，结果已加入消息列表")
    else:
        # 循环没有通过 return 正常结束，说明达到轮数上限
        raise RuntimeError("处理轮数超过上限，已停止")


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def main() -> None:
    client, model_name = create_client()
    user_text = input("请输入问题：")
    answer = run_room_assistant(client, model_name, user_text)
    print("最终回答：", answer)


if __name__ == "__main__":
    main()

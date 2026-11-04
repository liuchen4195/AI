import os
from dotenv import load_dotenv
from openai import OpenAI
from tools import LIST_ROOMS_TOOL, QUERY_ROOM_TOOL, list_rooms, query_room


# 两个职责不同的工具放进同一个列表，一次提供给模型
TOOL_SCHEMAS = [QUERY_ROOM_TOOL, LIST_ROOMS_TOOL]

SYSTEM_PROMPT = "你是会议室助手。需要实时会议室数据时选择合适的工具。"

# 三类问题：已知名称查询、按人数筛选、普通概念
QUESTIONS = [
    "星河会议室在哪里？",
    "有哪些至少容纳 10 人的会议室？",
    "什么是会议室？",
]


load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
model_name = os.getenv("OPENAI_MODEL")
base_url = os.getenv("BASE_URL")

if not api_key:
    raise ValueError("API key is required")
if not model_name:
    raise ValueError("Model name is required")
if not base_url:
    raise ValueError("Base url is required")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=30.0,
    max_retries=2
)


def observe_tool_choice(client, model_name: str, question: str):
    """发一次请求，只读取模型的选择结果，不执行任何工具。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    # 请求模型根据用户问题决定直接回答还是选择工具
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice="auto",
        # 本章先限制每轮最多提出一个调用，便于观察工具选择
        parallel_tool_calls=False,
    )

    # 取出模型本轮生成的消息
    assistant_message = response.choices[0].message
    # 没有工具调用时用空列表代替 None，便于统一判断
    tool_calls = assistant_message.tool_calls or []

    if not tool_calls:
        # 模型认为不需要外部数据，直接展示自然语言回答
        print("模型直接回答：", assistant_message.content)
        return None

    # 本章关闭了并行调用，因此只读取第一个工具请求
    tool_call = tool_calls[0]
    print("工具名称：", tool_call.function.name)
    print("参数 JSON：", tool_call.function.arguments)
    print("调用编号：", tool_call.id)
    return tool_call

def main() -> None:
    # 第 1 步：先脱离模型确认工具函数本身正确（不花模型调用次数）
    print("list_rooms(10) 自检：", list_rooms(10))
    print("query_room 自检：", query_room("星河会议室"))

    for question in QUESTIONS:
        print(f"\n=== 问题：{question} ===")
        observe_tool_choice(client, model_name, question)


if __name__ == "__main__":
    main()












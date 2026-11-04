import json

import dotenv
import os
from openai import OpenAI
from tools import tools_map, QUERY_ROOM_TOOL, ROOMS_LEN, WEATHER

dotenv.load_dotenv()

# 获取环境变量
MODEL_NAME = os.getenv("MODEL_NAME")
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")

# 创建 OPENAI 客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# 统一执行工具
def run_tool(tool):
    print("tool_calls信息：")
    print("tool id:", tool.id)
    print("tool 参数:", tool.function.arguments)
    print("tool 名称:", tool.function.name)

    # 查找工具是否存在
    tool_func = tools_map.get(tool.function.name)
    if not tool_func:
        return { "status": "error", "message": f"{tool.function.name} 此工具不存在" }

    # 解析模型返回的参数
    try:
        args = json.loads(tool.function.arguments)
    except:
        return { "status": "error", "message": f"{tool.function.arguments} 此参数解析失败" }

    # 调用工具
    try:
        res = tool_func(**args)
        return res
    except Exception as e:
        raise { "status": "error", "message": f"{tool.function.name} 执行失败, {str(e)}" }

# 系统提示词
system_message = {
    "role": "system",
    "content": "你是一个会议室查询助手，用户询问会议室相关信息需要调用工具查询，查询公司会议室信息时不能编造事实。其他问题可以直接回答，返回最终结果时需要用通知我本次是否调用了工具"
}

# 用户消息列表
messages = [system_message]
user = input("请输入你的问题（exit退出）：")
messages.append({ "role": "user", "content": user })

try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        # 把工具合同传给模型
        tools=[QUERY_ROOM_TOOL, ROOMS_LEN, WEATHER],
        # 允许模型自主选择调用工具
        tool_choice="auto",
        # 是否允许模型并行调用工具
        parallel_tool_calls=False
    )
    print("模型返回结果：", response)
    tool_calls = response.choices[0].message.tool_calls
    if tool_calls:
        tool = response.choices[0].message.tool_calls[0]
        # 执行 tool，获取结果
        tool_res = run_tool(tool)
        # 追加模型请求调用工具的消息
        messages.append(response.choices[0].message.model_dump())
        # 追加 tool 调用的结果
        messages.append({ "role": "tool", "tool_call_id": tool.id, "content": json.dumps(tool_res)})
        print("tool调用结果:", tool_res)

        # 把工具结果传给模型继续调用
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages
        )
        print("AI 最终结果:", response.choices[0].message.content)
    else:
        print("AI 最终结果:", response.choices[0].message.content)
except Exception as e:
    print("模型调用失败：", e)
















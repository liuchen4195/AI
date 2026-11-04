import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from tools import query_room, QUERY_ROOM_TOOL

# 读取并检查配置
load_dotenv()
api_key = (os.getenv("OPENAI_API_KEY") or '').strip()
model_name = (os.getenv("OPENAI_MODEL") or '').strip()
base_url = (os.getenv("BASE_URL") or '').strip()

# 配置缺失时立即停止，避免发送无效请求
if not api_key:
    raise RuntimeError("请先在 .env 中设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先在 .env 中设置 OPENAI_MODEL")
if not base_url:
    raise RuntimeError('请先在 .env 中设置 BASE_URL')

# 创建客户端
client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=30.0,
    max_retries=2
)

# 获取本次问题，并拒绝空输入（星河会议室在哪里？）
user_text= input('你: ').strip()
if not user_text:
    raise ValueError("输入不能为空")

# 准备对话消息，并说明哪些问题必须查询工具
messages = [
    {
        "role": "system",
        "content": "涉及公司会议室的位置、容量和设备信息时必须使用工具查询；一般概念可以直接回答。"
    },
    {
        "role": "user",
        "content": user_text
    }
]

#在普通对话请求的基础上增加三个与工具调用有关的参数
response = client.chat.completions.create(
    model=model_name,
    messages=messages,
    #告诉模型当前可以选择哪些工具
    tools=[QUERY_ROOM_TOOL],
    #允许模型自行决定调用工具或直接回答
    tool_choice="auto",
    #一次只处理一个工具调用
    parallel_tool_calls=False,
)
assistant_message = response.choices[0].message

#判断是否有工具调用
if assistant_message.tool_calls:
    tool_call = assistant_message.tool_calls[0]
    #读取工具名称、参数和调用编号
    print("调用编号：", tool_call.id)
    print("工具名称：", tool_call.function.name)
    print("参数字符串：", tool_call.function.arguments)   #JSON 字符串
else:
    print("模型没有提出工具调用,直接回答", assistant_message.content)

#先确认工具名称，再解析参数
tool_call = assistant_message.tool_calls[0]
if tool_call.function.name != "query_room":
    raise ValueError("模型请求了未知工具")

#JSON 字符串 → Python 字典/对象
arguments = json.loads(tool_call.function.arguments)
result = query_room(arguments["room_name"])
print("工具结果：", result)

# 先把 SDK 消息 → Python 字典，完整保留 tool_calls 和调用编号
messages.append(
    assistant_message.model_dump(exclude_none=True)
)

# 再追加与调用编号匹配的工具结果
messages.append(
    {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result, ensure_ascii=False),
    }
)

final_response = client.chat.completions.create(
    model=model_name,
    messages=messages,
)

final_answer = final_response.choices[0].message.content
print("最终回答：", final_answer)

print(response)




















































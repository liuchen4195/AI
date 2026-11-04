import os

from dotenv import load_dotenv
from ollama import chat


# 将 .env 中的配置加载为环境变量
load_dotenv()

# 读取并清理本地模型名
model_name = (os.getenv("OLLAMA_MODEL") or "").strip()
if not model_name:
    raise RuntimeError("请先在 .env 中设置 OLLAMA_MODEL")

# 获取本次问题，并拒绝空输入
user_text = input("你：").strip()
if not user_text:
    raise ValueError("输入不能为空")

# 组装发送给本地模型的 system 和 user 消息
messages = [
    # system 消息：规定回答方式和边界
    {
        "role": "system",
        "content": "回答要简洁；信息不足时明确说明。",
    },
    # user 消息：保存当前输入的问题
    {
        "role": "user",
        "content": user_text,
    },
]

# 发送一次非流式请求，并保存完整响应
# 用 Ollama Python SDK 的 chat 函数发送对话请求
response = chat(
    model=model_name,
    messages=messages,
    # stream=False 表示一次性返回完整回复（不是流式）
    stream=False,
)

# 提取本地模型生成的文本
print(f"助手：{response.message.content}")

# print(f'助手: {response["message"]["content"]}')























































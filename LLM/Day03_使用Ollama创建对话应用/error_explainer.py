import os

from dotenv import load_dotenv
from ollama import chat


# 这是应用自己的字符限制，用于避免误粘贴过长日志
MAX_ERROR_LENGTH = 1500

# 加载并检查本地模型配置
load_dotenv()
model_name = (os.getenv("OLLAMA_MODEL") or "").strip()
if not model_name:
    raise RuntimeError("请先在 .env 中设置 OLLAMA_MODEL")

# 只输入虚构、公开或已经脱敏的报错信息
print("提示：请先删除日志中的姓名、账号、密钥和公司内部地址。")
error_text = input("请粘贴报错信息：").strip()
if not error_text:
    raise ValueError("报错信息不能为空")
if len(error_text) > MAX_ERROR_LENGTH:
    raise ValueError(f"报错信息不能超过 {MAX_ERROR_LENGTH} 个字符")

# system 消息规定解释方式，user 消息保存本次报错文本
messages = [
    {
        "role": "system",
        "content": (
            "你是编程报错解释助手。请使用通俗中文回答，依次给出："
            "报错含义、两个优先检查项、一个修改示例。"
            "信息不足时说明还需要什么信息，不要假装已经定位根因。"
        ),
    },
    {
        "role": "user",
        "content": error_text,
    },
]

# 向本机 Ollama 服务发送一次非流式请求
response = chat(
    model=model_name,
    messages=messages,
    stream=False,
)

# 提取并显示模型生成的解释
print("\n【报错解释】")
print(response.message.content)



















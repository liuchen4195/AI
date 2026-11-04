"""多功能文本助手"""

import os

from dotenv import load_dotenv
from openai import OpenAI


# 每个功能包含一个显示名称和一条 System Prompt
TASKS = {
    "1": {
        "name": "通俗解释",
        "prompt": "请用通俗、简洁的语言解释输入内容，必要时给出一个例子；不确定时明确说明。",
    },
    "2": {
        "name": "内容摘要",
        "prompt": "请提取输入内容的核心信息，整理为不超过三点的摘要；不要补充原文没有的事实。",
    },
    "3": {
        "name": "文字润色",
        "prompt": "请在不改变原意的前提下润色输入内容，使表达清晰自然；不要添加新的事实。",
    },
    "4": {
        "name": "提取关键词",
        "prompt": "请提取输入内容的关键词，用一行文字返回，关键词之间用顿号分隔，不超过五个；不要解释，不要补充原文没有的信息。",
    },
}

# 这是本案例设置的输入上限，不是服务商的模型上限
MAX_INPUT_LENGTH = 2000

# 读取本地配置
load_dotenv()
api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()

if not api_key:
    raise RuntimeError("请先在 .env 中设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先在 .env 中设置 OPENAI_MODEL")

# 显示功能菜单
print("请选择文本处理功能：")
for number, task_info in TASKS.items():
    print(f"{number}. {task_info['name']}")

# 检查功能编号，非法编号不会发送 API 请求
choice = input("请输入功能编号：").strip()
if choice not in TASKS:
    raise ValueError("功能编号无效，请输入 1、2、3 或 4")

# 获取需要处理的内容
print("提示：输入会发送到云端，请勿填写个人隐私或公司机密。")
user_text = input("请输入要处理的内容：").strip()
if not user_text:
    raise ValueError("输入内容不能为空")
if len(user_text) > MAX_INPUT_LENGTH:
    raise ValueError(f"输入内容不能超过 {MAX_INPUT_LENGTH} 个字符")

# 根据选择取得功能配置，并组装本次消息
selected_task = TASKS[choice]
messages = [
    {
        "role": "system",
        "content": selected_task["prompt"],
    },
    {
        "role": "user",
        "content": user_text,
    },
]

# 每次运行只发送一次请求
client = OpenAI(
    api_key=api_key,
    base_url=os.getenv("BASE_URL")
)

response = client.chat.completions.create(
    model=model_name,
    messages=messages,
)

# 显示功能名称和模型返回的文本
print(f"\n【{selected_task['name']}结果】")
print(response.choices[0].message.content)
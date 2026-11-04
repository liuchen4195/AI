import os

from dotenv import load_dotenv
from openai import OpenAI


# dotenv 将 .env 中的配置加载为环境变量
load_dotenv()

# getenv 从环境文件读取并清理 API Key 与模型名
api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()
base_url = (os.getenv("BASE_URL") or "").strip()

# 配置缺失时立即停止，避免发送无效请求
if not api_key:
    raise RuntimeError("请先在 .env 中设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先在 .env 中设置 OPENAI_MODEL")
if not base_url:
    raise RuntimeError('请先在 .env 中设置 BASE_URL')

# 获取本次问题，并拒绝空输入
user_text = input("你：").strip()
if not user_text:
    raise ValueError("输入不能为空")

# 组装发送给模型的 system 和 user 消息
messages = [
    # system 消息：规定模型本次对话的回答方式和边界
    {
        "role": "system",
        "content": "回答要简洁；信息不足时明确说明。",
    },
    # user 消息：保存当前输入的具体问题
    {
        "role": "user",
        "content": user_text
     },
]

# 创建 OpenAI 客户端，用于与云端 API 通信
client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

# 指定模型和消息，发送一次请求，并保存完整响应（调对话补全接口）
response = client.chat.completions.create(model=model_name, messages=messages)

# 从响应对象中提取模型生成的文本
# print(f'助手: {response}')   #最直观展示生成了什么
print(f"助手：{response.choices[0].message.content}")

# # 流式请求：逐块返回，边生成边打印,最后返回Token用量
# try:
#     stream = client.chat.completions.create(
#         model=model_name,
#         messages=messages,
#         stream=True,
#         stream_options={'include_usage': True}
#     )
# except Exception as error:
#     print(f'调用失败: {type(error).__name__}')
#     raise SystemExit(1)
#
# # 逐块读取并打印，形成打字机效果,收集完整文本并显示Token用量
# full_text = []
# usage = None
# print('助手: ', end='', flush=True)
#
# for chunk in stream:
#     # 最后一个 chunk 可能没有 choices（只带 usage）
#         if getattr(chunk, 'usage', None):
#             usage = chunk.usage
#         if not chunk.choices:
#             continue
#         delta = chunk.choices[0].delta.content
#         if delta:
#             print(delta, end='', flush=True)
#             full_text.append(delta)
# print()
#
# # 显示 Token 用量
# if usage is not None:
#     print(
#         "Token 用量：",
#         f"输入={usage.prompt_tokens}，",
#         f"输出={usage.completion_tokens}，",
#         f"总计={usage.total_tokens}",
#     )
# else:
#     print("本次响应没有返回 Token 用量")































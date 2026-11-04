import os

from dotenv import load_dotenv
from openai import OpenAI


# 读取 Day02 已经准备好的 .env 配置
load_dotenv()

# 从环境变量中读取 API Key 和模型名，并去掉首尾空白
api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()
base_url = (os.getenv("BASE_URL") or "").strip()

# 缺少必要配置时立即停止，避免发送无效请求
if not api_key:
    raise RuntimeError("请先设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先设置 OPENAI_MODEL")

# 创建客户端，后续通过它调用模型服务
client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=30.0,  # 为网络调用设置超时配置
    max_retries=2,  # 初始请求失败后，最多自动重试 2 次
)

# 发起一次流式请求，返回值不再是完整响应，而是可以逐个读取的数据流
stream = client.chat.completions.create(
    model=model_name,
    # messages 保存本次请求发送给模型的消息
    #没有 system，属于简单单轮请求
    messages=[
        {
            "role": "user",
            "content": "请用三点说明如何排查耳机没有声音。",
        }
    ],
    #开启流式：逐块返回，边生成边可读
    stream=True,
    # 让最后一个数据块携带本次 Token 用量
    stream_options={"include_usage": True},
)

# 分别保存文本片段、结束原因和 Token 用量
text_parts = []
finish_reason = None
usage = None

# 每次循环读取一个流式数据块
for chunk in stream:
    # 如果当前数据块携带 Token 用量，就保存下来
    if chunk.usage is not None:
        usage = chunk.usage

    # 开启 include_usage 后，最后一个用量数据块可能没有 choices
    if not chunk.choices:
        continue

    # 文本对话只读取第一个候选结果
    choice = chunk.choices[0]

    # delta.content 是当前数据块新增的文本，不是完整回答
    delta_text = choice.delta.content or ""
    if delta_text:
        # 立即显示新增文本，并将它加入文本片段列表
        print(delta_text, end="", flush=True)
        text_parts.append(delta_text)

    # 最后一个包含 choices 的数据块会给出停止原因
    if choice.finish_reason is not None:
        finish_reason = choice.finish_reason

# 流式显示结束后换行，并把所有文本片段拼成完整回答
print()
full_text = "".join(text_parts).strip()

# 只有正常结束且文本非空，才能把本轮视为成功
if finish_reason != "stop" or not full_text:
    raise RuntimeError("流式响应未正常完成，不能写入成功历史")

print(f"完整回复长度：{len(full_text)} 个字符")

# 服务商返回 usage 时，显示本次请求的真实 Token 用量
if usage is not None:
    print(
        "Token 用量：",
        f"输入={usage.prompt_tokens}，",
        f"输出={usage.completion_tokens}，",
        f"总计={usage.total_tokens}",
    )

































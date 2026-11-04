import os

from dotenv import load_dotenv
from openai import OpenAI

# 输出上限1000字
MAX_INPUT_CHARS = 1000

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

# 保存本轮已经收到的文本和最终结束原因
text_parts = []
finish_reason = None

try:
    # 请求创建和流式读取都可能发生异常，因此都放在 try 中， stream迭代器
    stream = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": "请介绍流式输出。"
            },
        ],
        # 逐块返回
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        delta_text = chunk.choices[0].delta.content or ""
        if delta_text:
            #flush=True：立即刷新，打字机效果
            print(delta_text, end="", flush=True)
            text_parts.append(delta_text)

        if choice.finish_reason is not None:
            finish_reason = choice.finish_reason

except Exception as error:
    # 请求失败或流式读取中断时，不保存本轮回答
    print(f"\n调用失败：{type(error).__name__}")
    print("本轮回答不写入消息历史")

#try成功才执行的块
else:
    #换行 + 拼接完整文本
    print()
    full_text = "".join(text_parts).strip()

    if finish_reason != "stop":
        # length、缺少结束原因等情况都不能视为完整回答
        print(f"回复未完整生成，结束原因：{finish_reason}")
        print("本轮回答不写入消息历史")
    elif not full_text:
        print("模型没有返回有效文本，本轮回答不写入消息历史")
    else:
        # 只有正常结束且文本非空，才允许保存回答
        print(f"完整回复长度：{len(full_text)} 个字符")
        print("本轮回答可以写入消息历史")































import os

from dotenv import load_dotenv
from openai import OpenAI


# 这是应用设置的输入上限，不是模型的上下文上限
MAX_INPUT_CHARS = 1000

# 从 .env 加载并检查云端服务配置
load_dotenv()

api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()
base_url = (os.getenv("BASE_URL") or "").strip()
if not api_key:
    raise RuntimeError("请先设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先设置 OPENAI_MODEL")

# client:客户端, 创建一次客户端，后续多轮请求重复使用
client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

# # system 规则由应用固定，不接受普通输入修改
# messages = [
#     {
#         "role": "system",
#         "content": "你是需求澄清助手。信息不足时先追问，不自行编造条件。",
#     }
# ]

SYSTEM_MESSAGE = {
    "role": "system",
    "content": "你是需求澄清助手。信息不足时先追问，不自行编造条件。",
}

# system 只有一个可信来源
messages = [SYSTEM_MESSAGE.copy()]

def trim_history(message, max_rounds):
    """ 返回固定 system 和最近 max_rounds 组完整问答。"""
    if max_rounds < 0:
        raise ValueError('max_rounds 不能小于0')
    # 历史必须从 system 开始
    if not messages or messages[0].get('role') != 'system':
        raise ValueError('消息历史必须从 system 开始')

    dialogue = messages[1:]

    #一轮必须恰好包含 user 和 assistant 两条消息
    if len(dialogue) % 2 != 0:
        raise ValueError('消息历史中存在不完整问答')

    for idex in range(0, len(dialogue), 2):
        user_message = dialogue[idex]
        assistant_message = dialogue[idex + 1]
        if (
            user_message.get('role') != 'user'
            or assistant_message.get('role') != 'assistant'
        ):
            raise ValueError('消息历史必须按 user、assistant 顺序保存')

    # 每轮有两条消息，因此保留数量等于轮数乘 2
    keep_count = max_rounds * 2
    recent_dialogue = dialogue[-keep_count:] if keep_count else []

    # 返回时始终使用应用中固定的 system
    return [SYSTEM_MESSAGE.copy(), *recent_dialogue]

while True:
    user_text = input("你：").strip()

    # exit 和 quit 只结束本地程序，不调用 API
    if user_text.lower() in {"exit", "quit"}:
        print("会话结束")
        break
    if not user_text:
        print("请输入内容")
        continue
    if len(user_text) > MAX_INPUT_CHARS:
        print(f"输入不能超过 {MAX_INPUT_CHARS} 个字符")
        continue

    # 先临时加入本轮输入，构造包含历史的请求
    messages.append(
        {
            "role": "user",
            "content": user_text
        }
    )

    try:
        # 调 API，提取回复文本。
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
        # 从 API 响应里安全地取出回复文本, 本课只提取基础文本输出，并拒绝保存空回答
        assistant_text = (response.choices[0].message.content or "").strip()
    except Exception as error:
        # 调用失败时撤销本轮输入，避免形成没有回答的残缺历史
        messages.pop()
        print(f"调用失败，本轮未保存：{type(error).__name__}")
        continue

    if not assistant_text:
        # 空回答不能和当前 user 组成有效问答对
        messages.pop()
        print("模型没有返回有效文本，本轮未保存")
        continue

    # 调用成功后再保存 assistant，形成完整的一问一答
    messages.append({"role": "assistant", "content": assistant_text})
    print(f"助手：{assistant_text}")

    #读取同一个 `response` 的 `usage`
    #usage 是 API 响应里的 Token 用量统计，告诉你这次请求消耗了多少 Token。
    usage = response.usage
    if usage is not None:
        print(
            "Token 用量: ",
            f"输入={usage.prompt_tokens}，",
            f"输出={usage.completion_tokens}，",
            f"总计={usage.total_tokens}",
        )
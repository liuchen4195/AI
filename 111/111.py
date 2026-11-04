# import os
# from dotenv import load_dotenv
# from openai import OpenAI
#
# load_dotenv()
#
# api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
# model_name = (os.getenv('OPENAI_MODEL') or '').strip()
# base_url = (os.getenv('BASE_URL') or '').strip()
#
# if not api_key:
#     raise ValueError("API key is required")
# if not model_name:
#     raise ValueError("Model name is required")
# if not base_url:
#     raise ValueError("Base url is required")
#
# user_text = input('你: ').strip()
# if not user_text:
#     raise ValueError("User text is required")
#
# messages = [
#     {
#         "role": "system",
#         'content': '你是一个助手，说话简短易懂'
#     },
#     {
#         "role": "user",
#         'content': user_text
#     }
# ]
#
# client = OpenAI(
#     api_key=api_key,
#     base_url=base_url
# )
#
# # response = client.chat.completions.create(model=model_name, messages=messages)
# #
# # print(f'助手: {response.choices[0].message.content}')
#
#
# #流式输出
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
# full_text = []
# usage = None
#
# print('助手: ', end= '', flush=True)
# for chunk in stream:
#     if getattr(chunk, 'usage', None):
#         usage = chunk.usage
#     if not chunk.choices:
#         continue
#     delta = chunk.choices[0].delta.content
#     if delta:
#         print(delta, end='', flush=True)
#         full_text.append(delta)
# print()
#
# if usage:
#     print(
#         "Token 用量：",
#         f"输入={usage.prompt_tokens}，",
#         f"输出={usage.completion_tokens}，",
#         f"总计={usage.total_tokens}",
#     )
# else:
#     print('本次响应没有返回Token用量')




import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path


PROJECT_DIR = Path(__file__).parent
SESSION_PATH = PROJECT_DIR / 'session.json'

# 这是应用设置的输入上限，不是模型的上下文上限
MAX_INPUT_CHARS = 1000
MAX_REQUEST_ROUNDS = 5
MAX_SAVED_ROUNDS = 20

# 从 .env 加载并检查云端服务配置
load_dotenv()

api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()
base_url = (os.getenv("BASE_URL") or "").strip()
if not api_key:
    raise RuntimeError("请先设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先设置 OPENAI_MODEL")
if not base_url:
    raise RuntimeError('请先设置 BASE_URL')

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "你是活动通知需求澄清助手。"
        "需要确认活动主题、时间、地点、参与对象和通知语气。"
        "信息不足时每次追问最关键的一到两项，不自行编造。"
        "信息完整后输出通知标题和简短正文。"
    ),
}

def trim_history(messages, max_rounds):
    """保留固定 system 和最近若干组完整问答。"""
    if max_rounds < 0:
        raise ValueError('最大轮数不能小于0')
    if (
        not messages
        or not isinstance(messages[0], dict)
        or messages[0].get('role') != 'system'
    ):
        raise ValueError('消息历史必须从 system 开始')
    dialogue = messages[1:]
    if len(dialogue) % 2 != 0:
        raise ValueError('消息历史中存在不完整问答')

    for i in range(0, len(dialogue), 2):
        user_message = dialogue[i]
        assistant_message = dialogue[i + 1]
        if (
            not isinstance(user_message, dict)
            or user_message.get('role') != 'user'
            or not isinstance(assistant_message, dict)
            or assistant_message.get('role') != 'assistant'
        ):
            raise ValueError('消息历史必须按user、assistant顺序保存')

    keep_count = max_rounds * 2
    recent = dialogue[-keep_count:] if keep_count else []
    return [SYSTEM_MESSAGE.copy(), *recent]

def load_messages(path, max_saved_rounds):
    """加载合法问答对；不存在或空文件表示新会话。"""
    if not path.exists():
        return [SYSTEM_MESSAGE.copy()]

    text = path.read_text(encoding='utf-8')
    if not text.strip():
        return [SYSTEM_MESSAGE.copy()]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'会话文件不是合法 JSON：{error}') from error

    if not isinstance(data, list) or len(data) % 2 != 0:
        raise ValueError("会话文件必须是完整问答组成的列表")
    if len(data) > max_saved_rounds * 2:
        raise ValueError(f"会话文件不能超过 {max_saved_rounds} 轮")

    validated_dialogue = []
    for i ,item in enumerate(data):
        expected_role = 'user' if i % 2 == 0 else 'assistant'
        if not isinstance(item, dict):
            raise ValueError(f"第 {i + 1} 条消息格式不正确")
        content = item.get("content")
        if (
            item.get("role") != expected_role
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError(f"第 {i + 1} 条消息的角色或内容不正确")

        validated_dialogue.append(
            {
                "role": expected_role,
                "content": content,
            }
        )

    return [SYSTEM_MESSAGE.copy(), *validated_dialogue]

def save_messages(path, messages, max_saved_rounds):
    """限制本地保存轮数，并直接写入 JSON 文件。"""
    limited_messages = trim_history(messages, max_saved_rounds)
    dialogue = limited_messages[1:]
    path.write_text(
        json.dumps(dialogue, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

def print_usage(response):
    """显示服务端返回的本次 Token 用量。"""
    #usage = response.usage
    usage = getattr(response, 'usage', None)
    if usage is None:
        print('本次响应没有返回Token值')
        return
    print(
        "Token 用量：",
        f'输入={usage.prompt_tokens},'
        f'输出={usage.completion_tokens},'
        f'总计={usage.total_tokens}'
    )

def main():
    try:
        messages = load_messages(SESSION_PATH, max_saved_rounds=MAX_SAVED_ROUNDS)
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(f'会话加载失败，请检查 {SESSION_PATH.name}：{error}') from error
    print(f"已加载{(len(messages) - 1) // 2} 轮历史")
    while True:
        user_text = input('你: ').strip()
        if not user_text:
            print('请输入内容')
            continue
        if user_text.lower() in {'exit', 'quit'}:
            print('会话结束')
            break
        if len(user_text) > MAX_INPUT_CHARS:
            print(f'输入不能超过{MAX_INPUT_CHARS}个字符')
            continue

        request_messages = trim_history(messages, MAX_REQUEST_ROUNDS)
        request_messages.append(
            {
                'role': 'user',
                'content': user_text
            }
        )

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=request_messages
            )
        except Exception as error:
            print(f'调用失败, 本轮未保存: {type(error).__name__}')
            continue

        assistant_text = (response.choices[0].message.content or "").strip()
        if not assistant_text:
            print('模型没有返回可保存文本,本轮未保存')
            continue

        candidate_messages = [
            *messages,
            {
                'role': 'user',
                'content': user_text
            },
            {
                'role': 'assistant',
                'content': assistant_text
            }
        ]

        try:
            save_messages(
                SESSION_PATH,
                candidate_messages,
                MAX_SAVED_ROUNDS
            )
        except OSError as error:
            print(f'会话保存失败,本轮未进入历史: {error}')
            continue

        messages = trim_history(candidate_messages, MAX_SAVED_ROUNDS)
        print(f"助手：{assistant_text}")
        print_usage(response)
       
if __name__ == '__main__':
    main()

# def load_messages(path):
#     """从 JSON 文件加载历史；不存在或空文件返回只含 system 的列表。"""
#     if not path.exists():
#         return [SYSTEM_MESSAGE.copy()]
#
#     text = path.read_text(encoding="utf-8")
#     if not text.strip():
#         return [SYSTEM_MESSAGE.copy()]
#
#     data = json.loads(text)
#
#     dialogue = []
#     for item in data:
#         dialogue.append({
#             "role": item.get("role"),
#             "content": item.get("content"),
#         })
#
#     return [SYSTEM_MESSAGE.copy(), *dialogue]

# while True:
#     user_text = input('你: ').strip()
#     if not user_text:
#         print('请输入内容')
#         continue
#     if user_text.lower() in {'exit', 'quit'}:
#         print('会话结束')
#         break
#     if len(user_text) > MAX_INPUT_CHARS:
#         print(f'输入不能超过 {MAX_INPUT_CHARS} 个字符')
#         continue
#
#     messages.append(
#         {
#             'role': 'user',
#             'content': user_text
#         }
#     )
#
#     try:
#         response = client.chat.completions.create(
#             model=model_name,
#             messages=messages
#         )
#         assistant_text = (response.choices[0].message.content or "").strip()
#     except Exception as error:
#         messages.pop()
#         print(f'调用失败, 本轮未保存: {type(error).__name__}')
#         continue
#
#     if not assistant_text:
#         messages.pop()
#         print('模型没有返回有效文本,本轮未保存')
#         continue
#
#     messages.append(
#         {
#             'role': 'assistant',
#             'content': assistant_text
#         }
#     )
#     print(f'助手: {assistant_text}')














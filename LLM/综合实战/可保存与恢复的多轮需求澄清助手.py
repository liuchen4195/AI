"""
程序需要具备以下功能：

1. 从 `.env` 读取模型配置；
2. 启动时安全加载 `session.json`；
3. 支持连续对话以及 `exit`、`quit` 退出；
4. 每次请求最多携带最近 5 轮；
5. 本地最多保存最近 20 轮；
6. 使用候选历史，只有保存成功后才更新正式内存历史；
7. 每轮显示服务端返回的 Token 用量；
8. 拒绝空输入和超过本应用字符上限的输入。
"""

import os
import json
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI

# 会话文件固定保存在当前程序旁边，不受运行命令所在目录影响
PROJECT_DIR = Path(__file__).resolve().parent
SESSION_PATH = PROJECT_DIR / "session.json"

MAX_REQUEST_ROUNDS = 5
MAX_SAVED_ROUNDS = 20
# 本应用的输入规则，不是模型上下文上限
MAX_INPUT_CHARS = 1000

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "你是全知全能的ai助手。"
        "需要了解网络上的热门话术和事件。"
        "信息不足时每次追问最关键的一到两项，不自行编造。"
        "信息完整后输出通知标题和简短正文。"
    ),
}

#trim_history:裁剪器,裁剪历史
def trim_history(messages, max_rounds):
    """保留固定 system 和最近若干组完整问答。"""
    if max_rounds < 0:
        raise ValueError('max_rounds 不能小于0')

    if (
        not messages
        or not isinstance(messages[0], dict)
        or messages[0].get('role') != "system"
    ):
        raise ValueError('消息历史必须从 system 开始')

    dialogue = messages[1:]
    if len(dialogue) %2 != 0:
        raise ValueError('消息历史中存在不完整问答')

    for index in range(0, len(dialogue), 2):
        user_message = dialogue[index]
        assistant_message = dialogue[index + 1]
        if (
            not isinstance(user_message, dict)
            or user_message.get('role') != "user"
            or not isinstance(assistant_message, dict)
            or assistant_message.get('role') != "assistant"
        ):
            raise ValueError('消息历史必须按 user、assistant 顺序保存')

    keep_count = max_rounds * 2
    recent = dialogue[-keep_count:] if keep_count else []
    # .copy() 防止外部修改 SYSTEM_MESSAGE
    return [SYSTEM_MESSAGE.copy(), *recent]

#加载 + 校验 + 规范化
def load_messages(path, max_saved_rounds):
    if not path.exists():
        return [SYSTEM_MESSAGE.copy()]

    text = path.read_text(encoding='utf-8')
    if not text.strip():
        return [SYSTEM_MESSAGE.copy()]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'会话文件不是合法 json: {error}') from error

    if not isinstance(data, list) or len(data) % 2 != 0:
        raise ValueError('会话文件必须是完整问答组成的列表')

    if len(data) > max_saved_rounds * 2:
        raise ValueError(f'会话文件不能超过 {max_saved_rounds} 轮')

    # 遍历每条，按位置推断**期望角色**：偶数索引 user，奇数 assistant。
    validated_dialogue = []
    for index, item in enumerate(data):
        excepted_role = 'user' if index % 2 == 0 else 'assistant'
        #每条必须是字典
        if not isinstance(item, dict):
            raise ValueError(f'第{index + 1} 条消息格式不正确')
        # 角色必须匹配期望；content 必须是非空字符串。
        content = item.get('content')
        if (
            item.get('role') != excepted_role
            or not isinstance(content, dict)
            or not content.strip()
        ):
            raise ValueError(f'第 {index + 1} 条消息的角色或内容不正确')

        validated_dialogue.append(
            {
                'role': excepted_role,
                'content': content,
            }
        )
    # 返回：代码里的 system + 校验后的问答
    return [SYSTEM_MESSAGE.copy(), *validated_dialogue]

# 保存
def save_messages(path, messages, max_saved_rounds):
    """限制本地保存轮数，并直接写入 JSON 文件。"""
    # 裁到最近 max_saved_rounds 轮，去掉 system
    limited_messages = trim_history(messages, max_saved_rounds)
    dialogue = limited_messages[1:]

    #写文件，只写 user/assistant，不写 system
    path.write_text(
        json.dumps(dialogue, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

# 打印 Token 用量
def print_usage(response):
    usage = getattr(response, 'usage', None)
    if usage is None:
        print('本次响应没有返回Token用量')

    print(
        'Token 用量：',
        f'输入={usage.prompt_tokens}，',
        f'输出={usage.completion_tokens}，',
        f'总计={usage.total_tokens}',
    )


def main():
    load_dotenv()
    api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
    model_name = (os.getenv('OPENAI_MODEL') or '').strip()
    base_url = (os.getenv('BASE_URL') or '').strip()

    if not api_key:
        raise RuntimeError('请先设置 OPENAI_API_KEY')
    if not model_name:
        raise RuntimeError('请先设置 OPENAI_MODEL')

    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    try:
        #加载历史
        messages = load_messages(SESSION_PATH, max_saved_rounds=MAX_SAVED_ROUNDS)
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(f'会话加载失败，请检查 {SESSION_PATH.name}：{error}') from error
    print(f'已加载{(len(messages) -1) // 2} 轮历史')

    while True:
        user_text = input('你: ').strip()
        if user_text.lower() in {'exit', 'quit'}:
            print('会话结束')
            break

        # 新增：本地命令 /status，不进入历史、不调 API
        if user_text.lower() == "/status":
            print(f"当前内存问答轮数：{(len(messages) - 1) // 2}")
            print(f"每次请求最多携带轮数：{MAX_REQUEST_ROUNDS}")
            print(f"本地最多保存轮数：{MAX_SAVED_ROUNDS}")
            continue

        if not user_text:
            print('请输入内容')
            continue

        if len(user_text) > MAX_INPUT_CHARS:
            print(f'输入不能超过 {MAX_INPUT_CHARS} 个字符')
            continue

        # 请求只携带最近 5 轮，再追加当前输入
        request_messages = trim_history(messages, MAX_REQUEST_ROUNDS)
        request_messages.append({'role': 'user', 'content': user_text})

        try:
            response = client.chat.completions.create(
                model=model_name,
                # 改的是临时列表 request_messages，不动 messages
                messages=request_messages,
            )
        except Exception as error:
            print(f'调用失败,本轮未保存: {type(error).__name__}')
            continue

        assistant_text = (response.choices[0].message.content or '').strip()
        if not assistant_text:
            print('模型没有返回可保存的文本，本轮未保存')
            continue

        # 先构造候选历史，不立即修改正式内存历史
        candidate_messages = [
            *messages,
            {'role': 'user', 'content': user_text},
            {'role': 'assistant', 'content': assistant_text},
        ]

        try:
            save_messages(
                SESSION_PATH,
                candidate_messages,
                MAX_SAVED_ROUNDS
            )
        except OSError as error:
            print(f'会话保存失败，本轮未进入历史：{error}')
            continue

        # 保存成功后再提交，并让内存与文件都只保留最近 20 轮
        messages = trim_history(candidate_messages, MAX_REQUEST_ROUNDS)
        # 打印回复和 Token 用量
        print(f'助手: {assistant_text}')
        print_usage(response)

if __name__ == '__main__':
    main()




























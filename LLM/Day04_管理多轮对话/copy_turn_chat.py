import os
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ==================== 配置 ====================
# 这是应用设置的输入上限，不是模型的上下文上限
MAX_INPUT_CHARS = 1000
MAX_REQUEST_ROUNDS = 5
MAX_SAVED_ROUNDS = 20

PROJECT_DIR = Path(__file__).resolve().parent
SESSION_PATH = PROJECT_DIR / "session.json"

# 从 .env 加载并检查云端服务配置
load_dotenv()
api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
model_name = (os.getenv("OPENAI_MODEL") or "").strip()
base_url = (os.getenv("BASE_URL") or "").strip()

if not api_key:
    raise RuntimeError("请先设置 OPENAI_API_KEY")
if not model_name:
    raise RuntimeError("请先设置 OPENAI_MODEL")

# 创建一次客户端，后续多轮请求重复使用
client = OpenAI(
    api_key=api_key,
    base_url=base_url
)


SYSTEM_MESSAGE = {
    "role": "system",
    "content": "你是需求澄清助手。信息不足时先追问，不自行编造条件。",
}

# ==================== 历史裁剪 ====================
def trim_history(messages, max_rounds):
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

# ==================== 保存 ====================
def save_messages(path, messages, max_saved_rounds):
    """只保存最近若干组 user/assistant，不把 system 写入文件。"""
    limited_messages = trim_history(messages, max_saved_rounds)
    dialogue = limited_messages[1:]

    # 把最近的完整问答直接写入会话文件
    path.write_text(
        json.dumps(dialogue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ==================== 加载 ====================
def load_messages(path, max_saved_rounds):
    """加载合法问答对；文件不存在或为空时创建新会话。"""
    if not path.exists():
        return [SYSTEM_MESSAGE.copy()]

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return [SYSTEM_MESSAGE.copy()]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"会话文件不是合法 JSON：{error}") from error

    if not isinstance(data, list) or len(data) % 2 != 0:
        raise ValueError("会话文件必须是完整问答组成的列表")
    if len(data) > max_saved_rounds * 2:
        raise ValueError(f"会话文件不能超过 {max_saved_rounds} 轮")

    validated_dialogue = []
    for index, item in enumerate(data):
        expected_role = "user" if index % 2 == 0 else "assistant"
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 条消息格式不正确")

        content = item.get("content")
        if (
            item.get("role") != expected_role
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError(f"第 {index + 1} 条消息的角色或内容不正确")

        # 只保留 role 和 content
        validated_dialogue.append(
            {
                "role": expected_role,
                "content": content,
            }
        )

    # system 永远来自应用代码，不接受文件中的 system
    return [SYSTEM_MESSAGE.copy(), *validated_dialogue]

# ==================== 离线测试（不调 API） ====================
def run_offline_tests():
    print("=== 测试 trim_history ===")
    sample_messages = [
        SYSTEM_MESSAGE.copy(),
        {"role": "user", "content": "问题 1"},
        {"role": "assistant", "content": "回答 1"},
        {"role": "user", "content": "问题 2"},
        {"role": "assistant", "content": "回答 2"},
        {"role": "user", "content": "问题 3"},
        {"role": "assistant", "content": "回答 3"},
    ]
    # 三轮裁成两轮，应保留问题 2、回答 2、问题 3、回答 3
    trimmed_messages = trim_history(sample_messages, max_rounds=2)
    print([message["role"] for message in trimmed_messages])
    print([message["content"] for message in trimmed_messages[1:]])

    # 保留零轮时，只剩固定的 system
    system_only = trim_history(sample_messages, max_rounds=0)
    print([message["role"] for message in system_only])

    print("\n=== 测试 save/load ===")
    test_path = PROJECT_DIR / "session_test.json"
    try:
        test_messages = [
            SYSTEM_MESSAGE.copy(),
            {"role": "user", "content": "测试问题"},
            {"role": "assistant", "content": "测试回答"},
        ]
        save_messages(test_path, test_messages, max_saved_rounds=2)
        loaded = load_messages(test_path, max_saved_rounds=2)
        print("角色:", [m["role"] for m in loaded])
        print("内容:", loaded[1]["content"])
    finally:
        test_path.unlink(missing_ok=True)

    print()

# ==================== 主程序 ====================
def main():
    run_offline_tests()

    try:
        messages = load_messages(SESSION_PATH, MAX_SAVED_ROUNDS)
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(f"会话加载失败，请检查 session.json：{error}") from error

    print(f"已加载 {(len(messages) - 1) // 2} 轮历史")
    print("输入 exit 或 quit 结束会话。\n")

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

        # 发送前裁剪已完成历史，当前输入加到临时列表
        request_messages = trim_history(messages, max_rounds=5)
        request_messages.append({"role": "user", "content": user_text})

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=request_messages,
            )
            assistant_text = (response.choices[0].message.content or "").strip()
        except Exception as error:
            print(f"调用失败，本轮未保存：{type(error).__name__}")
            continue

        if not assistant_text:
            print("模型没有返回有效文本，本轮未保存")
            continue

        # 成功才写入正式历史，一次加一问一答
        messages.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ])
        print(f"助手：{assistant_text}")

        # 保存最近 MAX_SAVED_ROUNDS 轮
        try:
            save_messages(SESSION_PATH, messages, MAX_SAVED_ROUNDS)
        except OSError as error:
            print(f"会话保存失败：{error}")

        usage = response.usage
        if usage is not None:
            print(
                f"Token 用量："
                f"输入 {usage.prompt_tokens}，"
                f"输出 {usage.completion_tokens}，"
                f"总计 {usage.total_tokens}"
            )


if __name__ == "__main__":
    main()



























































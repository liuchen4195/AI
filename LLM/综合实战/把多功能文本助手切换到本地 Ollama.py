"""把多功能文本助手切换到本地 Ollama"""

# import os
# from dotenv import load_dotenv
# from ollama import chat
#
# # 业务功能与 Day02 保持一致
# TASKS = {
#     "1": {
#         "name": "通俗解释",
#         "prompt": "请用通俗、简洁的语言解释输入内容，必要时给出一个例子；不确定时明确说明。",
#     },
#     "2": {
#         "name": "内容摘要",
#         "prompt": "请提取输入内容的核心信息，整理为不超过三点的摘要；不要补充原文没有的事实。",
#     },
#     "3": {
#         "name": "文字润色",
#         "prompt": "请在不改变原意的前提下润色输入内容，使表达清晰自然；不要添加新的事实。",
#     },
# }
#
# # 这是应用自身的输入上限，不是本地模型的上下文上限
# MAX_INPUT_LENGTH = 2000
#
# load_dotenv()
#
# model_name = (os.getenv("OLLAMA_MODEL") or "").strip()
# if not model_name:
#     raise RuntimeError("请先在 .env 中设置 OLLAMA_MODEL")
#
# # 显示功能菜单
# print("请选择文本处理功能：")
# for number, task_info in TASKS.items():
#     print(f"{number}. {task_info['name']}")
#
# # 检查功能编号
# choice = input("请输入功能编号：").strip()
# if choice not in TASKS:
#     raise ValueError("功能编号无效，请输入 1、2 或 3")
#
# # 只使用虚构或公开文本测试
# print("提示：不要输入个人隐私、账号信息或公司机密。")
# user_text = input("请输入要处理的内容：").strip()
# if not user_text:
#     raise ValueError("输入内容不能为空")
# if len(user_text) > MAX_INPUT_LENGTH:
#     raise ValueError(f"输入内容不能超过 {MAX_INPUT_LENGTH} 个字符")
#
# # 根据选择取得对应的 System Prompt
# selected_task = TASKS[choice]
# messages = [
#     {
#         "role": "system",
#         "content": selected_task["prompt"],
#     },
#     {
#         "role": "user",
#         "content": user_text,
#     },
# ]
#
# # 业务流程不变，只把调用后端换成本地 Ollama
# response = chat(
#     model=model_name,
#     messages=messages,
#     stream=False,
# )
#
# print(f"\n【{selected_task['name']}结果】")
# print(response.message.content)




import os
from dotenv import load_dotenv
from ollama import chat

# ==================== 配置 ====================
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
}

MAX_INPUT_LENGTH = 200

load_dotenv()
model_name = (os.getenv("OPENAI_MODEL") or '').strip()
if not model_name:
    raise RuntimeError('请先配置好 OPENAI_MODEL')

# ==================== 菜单与输入 ====================
def show_menu():
    """显示功能菜单"""
    print('请选择文本处理功能')
    for i, task in TASKS.items():
        print(f'{i}. {task["name"]}')

def choice_task():
    """读编号，校验后返回任务配置"""
    choice = input('请输入编号: ').strip()
    if choice not in TASKS:
        print('请重新输入，编号只能是1|2|3')
    return TASKS[choice]

def valid_user_text():
    """读用户输入，校验非空和长度。"""
    print("提示：不要输入个人隐私、账号信息或公司机密。")
    user_text = input("请输入要处理的内容：").strip()
    if not user_text:
        raise ValueError("输入内容不能为空")
    if len(user_text) > MAX_INPUT_LENGTH:
        raise ValueError(f"输入内容不能超过 {MAX_INPUT_LENGTH} 个字符")
    return user_text

# ==================== 消息组装 ====================
def build_messages(task, user_text):
    """根据任务和输入组装 system + user 消息。"""
    return [
        {
            'role': 'system',
            'content': task['prompt']
        },
        {
            'role': 'user',
            'content': user_text
        }
    ]

# ==================== 调用模型 ====================
def call_ollama(model_name, messages):
    """调用本地 Ollama，返回回复文本；失败返回 None。"""
    try:
        response = chat(
            model=model_name,
            messages=messages,
            stream=False
        )
    except Exception as error:
        print(f'调用失败: {type(error).__name__}: {error}')
        return None
    return (response.message.content or '').strip()

# ==================== 主程序 ====================
def main():
    show_menu()
    task = choice_task()
    user_text = valid_user_text()
    messages = build_messages(task, user_text)

    reply = call_ollama(model_name, messages)
    if reply is None:
        return
    print(f'\n 【{task["name"]}结果】')
    print(reply)

if __name__ == '__main__':
    main()





















































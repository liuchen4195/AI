import asyncio
from service import UserService
from history import History
import time
SYSTEM_PROMPT = """你是城市天气与空气质量助手。

成功标准：
- 用户提供城市名称时，先调用 get_city_pos 获取真实坐标和时区。
- 坐标确认后，根据需求调用天气或空气质量工具。
- 同一阶段中互不依赖的查询可以在同一轮提出。
- 最终回答只使用本次工具结果中的事实，并说明数据时间和单位。

边界：
- 不得凭记忆生成坐标、天气、PM2.5、PM10 或 AQI。
- 候选城市不明确时，请用户补充国家或地区，不要擅自选择。
- 最多处理 3 个城市，不访问用户提供的任意 URL。
- 工具失败时如实说明，并保留其他已经成功的独立结果。
- 不把天气或空气质量结果解释成医疗建议。

当已有证据足以回答时立即结束，不要重复调用已经完成的工具。
"""

async def main():
    service = UserService()
    history = History("data/history.json")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history.messages
    ]

    while True:
        user = input("你：").strip()
        if not user:
            continue
        elif user == "/history":
            if len(messages) <= 1:
                print("暂无历史记录")
            else:
                rounds = (len(messages) - 1) // 2
                print(f"共 {rounds} 轮对话：\n")
                for idx, msg in enumerate(messages[1:], start=1):
                    role = msg.get("role", "")
                    content = msg.get("content") or ""
                    # 截断过长内容，避免刷屏
                    if len(content) > 120:
                        content = content[:120] + "..."
                    label = "你" if role == "user" else "助手"
                    print(f"[{idx}] {label}：{content}")
                print()
            continue

        elif user == "/clear":
            # 保留 system，清空对话历史
            messages = [messages[0]]
            history.messages = []
            history.save([])
            print("历史已清空\n")
            continue

        elif user == "/help":
            print("""
1. /help 查看帮助
2. /history 查看消息历史
3. /clear 清除历史
4. /exit 退出
            """)
            continue

        start_time = time.perf_counter()
        result = await service.run(messages, user)
        print(f"本次对话耗时 {time.perf_counter() - start_time}s")

        if result is None:
            print("AI助手：本次调用失败，未保存历史")
            continue

        print(f"AI助手：{result}")
        messages.extend([
            {
                "role": "user",
                "content": user
            },
            {
                "role": "assistant",
                "content": result
            }
        ])
        history.save(messages[1:])

if __name__ == '__main__':
    asyncio.run(main())
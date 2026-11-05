import asyncio
from service import UserService
from history import History
from tools import load_meeting_rooms
from prompt import SYSTEM_PROMPT
import time

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

        elif user == "/rooms":
            rooms = load_meeting_rooms()
            if not rooms:
                print("暂无会议室数据\n")
            else:
                print(f"可查询的会议室（共 {len(rooms)} 间）：\n")
                for room in rooms:
                    equipment = "、".join(room.get("equipment", []))
                    print(f"· {room.get('name')}｜{room.get('floor', '')}｜可容纳 {room.get('capacity', '?')} 人")
                    print(f"  地址：{room.get('address', '')}")
                    print(f"  设备：{equipment}")
                print()
            continue

        elif user == "/help":
            print("""
1. /help 查看帮助
2. /history 查看消息历史
3. /clear 清除历史
4. /rooms 查看可查询的会议室
5. /exit 退出
            """)
            continue

        start_time = time.perf_counter()
        result = await service.run(messages, user)
        print(f"本次对话耗时 {time.perf_counter() - start_time}s")

        if not result.ok or result.answer is None:
            reason = result.trace.get("stop_reason") or "unknown"
            print(f"AI助手：本次调用失败（{reason}），未保存历史")
            continue

        print(f"AI助手：{result.answer}")
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
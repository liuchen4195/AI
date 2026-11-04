import json
from pathlib import Path

class History:
    def __init__(self, history_path):
        self.history_path = Path(history_path)
        # 创建父级目录
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.messages = self.load()

    def load(self):
        if not self.history_path.exists():
            return []
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        # 过滤掉 content 为 None 或缺失的 assistant 消息
        clean = []
        for msg in data:
            if msg.get("role") == "assistant" and not msg.get("content"):
                continue
            clean.append(msg)
        return clean

    def save(self, messages):
        self.history_path.write_text(
            json.dumps(messages, ensure_ascii=False, indent=4),
            encoding="utf-8"
        )






































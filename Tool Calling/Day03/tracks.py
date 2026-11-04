import json
from pathlib import Path


#Tracks 类是把调用轨迹（track）追加保存到 JSON 文件
class Tracks:
    def __init__(self, path):
        self.path = Path(path)
        #创建父级目录
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self):
        if not self.path.exists():
            return []
        try:
            text = self.path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    #保存
    def save(self, track):
        tracks = self.load()
        tracks.append(track)
        self.path.write_text(
            json.dumps(tracks, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )





















































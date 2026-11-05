import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 导入 service 时校验 OPENAI_API_KEY / OPENAI_MODEL / BASE_URL；
# 缺少任一配置会直接抛出明确的 RuntimeError，避免服务带病启动。
import service  # noqa: F401
from prompt import SYSTEM_PROMPT


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


class ConversationSession:
    """单用户、进程内会话；只保存 user/assistant 最终消息。"""

    def __init__(self):
        self.messages = self._initial_messages()
        self.lock = asyncio.Lock()

    @staticmethod
    def _initial_messages():
        return [{"role": "system", "content": SYSTEM_PROMPT}]

    def add_turn(self, question: str, answer: str):
        """记录一轮完成的对话，不保存 tool_calls 和 tool 消息。"""
        self.messages.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])

    def reset(self):
        """恢复为只含 system 的初始会话。"""
        self.messages = self._initial_messages()


app = FastAPI(title="天气查询助手")
session = ConversationSession()
app.state.session = session

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

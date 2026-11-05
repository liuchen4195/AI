import asyncio
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from prompt import SYSTEM_PROMPT
from service import UserService


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


class ChatRequest(BaseModel):
    """只接受 question，禁止客户端注入 system/历史消息。"""

    model_config = ConfigDict(extra="forbid")

    question: str


class ConversationSession:
    """单用户、进程内会话；只保存 user/assistant 最终消息。"""

    def __init__(self):
        self.messages = self._initial_messages()
        self.lock = asyncio.Lock()
        self.processing = False

    @staticmethod
    def _initial_messages():
        return [{"role": "system", "content": SYSTEM_PROMPT}]

    @property
    def busy(self):
        # processing 在第一次 await 前同步置位，避免两个请求同时通过检查
        return self.processing or self.lock.locked()

    def add_turn(self, question: str, answer: str):
        """记录一轮完成的对话，不保存 tool_calls 和 tool 消息。"""
        self.messages.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])

    def reset(self):
        """恢复为只含 system 的初始会话。"""
        self.messages = self._initial_messages()


def error_response(status_code: int, error_type: str, message: str):
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "type": error_type,
                "message": message,
            },
        },
    )


app = FastAPI(title="天气查询助手")
session = ConversationSession()
app.state.session = session
app.state.user_service = UserService()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    question = payload.question.strip()
    if not question:
        # 输入错误：不创建 Trace，不修改会话
        return error_response(400, "invalid_input", "请输入要查询的问题")

    if session.busy:
        return error_response(409, "busy", "正在处理中，请稍后重试")

    session.processing = True
    try:
        async with session.lock:
            result = await app.state.user_service.run(
                session.messages,
                question,
            )

        if result.ok and result.answer is not None:
            session.add_turn(question, result.answer)
            return {
                "ok": True,
                "answer": result.answer,
                "trace": result.trace,
            }

        # 业务失败也返回 200，但失败轮次不写入模型上下文
        return {
            "ok": False,
            "answer": None,
            "trace": result.trace,
        }
    except Exception:
        logger.exception("chat request failed")
        return error_response(500, "internal_error", "服务器内部错误")
    finally:
        session.processing = False


@app.post("/api/clear")
async def clear():
    if session.busy:
        return error_response(409, "busy", "正在处理中，请稍后重试")

    session.reset()
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

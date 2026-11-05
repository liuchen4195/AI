import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from service import UserService
from web_history import (
    SessionManager,
    WebHistoryStore,
    new_turn_id,
    utc_now_iso,
)


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

COOKIE_NAME = "weather_session_id"
COOKIE_MAX_AGE = 180 * 24 * 60 * 60


class ChatRequest(BaseModel):
    """只接受 question，禁止客户端注入 system/历史消息。"""

    model_config = ConfigDict(extra="forbid")

    question: str


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


def cookie_secure(request: Request):
    configured = os.getenv("COOKIE_SECURE", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "")
    return forwarded.split(",")[0].strip().lower() == "https"


app = FastAPI(title="天气查询助手")
history_root = os.getenv("WEB_HISTORY_DIR", "data/web_sessions").strip() or "data/web_sessions"
app.state.history_store = WebHistoryStore(history_root)
app.state.session_manager = SessionManager(app.state.history_store)
app.state.user_service = UserService(persist_tracks=False)


@app.middleware("http")
async def attach_session(request: Request, call_next):
    """为 /api/ 请求加载 Cookie 会话，并在需要时写回 Cookie。"""
    path = request.url.path
    should_bind = path.startswith("/api/") and path != "/api/health"

    if should_bind:
        try:
            request.state.session = app.state.session_manager.get_or_create(
                request.cookies.get(COOKIE_NAME)
            )
        except Exception:
            logger.exception("load session failed")
            return error_response(500, "session_error", "读取会话失败，请稍后重试")

    response = await call_next(request)

    session = getattr(request.state, "session", None)
    if session is not None and request.cookies.get(COOKIE_NAME) != session.session_id:
        response.set_cookie(
            key=COOKIE_NAME,
            value=session.session_id,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=cookie_secure(request),
            path="/",
        )

    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    question = payload.question.strip()
    if not question:
        # 输入错误：不创建 Trace，不修改会话
        return error_response(400, "invalid_input", "请输入要查询的问题")

    session = request.state.session
    if session.busy:
        return error_response(409, "busy", "正在处理中，请稍后重试")

    session.processing = True
    try:
        async with session.lock:
            result = await app.state.user_service.run(
                session.messages,
                question,
            )

        trace = result.trace or {}
        answer = result.answer if result.ok else None
        ok = bool(result.ok and answer is not None)
        status = trace.get("status") or ("success" if ok else "failed")

        turn = {
            "turn_id": new_turn_id(),
            "question": question,
            "answer": answer,
            "status": status,
            "created_at": trace.get("started_at") or utc_now_iso(),
            "finished_at": trace.get("finished_at"),
            "trace": trace,
        }
        saved = session.add_turn(turn)
        if not saved:
            logger.error("turn persistence failed: %s", turn["turn_id"])

        return {
            "ok": ok,
            "answer": answer,
            "trace": trace,
            "turn_id": turn["turn_id"],
            "history_saved": saved,
        }
    except Exception:
        logger.exception("chat request failed")
        return error_response(500, "internal_error", "服务器内部错误")
    finally:
        session.processing = False


@app.get("/api/history")
async def history(request: Request):
    session = request.state.session
    return {
        "ok": True,
        "session_id": session.session_id,
        "turns": session.history_summary(),
    }


@app.get("/api/history/{turn_id}")
async def history_turn(turn_id: str, request: Request):
    session = request.state.session
    turn = session.get_turn(turn_id)
    if turn is None:
        return error_response(404, "turn_not_found", "未找到该轮历史记录")

    return {"ok": True, "turn": turn}


@app.post("/api/clear")
async def clear(request: Request):
    session = request.state.session
    if session.busy:
        return error_response(409, "busy", "正在处理中，请稍后重试")

    try:
        session.reset()
    except Exception:
        logger.exception("clear history failed")
        return error_response(500, "history_clear_failed", "清空历史失败，请稍后重试")

    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# http://192.168.32.1:8000 公共端口，所有人都能连
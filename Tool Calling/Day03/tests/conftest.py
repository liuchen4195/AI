import os
import sys
from pathlib import Path

import pytest

# 保证从仓库根目录运行 pytest 时也能导入 Day03 下的模块
DAY03_DIR = Path(__file__).resolve().parents[1]
if str(DAY03_DIR) not in sys.path:
    sys.path.insert(0, str(DAY03_DIR))

# app/service 在导入时校验配置；测试使用占位值，不会发起真实请求
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("BASE_URL", "http://127.0.0.1:1/v1")


@pytest.fixture
def api_context(tmp_path):
    """隔离的 app 会话管理器、测试客户端和当前会话。"""
    from fastapi.testclient import TestClient

    from app import COOKIE_NAME, app
    from web_history import SessionManager, WebHistoryStore

    original_manager = app.state.session_manager
    original_service = app.state.user_service

    store = WebHistoryStore(tmp_path / "web_sessions")
    manager = SessionManager(store)
    app.state.session_manager = manager
    session = manager.create_new()

    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, session.session_id)

    yield {
        "app": app,
        "client": client,
        "session": session,
        "manager": manager,
        "store": store,
    }

    app.state.session_manager = original_manager
    app.state.user_service = original_service

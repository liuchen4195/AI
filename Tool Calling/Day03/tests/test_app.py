from fastapi.testclient import TestClient

from app import app, session
from prompt import SYSTEM_PROMPT


client = TestClient(app)


def test_health():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_index_page_is_served():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "天气查询助手" in response.text


def test_static_index_is_mounted():
    response = client.get("/static/index.html")

    assert response.status_code == 200
    assert "天气查询助手" in response.text


def test_session_starts_with_only_system_message():
    session.reset()

    assert session.messages == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert session.lock is not None


def test_session_add_turn_only_keeps_final_messages():
    session.reset()
    session.add_turn("北京天气怎么样？", "北京今天晴。")

    assert [message["role"] for message in session.messages] == [
        "system",
        "user",
        "assistant",
    ]
    assert session.messages[1] == {"role": "user", "content": "北京天气怎么样？"}
    assert session.messages[2] == {"role": "assistant", "content": "北京今天晴。"}
    assert all(message["role"] != "tool" for message in session.messages)


def test_session_reset_restores_initial_state():
    session.add_turn("上海天气怎么样？", "上海今天多云。")
    session.reset()

    assert len(session.messages) == 1
    assert session.messages[0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_health_does_not_expose_session_or_prompt():
    response = client.get("/api/health")

    assert response.json() == {"ok": True}
    assert SYSTEM_PROMPT not in response.text
    assert "messages" not in response.text

from fastapi.testclient import TestClient

from app import app
from prompt import SYSTEM_PROMPT
from web_history import ConversationSession, WebHistoryStore


client = TestClient(app)


def make_session(tmp_path):
    store = WebHistoryStore(tmp_path / "web_sessions")
    state = store.create()
    return ConversationSession(state["session_id"], state, store)


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


def test_session_starts_with_only_system_message(tmp_path):
    session = make_session(tmp_path)

    assert session.messages == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert session.turns == []
    assert session.lock is not None


def test_session_add_turn_only_keeps_final_messages(tmp_path):
    session = make_session(tmp_path)
    saved = session.add_turn({
        "turn_id": "turn_1",
        "question": "北京天气怎么样？",
        "answer": "北京今天晴。",
        "status": "success",
        "trace": {"status": "success"},
    })

    assert saved is True
    assert [message["role"] for message in session.messages] == [
        "system",
        "user",
        "assistant",
    ]
    assert session.messages[1] == {"role": "user", "content": "北京天气怎么样？"}
    assert session.messages[2] == {"role": "assistant", "content": "北京今天晴。"}
    assert all(message["role"] != "tool" for message in session.messages)
    assert session.turns[0]["turn_index"] == 1


def test_session_failed_turn_is_kept_out_of_model_context(tmp_path):
    session = make_session(tmp_path)
    session.add_turn({
        "turn_id": "turn_1",
        "question": "北京天气怎么样？",
        "answer": None,
        "status": "failed",
        "trace": {"status": "failed", "error": {"message": "模型请求失败"}},
    })

    assert session.turns[0]["status"] == "failed"
    assert session.messages == [{"role": "system", "content": SYSTEM_PROMPT}]


def test_session_reset_restores_initial_state(tmp_path):
    session = make_session(tmp_path)
    session.add_turn({
        "turn_id": "turn_1",
        "question": "上海天气怎么样？",
        "answer": "上海今天多云。",
        "status": "success",
        "trace": {"status": "success"},
    })
    session.reset()

    assert len(session.messages) == 1
    assert session.messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert session.turns == []


def test_health_does_not_expose_session_or_prompt():
    response = client.get("/api/health")

    assert response.json() == {"ok": True}
    assert SYSTEM_PROMPT not in response.text
    assert "messages" not in response.text

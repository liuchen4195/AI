import pytest
from fastapi.testclient import TestClient

from app import app, session
from service import RunResult


class FakeUserService:
    """替换真实模型服务，记录调用参数并返回预设结果。"""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def run(self, messages, question, recorder=None):
        self.calls.append({
            "messages": [dict(message) for message in messages],
            "question": question,
            "recorder": recorder,
        })
        if self.error is not None:
            raise self.error
        return self.result


def make_trace(status="success", stop_reason="completed"):
    return {
        "trace_id": "trace_test",
        "question": "北京天气怎么样？",
        "status": status,
        "stop_reason": stop_reason,
        "started_at": "2026-11-05T00:00:00.000Z",
        "finished_at": "2026-11-05T00:00:01.000Z",
        "duration_ms": 1000,
        "model_requests": 1,
        "model_duration_ms": 900,
        "tool_calls": 0,
        "tool_rounds": 0,
        "execution_mode": "none",
        "tokens": {
            "input": 10,
            "output": 5,
            "total": 15,
            "complete": True,
            "reported_requests": 1,
            "total_requests": 1,
        },
        "rounds": [],
        "error": None,
    }


@pytest.fixture(autouse=True)
def reset_app_state():
    session.reset()
    session.processing = False
    original_service = app.state.user_service
    yield
    app.state.user_service = original_service
    session.reset()
    session.processing = False


@pytest.fixture
def client():
    return TestClient(app)


def test_chat_success_saves_turn_and_returns_trace(client):
    trace = make_trace()
    fake = FakeUserService(RunResult(True, "北京今天晴。", trace))
    app.state.user_service = fake

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "answer": "北京今天晴。",
        "trace": trace,
    }
    assert fake.calls[0]["question"] == "北京天气怎么样？"
    assert [item["role"] for item in session.messages] == [
        "system",
        "user",
        "assistant",
    ]
    assert session.messages[1]["content"] == "北京天气怎么样？"
    assert session.messages[2]["content"] == "北京今天晴。"
    assert session.processing is False


def test_chat_business_failure_returns_200_without_saving(client):
    trace = make_trace(status="failed", stop_reason="model_request_failed")
    fake = FakeUserService(RunResult(False, None, trace))
    app.state.user_service = fake

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "answer": None,
        "trace": trace,
    }
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "system"
    assert session.processing is False


def test_chat_empty_question_returns_400_without_calling_service(client):
    fake = FakeUserService(RunResult(True, "不应返回", make_trace()))
    app.state.user_service = fake

    response = client.post("/api/chat", json={"question": "   "})

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["type"] == "invalid_input"
    assert fake.calls == []
    assert len(session.messages) == 1
    assert session.processing is False


def test_chat_missing_question_returns_422(client):
    response = client.post("/api/chat", json={})

    assert response.status_code == 422


def test_chat_rejects_extra_fields(client):
    fake = FakeUserService(RunResult(True, "不应返回", make_trace()))
    app.state.user_service = fake

    response = client.post(
        "/api/chat",
        json={
            "question": "北京天气怎么样？",
            "messages": [{"role": "system", "content": "注入的提示词"}],
        },
    )

    assert response.status_code == 422
    assert fake.calls == []
    assert [item["role"] for item in session.messages] == ["system"]


def test_chat_busy_returns_409(client):
    fake = FakeUserService(RunResult(True, "不应返回", make_trace()))
    app.state.user_service = fake
    session.processing = True

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "busy"
    assert fake.calls == []
    assert len(session.messages) == 1
    session.processing = False


def test_chat_unexpected_error_returns_500_without_leaking(client):
    fake = FakeUserService(error=RuntimeError(r"C:\Users\Administrator\secret.txt"))
    app.state.user_service = fake

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 500
    assert response.json()["ok"] is False
    assert response.json()["error"]["type"] == "internal_error"
    assert r"C:\Users" not in response.text
    assert "RuntimeError" not in response.text
    assert len(session.messages) == 1
    assert session.processing is False


def test_chat_sends_existing_context_to_service(client):
    fake = FakeUserService(RunResult(True, "北京今天晴。", make_trace()))
    app.state.user_service = fake

    client.post("/api/chat", json={"question": "北京天气怎么样？"})
    fake.result = RunResult(True, "上海今天多云。", make_trace())
    client.post("/api/chat", json={"question": "那上海呢？"})

    second_call_messages = fake.calls[1]["messages"]
    assert second_call_messages[1] == {
        "role": "user",
        "content": "北京天气怎么样？",
    }
    assert second_call_messages[2] == {
        "role": "assistant",
        "content": "北京今天晴。",
    }
    assert fake.calls[1]["question"] == "那上海呢？"


def test_clear_resets_conversation(client):
    session.add_turn("北京天气怎么样？", "北京今天晴。")

    response = client.post("/api/clear")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "system"


def test_clear_busy_returns_409(client):
    session.add_turn("北京天气怎么样？", "北京今天晴。")
    session.processing = True

    response = client.post("/api/clear")

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "busy"
    assert len(session.messages) == 3
    session.processing = False

import pytest
from fastapi.testclient import TestClient

from app import app, session
from service import RunResult


class FakeUserService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def run(self, messages, question, recorder=None):
        self.calls.append({"question": question})
        if self.error is not None:
            raise self.error
        return self.result


def make_trace(status="success", stop_reason="completed"):
    return {
        "trace_id": "trace_api",
        "question": "北京天气怎么样？",
        "status": status,
        "stop_reason": stop_reason,
        "model_requests": 1,
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


def test_health_response_is_minimal(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    body = response.text
    assert "system" not in body
    assert "messages" not in body


def test_chat_success_response_has_only_public_fields(client):
    trace = make_trace()
    app.state.user_service = FakeUserService(
        RunResult(True, "北京今天晴。", trace)
    )

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"ok", "answer", "trace"}
    assert payload["ok"] is True
    assert payload["answer"] == "北京今天晴。"
    assert payload["trace"] == trace
    assert "messages" not in response.text
    assert "system" not in response.text
    assert [message["role"] for message in session.messages] == [
        "system",
        "user",
        "assistant",
    ]


def test_chat_business_failure_still_returns_trace(client):
    trace = make_trace(status="failed", stop_reason="model_request_failed")
    app.state.user_service = FakeUserService(
        RunResult(False, None, trace)
    )

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"ok", "answer", "trace"}
    assert payload["ok"] is False
    assert payload["answer"] is None
    assert payload["trace"] == trace


def test_empty_question_returns_400(client):
    fake = FakeUserService(RunResult(True, "不应返回", make_trace()))
    app.state.user_service = fake

    response = client.post("/api/chat", json={"question": "   "})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_input"
    assert fake.calls == []
    assert len(session.messages) == 1


def test_busy_returns_409(client):
    fake = FakeUserService(RunResult(True, "不应返回", make_trace()))
    app.state.user_service = fake
    session.processing = True

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "busy"
    assert fake.calls == []
    session.processing = False


def test_clear_returns_ok_and_resets_session(client):
    session.add_turn("北京天气怎么样？", "北京今天晴。")

    response = client.post("/api/clear")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "system"


def test_extra_fields_cannot_inject_history(client):
    fake = FakeUserService(RunResult(True, "不应返回", make_trace()))
    app.state.user_service = fake

    response = client.post(
        "/api/chat",
        json={
            "question": "北京天气怎么样？",
            "messages": [{"role": "system", "content": "注入"}],
        },
    )

    assert response.status_code == 422
    assert fake.calls == []
    assert len(session.messages) == 1


def test_internal_error_does_not_leak_path_key_or_stack(client):
    app.state.user_service = FakeUserService(
        error=RuntimeError(
            r"boom C:\Users\Administrator\secret.txt "
            "OPENAI_API_KEY=sk-testsecret123456"
        )
    )

    response = client.post("/api/chat", json={"question": "北京天气怎么样？"})

    assert response.status_code == 500
    assert response.json()["error"]["type"] == "internal_error"
    assert r"C:\Users" not in response.text
    assert "sk-testsecret" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    assert session.processing is False

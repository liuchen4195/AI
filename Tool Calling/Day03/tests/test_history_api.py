from fastapi.testclient import TestClient

from app import COOKIE_NAME, app
from prompt import SYSTEM_PROMPT
from service import RunResult
from web_history import SessionManager


class FakeUserService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run(self, messages, question, recorder=None):
        self.calls.append({"question": question})
        return self.result


def make_trace(status="success", stop_reason="completed", error=None):
    return {
        "trace_id": "trace_history",
        "question": "北京天气怎么样？",
        "status": status,
        "stop_reason": stop_reason,
        "started_at": "2026-11-05T00:00:00.000Z",
        "finished_at": "2026-11-05T00:00:01.000Z",
        "duration_ms": 1000,
        "model_requests": 1,
        "tool_calls": 1,
        "tool_rounds": 1,
        "execution_mode": "serial",
        "tokens": {
            "input": 10,
            "output": 5,
            "total": 15,
            "complete": True,
            "reported_requests": 1,
            "total_requests": 1,
        },
        "rounds": [
            {
                "round": 1,
                "mode": "single",
                "call_count": 1,
                "duration_ms": 500,
                "calls": [
                    {
                        "call_id": "call_1",
                        "name": "get_weather",
                        "description": "根据经纬度查询城市天气时调用此工具",
                        "arguments": {"latitude": "1", "longitude": "2"},
                        "result": {"status": "success"},
                        "status": "success",
                        "execution": "serial",
                        "started_at": "2026-11-05T00:00:00.100Z",
                        "finished_at": "2026-11-05T00:00:00.600Z",
                        "duration_ms": 500,
                    }
                ],
            }
        ],
        "error": error,
    }


def send_turn(api_context, result):
    api_context["app"].state.user_service = FakeUserService(result)
    return api_context["client"].post(
        "/api/chat",
        json={"question": "北京天气怎么样？"},
    )


def test_chat_saves_turn_and_detail_is_available(api_context):
    trace = make_trace()
    response = send_turn(api_context, RunResult(True, "北京今天晴。", trace))

    assert response.status_code == 200
    payload = response.json()
    turn_id = payload["turn_id"]

    history = api_context["client"].get("/api/history")
    assert history.status_code == 200
    data = history.json()
    assert data["ok"] is True
    assert data["session_id"] == api_context["session"].session_id
    assert len(data["turns"]) == 1
    summary = data["turns"][0]
    assert summary["turn_id"] == turn_id
    assert summary["turn_index"] == 1
    assert summary["question"] == "北京天气怎么样？"
    assert summary["answer"] == "北京今天晴。"
    assert summary["status"] == "success"
    assert summary["has_trace"] is True

    detail = api_context["client"].get(f"/api/history/{turn_id}")
    assert detail.status_code == 200
    turn = detail.json()["turn"]
    assert turn["turn_id"] == turn_id
    assert turn["trace"] == trace
    assert turn["trace"]["rounds"][0]["calls"][0]["name"] == "get_weather"


def test_history_survives_manager_cache_restart(api_context):
    trace = make_trace()
    response = send_turn(api_context, RunResult(True, "北京今天晴。", trace))
    session_id = api_context["session"].session_id
    turn_id = response.json()["turn_id"]

    # 模拟服务重启：新的 SessionManager + 空缓存，通过 Cookie 从文件加载
    app.state.session_manager = SessionManager(api_context["store"])
    fresh_client = TestClient(app)
    fresh_client.cookies.set(COOKIE_NAME, session_id)

    history = fresh_client.get("/api/history")
    assert history.status_code == 200
    assert len(history.json()["turns"]) == 1
    assert history.json()["turns"][0]["turn_id"] == turn_id

    detail = fresh_client.get(f"/api/history/{turn_id}")
    assert detail.status_code == 200
    assert detail.json()["turn"]["trace"] == trace


def test_history_is_isolated_by_cookie(api_context):
    trace = make_trace()
    response = send_turn(api_context, RunResult(True, "北京今天晴。", trace))
    turn_id = response.json()["turn_id"]

    other_client = TestClient(app)
    other_history = other_client.get("/api/history")

    assert other_history.status_code == 200
    assert other_history.json()["turns"] == []
    assert other_history.json()["session_id"] != api_context["session"].session_id

    other_detail = other_client.get(f"/api/history/{turn_id}")
    assert other_detail.status_code == 404


def test_failed_turn_is_saved_with_error_summary(api_context):
    error = {
        "type": "model_request_failed",
        "message": "模型服务调用失败，请稍后重试",
        "stage": "model_request",
        "round": 1,
    }
    trace = make_trace(status="failed", stop_reason="model_request_failed", error=error)
    response = send_turn(api_context, RunResult(False, None, trace))

    assert response.status_code == 200
    assert response.json()["history_saved"] is True
    turn_id = response.json()["turn_id"]

    summary = api_context["client"].get("/api/history").json()["turns"][0]
    assert summary["status"] == "failed"
    assert summary["answer"] is None
    assert summary["error_message"] == "模型服务调用失败，请稍后重试"

    detail = api_context["client"].get(f"/api/history/{turn_id}").json()["turn"]
    assert detail["trace"]["error"]["stage"] == "model_request"


def test_empty_input_and_busy_do_not_create_history(api_context):
    client = api_context["client"]
    session = api_context["session"]

    empty = client.post("/api/chat", json={"question": "   "})
    assert empty.status_code == 400
    assert client.get("/api/history").json()["turns"] == []

    session.processing = True
    busy = client.post("/api/chat", json={"question": "北京天气怎么样？"})
    assert busy.status_code == 409
    assert client.get("/api/history").json()["turns"] == []
    session.processing = False


def test_clear_removes_history_and_detail(api_context):
    trace = make_trace()
    response = send_turn(api_context, RunResult(True, "北京今天晴。", trace))
    turn_id = response.json()["turn_id"]

    clear = api_context["client"].post("/api/clear")
    assert clear.status_code == 200
    assert clear.json() == {"ok": True}
    assert api_context["client"].get("/api/history").json()["turns"] == []
    assert api_context["client"].get(f"/api/history/{turn_id}").status_code == 404


def test_missing_turn_returns_404(api_context):
    response = api_context["client"].get("/api/history/not-found")

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "turn_not_found"


def test_history_does_not_expose_system_prompt_or_secret(api_context):
    trace = make_trace()
    send_turn(api_context, RunResult(True, "北京今天晴。", trace))

    history_text = api_context["client"].get("/api/history").text
    assert SYSTEM_PROMPT not in history_text
    assert "sk-" not in history_text
    assert "OPENAI_API_KEY" not in history_text


def test_first_history_request_sets_http_only_cookie(api_context):
    fresh_client = TestClient(app)

    response = fresh_client.get("/api/history")

    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert len(response.json()["session_id"]) == 32


def test_persistence_failure_returns_answer_with_warning(api_context, monkeypatch):
    trace = make_trace()

    def fail_save(state):
        raise OSError("disk full")

    monkeypatch.setattr(api_context["store"], "save", fail_save)
    response = send_turn(api_context, RunResult(True, "北京今天晴。", trace))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["answer"] == "北京今天晴。"
    assert payload["history_saved"] is False
    assert len(api_context["session"].turns) == 1

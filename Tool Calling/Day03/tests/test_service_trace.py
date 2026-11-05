import asyncio
import json
from types import SimpleNamespace

import service
from service import RunResult, UserService
from tracks import Tracks


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tool.id,
                    "type": "function",
                    "function": {
                        "name": tool.function.name,
                        "arguments": tool.function.arguments,
                    },
                }
                for tool in self.tool_calls
            ]
        return data


def make_tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def make_usage(prompt=10, completion=5, total=15):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def make_response(content=None, tool_calls=None, usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=FakeMessage(content, tool_calls))],
        usage=usage,
    )


def make_service(tmp_path):
    instance = UserService()
    instance.tracks = Tracks(str(tmp_path / "tracks.json"))
    return instance


def run(coroutine):
    return asyncio.run(coroutine)


def test_run_without_tools_returns_success_trace(tmp_path):
    async def scenario():
        svc = make_service(tmp_path)

        async def send(messages):
            return make_response("北京今天晴。", usage=make_usage(10, 5, 15))

        svc.send = send
        return await svc.run([{"role": "system", "content": "sys"}], "北京天气")

    result = run(scenario())
    trace = result.trace

    assert isinstance(result, RunResult)
    assert result.ok is True
    assert result.answer == "北京今天晴。"
    assert trace["status"] == "success"
    assert trace["stop_reason"] == "completed"
    assert trace["model_requests"] == 1
    assert trace["tool_calls"] == 0
    assert trace["tool_rounds"] == 0
    assert trace["execution_mode"] == "none"
    assert trace["duration_ms"] is not None
    assert trace["tokens"]["input"] == 10
    assert trace["tokens"]["output"] == 5
    assert trace["tokens"]["total"] == 15
    assert trace["tokens"]["complete"] is True
    assert trace["rounds"] == []


def test_run_single_tool_round_records_call(tmp_path):
    tool = make_tool_call(
        "call_1",
        "get_weather",
        {"latitude": "39.9", "longitude": "116.4"},
    )

    async def scenario():
        svc = make_service(tmp_path)
        responses = iter([
            make_response(tool_calls=[tool], usage=make_usage(5, 2, 7)),
            make_response("北京今天晴。", usage=make_usage(6, 3, 9)),
        ])

        async def send(messages):
            return next(responses)

        async def fake_run_tools(tool_call):
            return {"status": "success", "message": "查询成功", "data": {"temperature": 20}}

        svc.send = send
        svc.run_tools = fake_run_tools
        return await svc.run([{"role": "system", "content": "sys"}], "北京天气")

    result = run(scenario())
    trace = result.trace

    assert result.ok is True
    assert trace["status"] == "success"
    assert trace["model_requests"] == 2
    assert trace["tool_calls"] == 1
    assert trace["tool_rounds"] == 1
    assert trace["execution_mode"] == "serial"
    assert trace["tokens"]["total"] == 16

    round_entry = trace["rounds"][0]
    call_entry = round_entry["calls"][0]
    assert round_entry["mode"] == "single"
    assert call_entry["name"] == "get_weather"
    assert call_entry["description"] == "根据经纬度查询城市天气时调用此工具"
    assert call_entry["execution"] == "serial"
    assert call_entry["status"] == "success"
    assert call_entry["arguments"]["latitude"] == "39.9"
    assert call_entry["result"]["data"]["temperature"] == 20
    assert call_entry["started_at"] is not None
    assert call_entry["finished_at"] is not None
    assert call_entry["duration_ms"] is not None


def test_run_parallel_tool_round_marks_parallel(tmp_path):
    calls = [
        make_tool_call("call_a", "get_weather", {"latitude": "1", "longitude": "2"}),
        make_tool_call("call_b", "get_quality", {"latitude": "1", "longitude": "2"}),
    ]

    async def scenario():
        svc = make_service(tmp_path)
        responses = iter([
            make_response(tool_calls=calls, usage=make_usage()),
            make_response("综合回答。", usage=make_usage()),
        ])

        async def send(messages):
            return next(responses)

        async def fake_run_tools(tool_call):
            return {"status": "success", "data": tool_call.function.name}

        svc.send = send
        svc.run_tools = fake_run_tools
        return await svc.run([{"role": "system", "content": "sys"}], "天气和空气")

    result = run(scenario())
    trace = result.trace
    round_entry = trace["rounds"][0]

    assert result.ok is True
    assert trace["status"] == "success"
    assert trace["tool_calls"] == 2
    assert round_entry["mode"] == "parallel"
    assert [call["execution"] for call in round_entry["calls"]] == ["parallel", "parallel"]
    assert trace["execution_mode"] == "parallel"


def test_run_multi_round_mixed_execution_mode(tmp_path):
    single_call = [make_tool_call("call_1", "get_city_pos", {"city_name": "北京"})]
    parallel_calls = [
        make_tool_call("call_2", "get_weather", {"latitude": "1", "longitude": "2"}),
        make_tool_call("call_3", "get_quality", {"latitude": "1", "longitude": "2"}),
    ]

    async def scenario():
        svc = make_service(tmp_path)
        responses = iter([
            make_response(tool_calls=single_call, usage=make_usage()),
            make_response(tool_calls=parallel_calls, usage=make_usage()),
            make_response("最终回答。", usage=make_usage()),
        ])

        async def send(messages):
            return next(responses)

        async def fake_run_tools(tool_call):
            return {"status": "success"}

        svc.send = send
        svc.run_tools = fake_run_tools
        return await svc.run([{"role": "system", "content": "sys"}], "比较北京")

    result = run(scenario())
    trace = result.trace

    assert result.ok is True
    assert trace["model_requests"] == 3
    assert trace["tool_rounds"] == 2
    assert trace["tool_calls"] == 3
    assert [item["mode"] for item in trace["rounds"]] == ["single", "parallel"]
    assert trace["execution_mode"] == "mixed"


def test_run_model_exception_returns_failed_result(tmp_path):
    async def scenario():
        svc = make_service(tmp_path)

        async def send(messages):
            raise RuntimeError(r"boom C:\Users\Administrator\secret.txt")

        svc.send = send
        return await svc.run([{"role": "system", "content": "sys"}], "北京")

    result = run(scenario())
    trace = result.trace

    assert result.ok is False
    assert result.answer is None
    assert trace["status"] == "failed"
    assert trace["stop_reason"] == "model_request_failed"
    assert trace["model_requests"] == 1
    assert trace["error"]["stage"] == "model_request"
    assert trace["error"]["round"] == 1
    assert r"C:\Users" not in json.dumps(trace, ensure_ascii=False)


def test_run_max_model_rounds_returns_failed_result(tmp_path):
    tool = make_tool_call("call_loop", "get_weather", {"latitude": "1", "longitude": "2"})

    async def scenario():
        svc = make_service(tmp_path)

        async def send(messages):
            return make_response(tool_calls=[tool], usage=make_usage())

        async def fake_run_tools(tool_call):
            return {"status": "success"}

        svc.send = send
        svc.run_tools = fake_run_tools
        return await svc.run([{"role": "system", "content": "sys"}], "循环")

    result = run(scenario())
    trace = result.trace

    assert result.ok is False
    assert trace["status"] == "failed"
    assert trace["stop_reason"] == "max_model_rounds"
    assert trace["model_requests"] == service.MAX_MODEL_ROUNDS
    assert trace["tool_rounds"] == service.MAX_MODEL_ROUNDS
    assert trace["execution_mode"] == "serial"


def test_run_empty_answer_returns_failed_result(tmp_path):
    async def scenario():
        svc = make_service(tmp_path)

        async def send(messages):
            return make_response("", usage=make_usage())

        svc.send = send
        return await svc.run([{"role": "system", "content": "sys"}], "北京")

    result = run(scenario())

    assert result.ok is False
    assert result.answer is None
    assert result.trace["status"] == "failed"
    assert result.trace["stop_reason"] == "empty_answer"
    assert result.trace["error"]["stage"] == "final_answer"


def test_run_tool_exception_marks_partial_and_redacts(tmp_path):
    tool = make_tool_call("call_1", "get_weather", {"latitude": "1", "longitude": "2"})

    async def scenario():
        svc = make_service(tmp_path)
        responses = iter([
            make_response(tool_calls=[tool], usage=make_usage()),
            make_response("工具失败了。", usage=make_usage()),
        ])

        async def send(messages):
            return next(responses)

        async def fake_run_tools(tool_call):
            raise RuntimeError(r"工具执行失败: C:\Users\Administrator\secret.txt")

        svc.send = send
        svc.run_tools = fake_run_tools
        return await svc.run([{"role": "system", "content": "sys"}], "测试")

    result = run(scenario())
    call_entry = result.trace["rounds"][0]["calls"][0]

    assert result.ok is True
    assert result.trace["status"] == "partial"
    assert call_entry["status"] == "error"
    assert call_entry["error_type"] == "tool_execution_failed"
    assert r"C:\Users" not in call_entry["error_message"]


def test_run_tool_reported_error_marks_partial(tmp_path):
    tool = make_tool_call("call_1", "get_room_info", {"room_name": "不存在"})

    async def scenario():
        svc = make_service(tmp_path)
        responses = iter([
            make_response(tool_calls=[tool], usage=make_usage()),
            make_response("没有找到该会议室。", usage=make_usage()),
        ])

        async def send(messages):
            return next(responses)

        async def fake_run_tools(tool_call):
            return {"status": "error", "message": "未找到会议室「不存在」", "data": None}

        svc.send = send
        svc.run_tools = fake_run_tools
        return await svc.run([{"role": "system", "content": "sys"}], "会议室")

    result = run(scenario())
    call_entry = result.trace["rounds"][0]["calls"][0]

    assert result.ok is True
    assert result.trace["status"] == "partial"
    assert call_entry["status"] == "error"
    assert call_entry["error_type"] == "tool_reported_error"
    assert "未找到会议室" in call_entry["error_message"]


def test_run_missing_usage_keeps_tokens_null(tmp_path):
    async def scenario():
        svc = make_service(tmp_path)

        async def send(messages):
            return make_response("北京今天晴。", usage=None)

        svc.send = send
        return await svc.run([{"role": "system", "content": "sys"}], "北京")

    result = run(scenario())
    tokens = result.trace["tokens"]

    assert result.ok is True
    assert tokens["input"] is None
    assert tokens["output"] is None
    assert tokens["total"] is None
    assert tokens["complete"] is False
    assert tokens["reported_requests"] == 0
    assert tokens["total_requests"] == 1

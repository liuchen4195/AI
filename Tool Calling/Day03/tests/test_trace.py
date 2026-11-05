import json
from types import SimpleNamespace

import pytest

from trace import (
    TOOL_DESCRIPTIONS,
    TraceRecorder,
    redact_text,
    sanitize_error,
)


class ManualClock:
    """可手动推进的测试时钟，替代 time.perf_counter。"""

    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeNow:
    """生成可读且递增的假时间字符串。"""

    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        return f"2026-11-05T00:00:{self.count:02d}.000Z"


def make_tool(
    call_id="call_1",
    name="get_weather",
    arguments='{"latitude":"39.9","longitude":"116.4"}',
):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def make_usage(prompt=10, completion=5, total=15):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def finish_model(recorder, clock, usage=None, ok=True, advance=0.1):
    started = recorder.begin_model_request()
    clock.advance(advance)
    recorder.finish_model_request(started, usage=usage, ok=ok)


def test_no_tool_success_trace():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())

    finish_model(recorder, clock, usage=make_usage(10, 5, 15), advance=0.25)
    clock.advance(0.05)
    trace = recorder.finish("success", "completed")

    assert trace["status"] == "success"
    assert trace["stop_reason"] == "completed"
    assert trace["model_requests"] == 1
    assert trace["model_duration_ms"] == 250
    assert trace["tool_calls"] == 0
    assert trace["tool_rounds"] == 0
    assert trace["execution_mode"] == "none"
    assert trace["duration_ms"] == 300
    assert trace["tokens"] == {
        "input": 10,
        "output": 5,
        "total": 15,
        "complete": True,
        "reported_requests": 1,
        "total_requests": 1,
    }
    assert trace["error"] is None


def test_single_tool_round_and_call_timing():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())
    finish_model(recorder, clock)

    round_entry = recorder.begin_tool_round([make_tool()])
    call_entry = round_entry["calls"][0]
    recorder.start_tool_call(call_entry)
    clock.advance(0.04)
    recorder.finish_tool_call(call_entry, {"status": "success", "data": 1})
    clock.advance(0.01)
    recorder.finish_tool_round(round_entry)

    trace = recorder.finish("success", "completed")

    assert round_entry["mode"] == "single"
    assert round_entry["call_count"] == 1
    assert round_entry["duration_ms"] == 50
    assert call_entry["execution"] == "serial"
    assert call_entry["status"] == "success"
    assert call_entry["duration_ms"] == 40
    assert call_entry["started_at"] is not None
    assert call_entry["finished_at"] is not None
    assert trace["execution_mode"] == "serial"
    assert trace["tool_rounds"] == 1
    assert trace["tool_calls"] == 1


def test_parallel_round_duration_is_not_sum_of_calls():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气和空气", clock=clock, now=FakeNow())

    round_entry = recorder.begin_tool_round([
        make_tool("call_a", "get_weather"),
        make_tool("call_b", "get_quality"),
    ])
    call_a, call_b = round_entry["calls"]

    # 两个调用同一时刻开始，模拟并发
    recorder.start_tool_call(call_a)
    recorder.start_tool_call(call_b)

    clock.advance(0.05)
    recorder.finish_tool_call(call_b, {"status": "success"})
    clock.advance(0.05)
    recorder.finish_tool_call(call_a, {"status": "success"})
    clock.advance(0.02)
    recorder.finish_tool_round(round_entry)

    trace = recorder.finish("success", "completed")

    call_sum = call_a["duration_ms"] + call_b["duration_ms"]
    assert call_a["duration_ms"] == 100
    assert call_b["duration_ms"] == 50
    assert call_sum == 150
    assert round_entry["duration_ms"] == 120
    assert round_entry["duration_ms"] != call_sum
    assert round_entry["mode"] == "parallel"
    assert call_a["execution"] == "parallel"
    assert call_b["execution"] == "parallel"
    assert trace["execution_mode"] == "parallel"


def test_multi_round_mixed_execution_mode():
    clock = ManualClock()
    recorder = TraceRecorder("多城市比较", clock=clock, now=FakeNow())

    round_one = recorder.begin_tool_round([
        make_tool("call_1", "get_weather"),
        make_tool("call_2", "get_quality"),
    ])
    for call_entry in round_one["calls"]:
        recorder.start_tool_call(call_entry)
    clock.advance(0.02)
    for call_entry in round_one["calls"]:
        recorder.finish_tool_call(call_entry, {"status": "success"})
    clock.advance(0.01)
    recorder.finish_tool_round(round_one)

    round_two = recorder.begin_tool_round([
        make_tool("call_3", "get_room_info", '{"room_name":"星辰"}'),
    ])
    recorder.start_tool_call(round_two["calls"][0])
    clock.advance(0.03)
    recorder.finish_tool_call(round_two["calls"][0], {"status": "success"})
    clock.advance(0.01)
    recorder.finish_tool_round(round_two)

    trace = recorder.finish("success", "completed")

    assert trace["tool_rounds"] == 2
    assert trace["tool_calls"] == 3
    assert [item["round"] for item in trace["rounds"]] == [1, 2]
    assert [item["mode"] for item in trace["rounds"]] == ["parallel", "single"]
    assert trace["execution_mode"] == "mixed"


def test_tokens_missing_are_none_not_zero():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())

    finish_model(recorder, clock, usage=None, ok=True)
    trace = recorder.finish("success", "completed")

    assert trace["tokens"] == {
        "input": None,
        "output": None,
        "total": None,
        "complete": False,
        "reported_requests": 0,
        "total_requests": 1,
    }


def test_tokens_partial_usage_marks_incomplete():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())

    finish_model(recorder, clock, usage=make_usage(10, 5, 15))
    finish_model(recorder, clock, usage=None)
    trace = recorder.finish("success", "completed")

    assert trace["tokens"]["input"] == 10
    assert trace["tokens"]["output"] == 5
    assert trace["tokens"]["total"] == 15
    assert trace["tokens"]["complete"] is False
    assert trace["tokens"]["reported_requests"] == 1
    assert trace["tokens"]["total_requests"] == 2


def test_tokens_accumulate_across_model_requests():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())

    finish_model(recorder, clock, usage=make_usage(10, 5, 15))
    finish_model(recorder, clock, usage=make_usage(20, 6, 26))
    trace = recorder.finish("success", "completed")

    assert trace["tokens"]["input"] == 30
    assert trace["tokens"]["output"] == 11
    assert trace["tokens"]["total"] == 41
    assert trace["tokens"]["complete"] is True
    assert trace["tokens"]["reported_requests"] == 2


def test_tokens_total_derived_from_input_and_output():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())

    usage_without_total = SimpleNamespace(prompt_tokens=3, completion_tokens=4)
    finish_model(recorder, clock, usage=usage_without_total)
    trace = recorder.finish("success", "completed")

    assert trace["tokens"]["input"] == 3
    assert trace["tokens"]["output"] == 4
    assert trace["tokens"]["total"] == 7
    assert trace["tokens"]["complete"] is True


@pytest.mark.parametrize(
    "error, expected_type",
    [
        (RuntimeError("访问的工具不存在！"), "tool_not_found"),
        (RuntimeError("参数解析失败: bad json"), "argument_parse_failed"),
        (RuntimeError("参数校验未通过!"), "validation_failed"),
        (TimeoutError("timed out"), "timeout"),
        (RuntimeError("未知异常"), "tool_execution_failed"),
    ],
)
def test_error_classification(error, expected_type):
    error_type, message = sanitize_error(error)
    assert error_type == expected_type
    assert isinstance(message, str) and message


def test_error_message_hides_paths_and_keys():
    error = RuntimeError(
        r"工具执行失败: C:\Users\Administrator\secret.txt sk-abcdef1234567890"
    )
    error_type, message = sanitize_error(error)

    assert error_type == "tool_execution_failed"
    assert r"C:\Users" not in message
    assert "sk-" not in message


def test_redact_text_removes_paths_keys_and_traceback():
    path_text = redact_text(r"读取 C:\Users\Administrator\secret.txt 失败")
    key_text = redact_text("key=sk-abcdef1234567890")
    traceback_text = redact_text(
        'Traceback (most recent call last):\n  File "C:\\x", line 1\nValueError: x'
    )

    assert "C:\\Users" not in path_text
    assert "[路径已隐藏]" in path_text
    assert "sk-" not in key_text
    assert "Traceback" not in traceback_text


def test_tool_reported_error_is_redacted_and_marked_error():
    clock = ManualClock()
    recorder = TraceRecorder("会议室", clock=clock, now=FakeNow())
    round_entry = recorder.begin_tool_round([make_tool("call_1", "get_room_info")])
    call_entry = round_entry["calls"][0]

    recorder.start_tool_call(call_entry)
    clock.advance(0.01)
    recorder.finish_tool_call(
        call_entry,
        {"status": "error", "message": "找不到 C:\\Users\\Administrator\\rooms.json"},
        "tool_reported_error",
        "找不到 C:\\Users\\Administrator\\rooms.json",
    )

    assert call_entry["status"] == "error"
    assert call_entry["error_type"] == "tool_reported_error"
    assert "C:\\Users" not in call_entry["error_message"]


def test_unfinished_call_is_not_shown_as_success():
    clock = ManualClock()
    recorder = TraceRecorder("会议室", clock=clock, now=FakeNow())
    round_entry = recorder.begin_tool_round([make_tool("call_1", "get_room_info")])

    recorder.finish_tool_round(round_entry)
    call_entry = round_entry["calls"][0]

    assert call_entry["status"] == "error"
    assert call_entry["result"] is None
    assert call_entry["started_at"] is None
    assert call_entry["duration_ms"] is None


def test_trace_is_json_serializable_without_internal_keys():
    clock = ManualClock()
    recorder = TraceRecorder("北京天气", clock=clock, now=FakeNow())
    finish_model(recorder, clock, usage=make_usage())

    round_entry = recorder.begin_tool_round([make_tool()])
    recorder.start_tool_call(round_entry["calls"][0])
    clock.advance(0.01)
    recorder.finish_tool_call(round_entry["calls"][0], {"status": "success"})
    recorder.finish_tool_round(round_entry)
    trace = recorder.finish("success", "completed")

    encoded = json.dumps(trace, ensure_ascii=False)
    assert "_started_perf" not in encoded
    assert trace["trace_id"]
    assert trace["started_at"].endswith("Z")


def test_tool_descriptions_come_from_tool_contracts():
    assert set(TOOL_DESCRIPTIONS) == {
        "get_city_pos",
        "get_weather",
        "get_quality",
        "get_room_info",
    }
    assert TOOL_DESCRIPTIONS["get_weather"] == "根据经纬度查询城市天气时调用此工具"

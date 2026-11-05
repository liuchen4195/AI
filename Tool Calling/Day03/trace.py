import json
import re
import time
import uuid
from datetime import datetime, timezone

from model import TOOLS


# 工具名称 -> 用途说明，直接复用给模型看的工具合同
TOOL_DESCRIPTIONS = {
    item["function"]["name"]: item["function"].get("description", "")
    for item in TOOLS
}

# 工具错误的用户可读消息；不直接展示原始异常
ERROR_MESSAGES = {
    "tool_not_found": "模型请求了未授权的工具",
    "argument_parse_failed": "工具参数格式不正确",
    "validation_failed": "工具参数校验未通过",
    "timeout": "工具调用超时",
    "tool_execution_failed": "工具执行失败，请稍后重试",
    "tool_reported_error": "工具返回错误",
    "model_request_failed": "模型服务调用失败，请稍后重试",
}

# 错误信息脱敏：密钥、认证头、本机路径、异常堆栈
REDACTION_PATTERNS = [
    (re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}"), "[密钥已隐藏]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"), "Bearer [已隐藏]"),
    (
        re.compile(r"(?i)\b(api[_-]?key|password|secret|token)\b\s*[=:]\s*[^\s,;]+"),
        r"\1=[已隐藏]",
    ),
    (re.compile(r"[A-Za-z]:\\[^\n\r\"']*"), "[路径已隐藏]"),
    (re.compile(r"[A-Za-z]:/[^\s\"']*"), "[路径已隐藏]"),
    (re.compile(r"/(?:home|Users|tmp|var|opt|root)/[^\s\"']*"), "[路径已隐藏]"),
    (re.compile(r"(?is)Traceback \(most recent call last\):.*"), "[堆栈已隐藏]"),
]


def utc_now_iso():
    """返回毫秒级 UTC 时间，例如 2026-11-05T09:30:12.123Z。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_arguments(raw_arguments):
    """把模型返回的参数 JSON 字符串转成对象；解析失败时保留原始字符串。"""
    try:
        return json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError, ValueError):
        return raw_arguments


def elapsed_ms(started_perf, finished_perf):
    """由两个 perf_counter 值计算整数毫秒；缺失任意一端返回 None。"""
    if started_perf is None or finished_perf is None:
        return None
    return int(round((finished_perf - started_perf) * 1000))


def redact_text(text):
    """清理错误文本中的密钥、认证头和本机路径；不是用于展示正常工具结果。"""
    if text is None:
        return None
    cleaned = str(text)
    for pattern, replacement in REDACTION_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def default_message(error_type):
    return ERROR_MESSAGES.get(error_type, "操作失败，请稍后重试")


def classify_error(error):
    """把异常归类成稳定的错误码，供页面展示与测试使用。"""
    if error is None:
        return "tool_execution_failed"

    # 自定义异常可以携带明确的 error_type
    explicit_type = getattr(error, "error_type", None)
    if explicit_type:
        return explicit_type

    if isinstance(error, TimeoutError):
        return "timeout"

    class_name = type(error).__name__.lower()
    text = str(error)
    lowered = text.lower()

    if "timeout" in class_name or "timed out" in lowered or "timeout" in lowered or "超时" in text:
        return "timeout"
    if "访问的工具不存在" in text or "tool_not_found" in lowered:
        return "tool_not_found"
    if "参数解析失败" in text or "argument_parse" in lowered:
        return "argument_parse_failed"
    if "参数校验未通过" in text or "validation" in lowered:
        return "validation_failed"
    return "tool_execution_failed"


def sanitize_error(error):
    """
    返回 (error_type, 用户可读消息)。

    只使用分类后的固定消息，不把原始异常文本直接展示给用户，
    因此不会泄露本机路径、密钥或异常堆栈。
    """
    error_type = classify_error(error)
    message = getattr(error, "user_message", None) or default_message(error_type)
    return error_type, redact_text(message)


def _usage_value(usage, *names):
    """兼容对象属性和字典两种 usage 形式。"""
    if usage is None:
        return None
    for name in names:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None)
        if value is not None:
            return value
    return None


def _derive_execution_mode(rounds):
    """只根据真实工具轮次推导调用方式，不根据工具名称猜测。"""
    if not rounds:
        return "none"
    if len(rounds) == 1:
        return "parallel" if rounds[0]["call_count"] > 1 else "serial"
    if any(item["call_count"] > 1 for item in rounds):
        return "mixed"
    return "serial"


class TraceRecorder:
    """
    一轮对话的轨迹记录器。

    - 模型请求：次数、耗时、Token 用量累计；
    - 工具轮次：轮次编号、调用数量、串行/并行、轮次起止与耗时；
    - 工具调用：调用编号、名称、用途、参数、结果、状态、错误、起止与耗时；
    - 收尾：整体状态、停止原因、总耗时、调用方式。

    所有未采集到的值保持 None，由页面显示“未记录/未返回”。
    """

    def __init__(self, question, *, clock=None, now=None):
        self._clock = clock or time.perf_counter
        self._now = now or utc_now_iso
        self._started_perf = self._clock()
        self._model_durations = []
        self._token_input = None
        self._token_output = None
        self._token_total = None
        self._token_reported_requests = 0
        self._token_complete = True

        self.trace = {
            "trace_id": uuid.uuid4().hex[:12],
            "question": question,
            "status": "running",
            "stop_reason": None,
            "started_at": self._now(),
            "finished_at": None,
            "duration_ms": None,
            "model_requests": 0,
            "model_duration_ms": 0,
            "tool_calls": 0,
            "tool_rounds": 0,
            "execution_mode": "none",
            "tokens": {
                "input": None,
                "output": None,
                "total": None,
                "complete": False,
                "reported_requests": 0,
                "total_requests": 0,
            },
            "rounds": [],
            "error": None,
        }

    # ---- 模型请求 ----
    def begin_model_request(self):
        """开始一次模型请求，返回用于计算耗时的 perf_counter 起点。"""
        self.trace["model_requests"] += 1
        self.trace["tokens"]["total_requests"] += 1
        return self._clock()

    def finish_model_request(self, started_perf, usage=None, ok=True):
        """结束一次模型请求，累计耗时与 Token。"""
        duration = elapsed_ms(started_perf, self._clock())
        if duration is not None:
            self._model_durations.append(duration)
        self.trace["model_duration_ms"] = sum(
            value for value in self._model_durations if value is not None
        )

        if not ok:
            self._token_complete = False
            self._refresh_tokens()
            return duration

        self._accumulate_usage(usage)
        return duration

    def _accumulate_usage(self, usage):
        input_tokens = _usage_value(usage, "prompt_tokens", "input_tokens")
        output_tokens = _usage_value(usage, "completion_tokens", "output_tokens")
        total_tokens = _usage_value(usage, "total_tokens")

        if usage is None or (
            input_tokens is None and output_tokens is None and total_tokens is None
        ):
            self._token_complete = False
            self._refresh_tokens()
            return

        self._token_reported_requests += 1

        if input_tokens is not None:
            self._token_input = (self._token_input or 0) + int(input_tokens)
        else:
            self._token_complete = False

        if output_tokens is not None:
            self._token_output = (self._token_output or 0) + int(output_tokens)
        else:
            self._token_complete = False

        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            # 服务商未返回 total 时，用实际返回的输入/输出相加，不按字符估算
            total_tokens = int(input_tokens) + int(output_tokens)

        if total_tokens is not None:
            self._token_total = (self._token_total or 0) + int(total_tokens)
        else:
            self._token_complete = False

        self._refresh_tokens()

    def _refresh_tokens(self):
        tokens = self.trace["tokens"]
        tokens["input"] = self._token_input
        tokens["output"] = self._token_output
        tokens["total"] = self._token_total
        tokens["reported_requests"] = self._token_reported_requests
        tokens["complete"] = bool(
            self._token_complete
            and tokens["total_requests"] > 0
            and self._token_reported_requests == tokens["total_requests"]
        )

    # ---- 工具轮次与调用 ----
    def begin_tool_round(self, tool_calls):
        """开始一轮工具调用，返回轮次记录（含每个调用的占位信息）。"""
        self.trace["tool_rounds"] += 1
        call_count = len(tool_calls)
        mode = "parallel" if call_count > 1 else "single"
        round_entry = {
            "round": len(self.trace["rounds"]) + 1,
            "mode": mode,
            "call_count": call_count,
            "started_at": self._now(),
            "finished_at": None,
            "duration_ms": None,
            "calls": [],
        }

        for tool in tool_calls:
            round_entry["calls"].append({
                "call_id": tool.id,
                "name": tool.function.name,
                "description": TOOL_DESCRIPTIONS.get(tool.function.name, "未知工具"),
                "arguments": parse_arguments(tool.function.arguments),
                "result": None,
                "status": "running",
                "error_type": None,
                "error_message": None,
                "execution": "parallel" if call_count > 1 else "serial",
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
            })

        round_entry["_started_perf"] = self._clock()
        self.trace["tool_calls"] += call_count
        self.trace["rounds"].append(round_entry)
        return round_entry

    def start_tool_call(self, call_entry):
        """在工具协程真正开始执行时调用，记录该调用的开始时间。"""
        call_entry["status"] = "running"
        call_entry["started_at"] = self._now()
        call_entry["_started_perf"] = self._clock()

    def finish_tool_call(self, call_entry, result, error_type=None, error_message=None):
        """结束一个工具调用，写入结果、状态、错误与耗时。"""
        finished_perf = self._clock()
        started_perf = call_entry.pop("_started_perf", None)
        call_entry["result"] = result
        call_entry["finished_at"] = self._now()
        call_entry["duration_ms"] = elapsed_ms(started_perf, finished_perf)

        if started_perf is None and not error_type:
            error_type = "tool_execution_failed"
            error_message = "工具未正常执行"

        if error_type:
            call_entry["status"] = "error"
            call_entry["error_type"] = error_type
            call_entry["error_message"] = redact_text(
                error_message or default_message(error_type)
            )
        else:
            call_entry["status"] = "success"
            call_entry["error_type"] = None
            call_entry["error_message"] = None

    def finish_tool_round(self, round_entry):
        """结束一轮工具调用；未完成的调用标记为失败，不能显示为成功。"""
        finished_perf = self._clock()
        started_perf = round_entry.pop("_started_perf", None)
        round_entry["finished_at"] = self._now()
        round_entry["duration_ms"] = elapsed_ms(started_perf, finished_perf)

        for call_entry in round_entry["calls"]:
            if call_entry["status"] == "running":
                self.finish_tool_call(
                    call_entry,
                    None,
                    "tool_execution_failed",
                    "工具未返回结果",
                )

    def has_tool_errors(self):
        return any(
            call["status"] == "error"
            for round_entry in self.trace["rounds"]
            for call in round_entry["calls"]
        )

    # ---- 整轮收尾 ----
    def finish(self, status, stop_reason, error=None):
        """结束本轮；补齐未完成轮次，写入整体状态、耗时与调用方式。"""
        for round_entry in self.trace["rounds"]:
            if round_entry["finished_at"] is None:
                self.finish_tool_round(round_entry)

        self.trace["status"] = status
        self.trace["stop_reason"] = stop_reason

        if error is None:
            self.trace["error"] = None
        elif isinstance(error, dict):
            safe_error = dict(error)
            safe_error["message"] = redact_text(safe_error.get("message"))
            self.trace["error"] = safe_error
        else:
            self.trace["error"] = {
                "type": stop_reason,
                "message": redact_text(error),
                "stage": None,
                "round": None,
            }

        self.trace["finished_at"] = self._now()
        self.trace["duration_ms"] = elapsed_ms(self._started_perf, self._clock())
        self.trace["execution_mode"] = _derive_execution_mode(self.trace["rounds"])
        self._refresh_tokens()
        return self.trace

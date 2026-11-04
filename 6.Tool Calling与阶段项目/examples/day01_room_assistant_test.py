# -*- coding: utf-8 -*-
"""Day01 会议室助手的离线安全与循环测试。

使用假模型（FakeClient）验证：
1. execute_tool_call() 的七个安全边界（call_1 ~ call_7）；
2. 消息顺序：assistant 工具请求必须位于 tool 结果之前；
3. tool 消息复用模型返回的原始调用编号；
4. 空回答与轮数上限两个停止条件。

运行方式（在仓库根目录）：
    python "6.Tool Calling与阶段项目/examples/day01_room_assistant_test.py"

本文件不访问网络、不读取 .env，全部结论来自离线假模型；
它证明程序分支和消息顺序正确，但不能代替真实云端调用的证据。
"""

import json

from day01_room_assistant import (
    MAX_ROUNDS,
    TOOL_REGISTRY,
    execute_tool_call,
    run_room_assistant,
)


# --------------------------------------------------------------------------
# 假模型：只实现主程序实际用到的最小接口
# --------------------------------------------------------------------------
class FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> dict:
        data = {"role": "assistant"}
        if self.content is not None or not exclude_none:
            data["content"] = self.content
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ]
        return data


class FakeResponse:
    def __init__(self, message: FakeMessage):
        self.choices = [type("Choice", (), {"message": message})()]


class FakeCompletions:
    """按脚本逐个返回响应，并记录每次请求的 messages 供顺序检查。"""

    def __init__(self, scripted_responses):
        self.scripted_responses = list(scripted_responses)
        self.recorded_requests = []

    def create(self, model=None, messages=None, **kwargs):
        self.recorded_requests.append(messages)
        return FakeResponse(self.scripted_responses.pop(0))


class FakeClient:
    def __init__(self, scripted_responses):
        self.chat = type(
            "Chat", (), {"completions": FakeCompletions(scripted_responses)}
        )()


def tool_call_query_room(call_id: str, room_name: str) -> FakeToolCall:
    return FakeToolCall(call_id, "query_room", json.dumps({"room_name": room_name}, ensure_ascii=False))


def check(name: str, condition: bool) -> None:
    print(f"{name}：{'PASS' if condition else 'FAIL'}")


# --------------------------------------------------------------------------
# 一、安全边界测试：call_1 ~ call_7
# --------------------------------------------------------------------------
print("== 工具安全边界测试 ==")

call_counter = {"count": 0}
real_query_room = TOOL_REGISTRY["query_room"]


def counting_query_room(room_name: str) -> dict:
    call_counter["count"] += 1
    return real_query_room(room_name)


TOOL_REGISTRY["query_room"] = counting_query_room

# call_1：合法名称，应执行工具并查询成功
result_1 = execute_tool_call(tool_call_query_room("call_1", "星河会议室"))
print("call_1 成功查询：", result_1)
check("call_1 查询星河会议室", result_1.get("ok") is True and result_1.get("capacity") == 12)

# call_2：合法格式但会议室不存在，属业务失败
result_2 = execute_tool_call(tool_call_query_room("call_2", "海底会议室"))
print("call_2 房间不存在：", result_2)
check("call_2 返回 room_not_found", result_2 == {"ok": False, "error": "room_not_found"})

# call_3：白名单之外的工具，直接拒绝
result_3 = execute_tool_call(FakeToolCall("call_3", "delete_room", '{"room_name": "星河会议室"}'))
print("call_3 未知工具：", result_3)
check("call_3 返回 tool_not_allowed", result_3 == {"ok": False, "error": "tool_not_allowed"})

# call_4：参数不是合法 JSON
result_4 = execute_tool_call(FakeToolCall("call_4", "query_room", '{"room_name": 星河}'))
print("call_4 非法 JSON：", result_4)
check("call_4 返回 invalid_json", result_4 == {"ok": False, "error": "invalid_json"})

# call_5：room_name 类型错误
result_5 = execute_tool_call(FakeToolCall("call_5", "query_room", '{"room_name": 123}'))
print("call_5 名称类型错误：", result_5)
check("call_5 返回 invalid_room_name", result_5 == {"ok": False, "error": "invalid_room_name"})

# call_6：缺少必需字段
result_6 = execute_tool_call(FakeToolCall("call_6", "query_room", '{"room": "星河会议室"}'))
print("call_6 缺少必需字段：", result_6)
check("call_6 返回 invalid_arguments", result_6 == {"ok": False, "error": "invalid_arguments"})

# call_7：工具执行阶段发生异常，返回稳定错误码
def broken_query_room(room_name: str) -> dict:
    raise RuntimeError("数据源断开")


TOOL_REGISTRY["query_room"] = broken_query_room
result_7 = execute_tool_call(tool_call_query_room("call_7", "星河会议室"))
print("call_7 工具执行异常：", result_7)
check("call_7 返回 tool_failed", result_7 == {"ok": False, "error": "tool_failed"})

# 校验失败时不得执行真正的工具函数：只有 call_1（成功查询）和
# call_2（房间不存在，属合法业务查询）真正执行过，共 2 次
check(
    "非法请求未进入工具函数（仅 call_1、call_2 执行）",
    call_counter["count"] == 2,
)
TOOL_REGISTRY["query_room"] = real_query_room

# --------------------------------------------------------------------------
# 二、消息顺序与调用编号测试
# --------------------------------------------------------------------------
print()
print("== 消息闭环测试 ==")

final_answer = "星河会议室位于 B座2层 B201，最多容纳 12 人。"
scripted = [
    # 第 1 轮：模型提出工具调用
    FakeMessage(
        content=None,
        tool_calls=[tool_call_query_room("call_loop_1", "星河会议室")],
    ),
    # 第 2 轮：模型根据工具结果给出最终回答
    FakeMessage(content=final_answer, tool_calls=None),
]
client = FakeClient(scripted)
answer = run_room_assistant(client, "fake-model", "星河会议室在哪里？")

round1_messages = client.chat.completions.recorded_requests[0]
round2_messages = client.chat.completions.recorded_requests[1]
roles_round2 = [message["role"] for message in round2_messages]

assistant_index = roles_round2.index("assistant")
tool_index = roles_round2.index("tool")
tool_message = round2_messages[tool_index]
assistant_call = round2_messages[assistant_index]["tool_calls"][0]

check("消息顺序与调用编号测试", (
    roles_round2 == ["system", "user", "assistant", "tool", "assistant"]
    and assistant_index < tool_index
    and assistant_call["id"] == "call_loop_1"
    and tool_message["tool_call_id"] == "call_loop_1"
    and tool_message["content"] == json.dumps(
        {"ok": True, "room_name": "星河会议室", "location": "B座2层 B201", "capacity": 12},
        ensure_ascii=False,
    )
    and answer == final_answer
))

# --------------------------------------------------------------------------
# 三、空回答测试
# --------------------------------------------------------------------------
empty_client = FakeClient([FakeMessage(content=None, tool_calls=None)])
empty_ok = False
try:
    run_room_assistant(empty_client, "fake-model", "星河会议室在哪里？")
except RuntimeError as error:
    empty_ok = "工具调用或最终回答" in str(error)
check("空回答测试", empty_ok)

# --------------------------------------------------------------------------
# 四、轮数上限测试
# --------------------------------------------------------------------------
always_call = [
    FakeMessage(
        content=None,
        tool_calls=[tool_call_query_room(f"call_loop_{number}", "星河会议室")],
    )
    for number in range(1, MAX_ROUNDS + 1)
]
loop_client = FakeClient(always_call)
limit_ok = False
try:
    run_room_assistant(loop_client, "fake-model", "星河会议室在哪里？")
except RuntimeError as error:
    limit_ok = "轮数超过上限" in str(error)
check("轮数上限测试", limit_ok)

# --------------------------------------------------------------------------
# 五、两个分支的行为示例（离线假模型）
# --------------------------------------------------------------------------
print()
tool_branch_client = FakeClient(
    [
        FakeMessage(
            content=None,
            tool_calls=[tool_call_query_room("call_demo_1", "星河会议室")],
        ),
        FakeMessage(content=final_answer, tool_calls=None),
    ]
)
print("需要工具：", run_room_assistant(tool_branch_client, "fake-model", "星河会议室在哪里？"))

direct_client = FakeClient(
    [
        FakeMessage(
            content="会议室是供多人讨论、协作或远程沟通使用的空间。",
            tool_calls=None,
        )
    ]
)
print(
    "无需工具：",
    run_room_assistant(direct_client, "fake-model", "什么是会议室？"),
)

import json
from tools import query_room, ROOM_TOOL
from tool_call import assistant_message

TOOL_REGISTRY = {
    'query_room': query_room
}

def execute_tool_call(tool_call) -> dict:
    # 1. 检查工具是否在白名单中
    tool_name = tool_call.function.name
    tool_function = TOOL_REGISTRY.get(tool_name)
    if tool_function is None:
        return {"ok": False, "error": "tool_not_allowed"}

    # 2. 把 JSON 参数字符串解析成 Python 数据
    try:
        arguments = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "invalid_json"}

    # 3. 检查必需字段和额外字段
    if not isinstance(arguments, dict) or set(arguments) != {"room_name"}:
        return {"ok": False, "error": "invalid_arguments"}

    # 4. 检查参数类型和业务规则
    room_name = arguments["room_name"]
    if not isinstance(room_name, str):
        return {"ok": False, "error": "invalid_room_name"}

    room_name = room_name.strip()
    if not room_name or len(room_name) > 20:
        return {"ok": False, "error": "invalid_room_name"}

    # 5. 只有全部校验通过后，才执行真正的 Python 函数
    try:
        return tool_function(room_name=room_name)
    except Exception:
        return {"ok": False, "error": "tool_failed"}


tool_call = assistant_message.tool_calls[0]
result = execute_tool_call(tool_call)
print(result)

































import json
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOMS = {
    "星河会议室": {"location": "B座2层 B201", "capacity": 12},
    "远航会议室": {"location": "A座3层 A301", "capacity": 20},
    "晨曦会议室": {"location": "C座1层 C101", "capacity": 6},
}


# ==================== 工具函数 ====================

def query_room(room_name: str) -> dict:
    """按名称查询会议室位置和容量。"""
    room = ROOMS[room_name]
    if room is None:
        return {
            'ok': False,
            'error': 'room_not_found'
        }
    return {
        'ok': True,
        'room_name': room_name, **room
    }


def list_rooms(min_capacity: int) -> dict:
    """按最少容纳人数筛选会议室。"""
    matches = [
        {'room_name': name, **room}
        for name, room in ROOMS.items()
        if room['capacity'] >= min_capacity
    ]
    return {
        'ok': True,
        'rooms': matches
    }


# ==================== Pydantic 参数模型 ====================

class ToolArgsModel(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        strict=True,
        str_strip_whitespace=True,
        str_min_length=1
    )

class QueryRoomArgs(ToolArgsModel):
    room_name: str = Field(description='要查询的完整会议室名称')

class ListRoomsArgs(ToolArgsModel):
    min_capacity: int = Field(
        ge=1, le=100, description="需要容纳的最少人数，范围 1 到 100"
    )

    
# ==================== 工具 Schema（给模型看） ====================

QUERY_ROOM_TOOL = {
    "type": "function",
    "function": {
        "name": "query_room",
        "description": "已知会议室名称时，查询它的位置和容量。",
        "strict": True,
        "parameters": QueryRoomArgs.model_json_schema(),
    },
}

LIST_ROOMS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_rooms",
        "description": "不知道具体名称时，按最少容纳人数筛选会议室。",
        "strict": True,
        "parameters": ListRoomsArgs.model_json_schema(),
    },
}

TOOL_SCHEMAS = [QUERY_ROOM_TOOL, LIST_ROOMS_TOOL]


# ==================== 工具注册表（程序白名单） ====================

TOOL_REGISTRY = {
    "query_room": {"function": query_room, "args_model": QueryRoomArgs},
    "list_rooms": {"function": list_rooms, "args_model": ListRoomsArgs},
}


# ==================== 统一校验 + 安全执行 ====================
def execute_tool_call(tool_call) -> dict:
    """安全执行一次工具调用，永远返回字典，不抛异常。"""
    tool_name = tool_call.function.name
    tool_config = TOOL_REGISTRY.get(tool_name)
    if tool_config is None:
        return {"ok": False, "error": "tool_not_allowed"}

    try:
        arguments = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "invalid_json"}

    if not isinstance(arguments, dict):
        return {"ok": False, "error": "invalid_arguments"}

    args_model = tool_config["args_model"]
    try:
        validated_args = args_model.model_validate(arguments)
    except ValidationError:
        return {"ok": False, "error": "invalid_arguments"}

    tool_function = tool_config["function"]
    try:
        return tool_function(**validated_args.model_dump())
    except Exception:
        return {"ok": False, "error": "tool_failed"}















































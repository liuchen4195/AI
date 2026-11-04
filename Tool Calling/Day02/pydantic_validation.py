import json
from tools import list_rooms, query_room
from pydantic import BaseModel, ConfigDict, Field, ValidationError

class ToolArgsModel(BaseModel):
    model_config = ConfigDict(
        # 拒绝模型生成的未定义参数
        extra="forbid",
        # 不自动把字符串数字转换成整数
        strict=True,
        # 清除字符串首尾空白，并拒绝空字符串
        str_strip_whitespace=True,
        str_min_length=1,
    )


class QueryRoomArgs(ToolArgsModel):
    """query_room 只需要一个非空会议室名称。"""

    room_name: str = Field(
        description="要查询的完整会议室名称",
    )


class ListRoomsArgs(ToolArgsModel):
    """list_rooms 需要一个 1～100 之间的严格整数。"""

    min_capacity: int = Field(
        ge=1,
        le=100,
        description="需要容纳的最少人数，范围为 1 到 100",
    )


# 为 query_room 生成给模型阅读的工具说明
QUERY_ROOM_TOOL = {
    "type": "function",
    "function": {
        "name": "query_room",
        "description": "已知会议室名称时，查询它的位置和容量。",
        "strict": True,
        # 直接从 Pydantic 参数模型生成 JSON Schema
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

# 模型通过这个列表了解本轮可以选择哪些工具
TOOL_SCHEMAS = [QUERY_ROOM_TOOL, LIST_ROOMS_TOOL]

#找到白名单函数和对应的 Pydantic 参数模型
TOOL_REGISTRY = {
    "query_room": {
        # 真正执行的本地 Python 函数
        "function": query_room,
        # 执行前用于校验模型参数的 Pydantic 模型
        "args_model": QueryRoomArgs,
    },
    "list_rooms": {
        "function": list_rooms,
        "args_model": ListRoomsArgs,
    },
}


def execute_tool_call(tool_call) -> dict:
    # 第一步：读取工具名称，并在白名单注册表中查找
    tool_name = tool_call.function.name
    tool_config = TOOL_REGISTRY.get(tool_name)
    if tool_config is None:
        return {"ok": False, "error": "tool_not_allowed"}

    # 第二步：把模型返回的参数 JSON 字符串解析成字典
    try:
        arguments = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "invalid_json"}

    # 第三步：使用当前工具对应的 Pydantic 模型校验参数
    args_model = tool_config["args_model"]
    try:
        # Pydantic 模型实例（参数已校验）
        validated_args = args_model.model_validate(arguments)
    except ValidationError:
        return {"ok": False, "error": "invalid_arguments"}

    # 第四步：只把校验后的参数传给白名单函数
    tool_function = tool_config["function"]
    try:
        # .model_dump()转成字典
        return tool_function(**validated_args.model_dump())
    except Exception:
        return {"ok": False, "error": "tool_failed"}








































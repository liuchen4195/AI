import json
from datetime import datetime


ROOMS = {
    "晨曦会议室": {"location": "A座1层 A101", "capacity": 6},
    "星河会议室": {"location": "B座2层 B201", "capacity": 12},
    "远航会议室": {"location": "B座3层 B301", "capacity": 20},
}

# 会议室名称的业务长度上限，与 Schema 中的 enum 保持一致
MAX_ROOM_NAME_LENGTH = 20

# list_rooms 的容量范围，与 Schema 中的 minimum / maximum 保持一致
MIN_CAPACITY = 1
MAX_CAPACITY = 100


"""===========================工具函数（均为只读，不修改任何外部状态）========================="""

# 统一工具成功和失败时的返回格式
def query_room(room_name: str) -> dict:
    """查询固定会议室的位置和容量，只读，不创建预约。"""
    room = ROOMS.get(room_name)
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
    """列出容量不小于 min_capacity 的会议室；没有符合条件时返回空列表。"""
    rooms = [
        {
            'room_name': name, 'location': room['location'],
            'capacity': room['capacity']
        }
        for name, room in ROOMS.items()
        if room['capacity'] >= min_capacity
    ]
    # 按容量升序、名称升序排列，保证同样输入每次结果一致
    rooms.sort(key=lambda item: (item['capacity'], item['room_name']))
    # 即使没有匹配项，也返回成功状态和空列表
    return {'ok': True, 'rooms': rooms}


def get_local_time() -> dict:
    """读取运行本程序的电脑当前本地时间；纯标准库，不访问网络。"""
    now = datetime.now().astimezone()
    return {
        'ok': True,
        'local_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        'timezone': now.strftime('%z') or '本地时区',
    }


"""========================工具合同：名称、描述、参数 Schema、额外字段限制======================"""

#用参数 Schema 告诉模型怎样调用
QUERY_ROOM_TOOL = {
    #声明这是一个函数类工具
    "type": "function",
    "function": {
        #模型提出调用时使用的工具名称
        "name": "query_room",
        #说明工具的用途和能力边界
        "description": "查询固定会议室的位置和容量；只读，不创建预约。",
        #要求模型生成的参数严格符合 Schema
        "strict": True,
        #描述工具的全部输入参数
        "parameters": {
            "type": "object",
            #定义每个参数的名称、类型和说明
            "properties": {
                "room_name": {
                    "type": "string",
                    #限制参数可以使用的值
                    "enum": ["晨曦会议室", "星河会议室", "远航会议室"],
                    "description": "需要查询的完整会议室名称",
                }
            },
            #指定必须提供的参数
            "required": ["room_name"],
            #禁止增加未定义参数
            "additionalProperties": False,
        },
    },
}


LIST_ROOMS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_rooms",
        "description": "按最小容量筛选会议室，返回会议室名称、位置和容量；只读。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "min_capacity": {
                    "type": "integer",
                    "minimum": MIN_CAPACITY,
                    "maximum": MAX_CAPACITY,
                    "description": "所需的最小容纳人数，1 到 100 之间的整数",
                }
            },
            "required": ["min_capacity"],
            "additionalProperties": False,
        },
    },
}


TIME_TOOL = {
    "type": "function",
    "function": {
        "name": "get_local_time",
        "description": "读取运行本程序的电脑当前本地时间；只读，不需要参数。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}


"""==========================参数校验：字段 → 类型 → 业务范围======================="""

def validate_room_arguments(arguments: dict):
    """校验 query_room 的参数，通过则返回干净的关键字参数。"""
    if set(arguments) != {'room_name'}:
        return None, 'invalid_arguments'

    room_name = arguments['room_name']
    if not isinstance(room_name, str):
        return None, 'invalid_room_name'

    room_name = room_name.strip()
    if not room_name or len(room_name) > MAX_ROOM_NAME_LENGTH:
        return None, 'invalid_room_name'

    # 全部检查通过：返回干净的关键字参数，第二个值必须是 None
    return {"room_name": room_name}, None


def validate_list_rooms_arguments(arguments: dict):
    """校验 list_rooms 的参数：必须只有 min_capacity，且是 1~100 的整数。"""
    if set(arguments) != {"min_capacity"}:
        return None, "invalid_arguments"

    min_capacity = arguments["min_capacity"]
    # bool 是 int 的子类，True 会被当成 1，必须单独排除
    if isinstance(min_capacity, bool) or not isinstance(min_capacity, int):
        return None, "invalid_min_capacity"
    if not MIN_CAPACITY <= min_capacity <= MAX_CAPACITY:
        return None, "invalid_min_capacity"

    return {"min_capacity": min_capacity}, None


def validate_time_arguments(arguments: dict):
    """get_local_time 不接受任何参数。"""
    if arguments:
        return None, "invalid_arguments"
    return {}, None
























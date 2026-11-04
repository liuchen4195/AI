import requests
from model import CityPOS, CityQuality, CityWeather, RoomInfo
import aiohttp
import json
from pathlib import Path

# 会议室数据文件路径（与 history.json 相同约定：从 Day03 目录运行）
MEETING_ROOMS_PATH = Path("data/meeting_rooms.json")


# 查询城市经纬度, async def: 定义异步函数
async def get_city_pos(city_name:str):
    # 创建 HTTP 会话
    async with aiohttp.ClientSession() as session:
        # async with：退出时自动关闭 session
        async with session.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=5&language=zh&countryCode=CN") as response:
            # 异步读响应体并解析 json
            res = await response.json()
            # if res.status != 200:
            #     return {
            #     "status": "error",
            #     "message": "城市经纬度查询失败，请稍后重试！",
            # }
            return {
                "status" : "success",
                "message": "查询成功",
                "data": res
            }


# 查询城市天气
async def get_weather(latitude:str, longitude:str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,wind_speed_10m&hourly=temperature_2m") as response:
            res = await response.json()
            return {
                "status": "success",
                "message": "查询成功",
                "data": res
            }


#查询城市空气质量
async def get_quality(latitude:str, longitude:str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={latitude}&longitude={longitude}&current=european_aqi,pm10,pm2_5,nitrogen_dioxide,ozone&timezone=Asia/Shanghai") as response:
            res = await response.json()
            return {
                "status": "success",
                "message": "查询成功",
                "data": res
            }


# 读取会议室数据文件（容错：文件不存在或损坏时返回空列表）
def load_meeting_rooms():
    try:
        rooms = json.loads(MEETING_ROOMS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return rooms if isinstance(rooms, list) else []


# 查询会议室信息（地址、人数等），数据来自本地 JSON 文件
async def get_room_info(room_name:str):
    rooms = load_meeting_rooms()
    if not rooms:
        return {
            "status": "error",
            "message": "会议室数据读取失败，请稍后重试！",
            "data": None,
        }

    # 先按名称精确匹配，再按名称包含关系模糊匹配
    for room in rooms:
        if room.get("name") == room_name:
            return {
                "status": "success",
                "message": "查询成功",
                "data": room,
            }

    matched = [room for room in rooms if room_name in str(room.get("name", ""))]
    if matched:
        return {
            "status": "success",
            "message": "查询成功",
            "data": matched,
        }

    return {
        "status": "error",
        "message": f"未找到会议室「{room_name}」，请确认名称后重试！",
        "data": None,
    }


# 可以调用的所有工具列表
tools_map = {
    "get_city_pos": {
        "function": get_city_pos,
        "args": CityPOS
    },
    "get_weather": {
        "function": get_weather,
        "args": CityWeather
    },
    "get_quality": {
        "function": get_quality,
        "args": CityQuality
    },
    "get_room_info": {
        "function": get_room_info,
        "args": RoomInfo
    },
}



































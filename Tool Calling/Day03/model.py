from pydantic import BaseModel, Field


# 工具参数模型
class CityPOS(BaseModel):
    """根据城市名称查询经纬度"""
    city_name: str = Field(description="要搜索的城市名称")

class CityWeather(BaseModel):
    """使用经纬度查询当前天气"""
    latitude: str = Field(description="城市纬度")
    longitude: str = Field(description="城市经度")

class CityQuality(BaseModel):
    """使用相同经纬度查询当前空气质量"""
    latitude: str = Field(description="城市纬度")
    longitude: str = Field(description="城市经度")

class RoomInfo(BaseModel):
    """根据会议室名称查询地址、人数等信息"""
    room_name: str = Field(description="要查询的会议室名称")


#工具合同
city_tool = {
    "type": "function",
    "function": {
        "name": "get_city_pos",
        "description": "根据城市名称查询经纬度时调用此工具",
        "strict": True,
        "parameters": CityPOS.model_json_schema(),
    },
}

weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "根据经纬度查询城市天气时调用此工具",
        "strict": True,
        "parameters": CityWeather.model_json_schema(),
    },
}

quality_tool = {
    "type": "function",
    "function": {
        "name": "get_quality",
        "description": "根据经纬度查询城市空气质量时调用此工具",
        "strict": True,
        "parameters": CityQuality.model_json_schema(),
    },
}

room_tool = {
    "type": "function",
    "function": {
        "name": "get_room_info",
        "description": "根据会议室名称查询地址、人数等信息时调用此工具",
        "strict": True,
        "parameters": RoomInfo.model_json_schema(),
    },
}

# 给模型传递的工具列表
TOOLS = [city_tool, weather_tool, quality_tool, room_tool]























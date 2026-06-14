"""
高德地图 MCP Server
通过 stdio 传输，提供以下工具：
  - search_poi         关键词搜索 POI
  - search_attractions 搜索景点
  - search_food        搜索美食
  - search_hotels      搜索酒店
  - get_weather        查询天气
  - geocode            地址→经纬度
  - get_district       行政区划查询

启动方式（由 MCP Client 自动管理）：
  python backend/mcp_servers/amap_server.py
"""
import json
import os
import sys
import asyncio
from typing import Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server

# ===== 高德 API 封装（内联，不依赖 backend.amap_service） =====

AMAP_BASE_URL = "https://restapi.amap.com/v3"

# 城市→adcode 缓存
ADCODE_CACHE = {
    "北京":"110000","北京市":"110000","上海":"310000","上海市":"310000",
    "广州":"440100","广州市":"440100","深圳":"440300","深圳市":"440300",
    "杭州":"330100","杭州市":"330100","成都":"510100","成都市":"510100",
    "重庆":"500000","重庆市":"500000","南京":"320100","南京市":"320100",
    "武汉":"420100","武汉市":"420100","西安":"610100","西安市":"610100",
    "苏州":"320500","苏州市":"320500","长沙":"430100","长沙市":"430100",
    "厦门":"350200","厦门市":"350200","三亚":"460200","三亚市":"460200",
    "大理":"532901","大理市":"532901","丽江":"530702","丽江市":"530702",
}


def get_api_key() -> str:
    """从环境变量获取高德 API Key"""
    key = os.getenv("AMAP_API_KEY", "")
    if not key:
        raise RuntimeError("AMAP_API_KEY 环境变量未设置")
    return key


async def amap_request(path: str, params: dict) -> dict:
    """统一的高德 API 请求"""
    params["key"] = get_api_key()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{AMAP_BASE_URL}{path}", params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            raise RuntimeError(f"高德API错误: {data.get('info', '未知')}")
        return data


async def city_to_adcode(city: str) -> str:
    """城市名→adcode"""
    for k, v in ADCODE_CACHE.items():
        if city in k or k in city:
            return v
    # 调 API
    try:
        data = await amap_request("/config/district", {"keywords": city, "subdistrict": 0})
        districts = data.get("districts", [])
        if districts:
            return districts[0].get("adcode", city)
    except Exception:
        pass
    return city


# ===== MCP Server =====

server = Server("amap-server")


@server.tool()
async def search_poi(
    keywords: str,
    city: str,
    poi_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
) -> str:
    """
    搜索指定城市的 POI（兴趣点）。

    Args:
        keywords: 搜索关键词，如「故宫」「火锅」「酒店」
        city: 城市名称，如「北京」「杭州」
        poi_type: POI类型代码，如「风景名胜」「餐饮」，不传则搜索全部类型
        limit: 返回数量，默认10，最大50
        offset: 分页偏移量

    Returns:
        JSON字符串，包含 total（总数）和 pois（POI列表）
    """
    params = {
        "keywords": keywords,
        "city": city,
        "offset": min(limit, 50),
        "page": offset // limit + 1 if limit else 1,
        "extensions": "all",
        "citylimit": "true",
    }
    if poi_type:
        params["types"] = poi_type

    data = await amap_request("/place/text", params)
    pois = []
    for p in data.get("pois", []):
        pois.append({
            "id": p.get("id", ""),
            "name": p.get("name", ""),
            "address": p.get("address", ""),
            "location": p.get("location", ""),
            "type": p.get("typecode", ""),
            "distance": p.get("distance", ""),
            "tel": p.get("tel", ""),
        })
    return json.dumps({"total": int(data.get("count", 0)), "pois": pois}, ensure_ascii=False)


@server.tool()
async def search_attractions(city: str, keywords: str = "景点", limit: int = 15) -> str:
    """
    搜索城市的景点。

    Args:
        city: 城市名称
        keywords: 搜索关键词，默认「景点」
        limit: 返回数量，默认15

    Returns:
        JSON字符串，包含景点列表
    """
    return await search_poi(
        keywords=keywords, city=city,
        poi_type="风景名胜|公园|博物馆|展览馆|纪念馆|古迹",
        limit=limit,
    )


@server.tool()
async def search_food(city: str, keywords: str = "美食", limit: int = 10) -> str:
    """
    搜索城市的美食/餐饮。

    Args:
        city: 城市名称
        keywords: 搜索关键词，默认「美食」
        limit: 返回数量，默认10

    Returns:
        JSON字符串，包含餐厅列表
    """
    return await search_poi(
        keywords=keywords, city=city,
        poi_type="餐饮|中餐厅|火锅|小吃|咖啡厅",
        limit=limit,
    )


@server.tool()
async def search_hotels(city: str, limit: int = 10) -> str:
    """
    搜索城市的酒店/住宿。

    Args:
        city: 城市名称
        limit: 返回数量，默认10

    Returns:
        JSON字符串，包含酒店列表
    """
    return await search_poi(
        keywords="酒店", city=city,
        poi_type="酒店|宾馆|青年旅社|民宿",
        limit=limit,
    )


@server.tool()
async def get_weather(city: str) -> str:
    """
    查询城市的实时天气和未来预报。

    Args:
        city: 城市名称

    Returns:
        JSON字符串，包含 live（实时天气）和 forecasts（预报）
    """
    adcode = await city_to_adcode(city)
    data = await amap_request("/weather/weatherInfo", {
        "city": adcode, "extensions": "all",
    })
    lives = data.get("lives", [])
    forecasts = data.get("forecasts", [])
    result = {
        "city": city,
        "live": None,
        "forecasts": [],
    }
    if lives:
        w = lives[0]
        result["live"] = {
            "weather": w.get("weather", ""),
            "temperature": w.get("temperature", ""),
            "winddirection": w.get("winddirection", ""),
            "windpower": w.get("windpower", ""),
            "humidity": w.get("humidity", ""),
        }
    if forecasts:
        for fc in forecasts[0].get("casts", []):
            result["forecasts"].append({
                "date": fc.get("date", ""),
                "week": fc.get("week", ""),
                "dayweather": fc.get("dayweather", ""),
                "nightweather": fc.get("nightweather", ""),
                "daytemp": fc.get("daytemp", ""),
                "nighttemp": fc.get("nighttemp", ""),
            })
    return json.dumps(result, ensure_ascii=False)


@server.tool()
async def geocode(address: str, city: Optional[str] = None) -> str:
    """
    将地址转换为经纬度坐标。

    Args:
        address: 地址，如「北京市朝阳区天安门」
        city: 可选的城市限定

    Returns:
        JSON字符串，包含经纬度
    """
    params = {"address": address}
    if city:
        params["city"] = city
    data = await amap_request("/geocode/geo", params)
    geocodes = data.get("geocodes", [])
    if geocodes:
        loc = geocodes[0].get("location", "0,0")
        lng, lat = loc.split(",")
        return json.dumps({"lng": float(lng), "lat": float(lat), "address": geocodes[0].get("formatted_address", "")}, ensure_ascii=False)
    return json.dumps({"lng": 0, "lat": 0})


@server.tool()
async def get_district(city: str) -> str:
    """
    查询城市行政区划信息。

    Args:
        city: 城市名称

    Returns:
        JSON字符串，包含行政区划
    """
    data = await amap_request("/config/district", {"keywords": city, "subdistrict": 0})
    return json.dumps(data.get("districts", []), ensure_ascii=False)


# ===== 入口 =====

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
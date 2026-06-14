"""
高德地图 API 服务层
"""
import httpx
from typing import Optional


class AmapAPIError(Exception):
    """高德 API 通用异常"""
    def __init__(self, status: str, info: str, infocode: str = ""):
        self.status = status
        self.info = info
        self.infocode = infocode
        super().__init__(f"高德API错误 [{infocode}]: {info}")


class AmapService:
    """高德地图 Web 服务封装"""

    BASE_URL = "https://restapi.amap.com/v3"

    # 常用城市 adcode 缓存
    ADCODE_CACHE = {
        "北京": "110000", "北京市": "110000",
        "上海": "310000", "上海市": "310000",
        "广州": "440100", "广州市": "440100",
        "深圳": "440300", "深圳市": "440300",
        "杭州": "330100", "杭州市": "330100",
        "成都": "510100", "成都市": "510100",
        "重庆": "500000", "重庆市": "500000",
        "南京": "320100", "南京市": "320100",
        "武汉": "420100", "武汉市": "420100",
        "西安": "610100", "西安市": "610100",
        "苏州": "320500", "苏州市": "320500",
        "长沙": "430100", "长沙市": "430100",
        "厦门": "350200", "厦门市": "350200",
        "三亚": "460200", "三亚市": "460200",
        "大理": "532901", "大理市": "532901",
        "丽江": "530702", "丽江市": "530702",
    }

    def __init__(self, api_key: str, timeout: int = 15):
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ========== 客户端管理 ==========

    async def _get_client(self) -> httpx.AsyncClient:
        """懒加载 httpx 客户端（连接复用）"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=10),
            )
        return self._client

    async def close(self):
        """释放连接池"""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ========== 内部工具 ==========

    def _check_response(self, data: dict) -> dict:
        """检查高德 API 响应状态，不合法时抛异常"""
        if data.get("status") != "1":
            raise AmapAPIError(
                status=data.get("status", "0"),
                info=data.get("info", "未知错误"),
                infocode=data.get("infocode", ""),
            )
        return data

    async def _city_to_adcode(self, city: str) -> str:
        """城市名 → adcode（天气 API 需要）"""
        for key, value in self.ADCODE_CACHE.items():
            if city in key or key in city:
                return value
        # 缓存未命中则调行政区划 API
        try:
            data = await self.get_district(city)
            districts = data.get("districts", [])
            if districts:
                return districts[0].get("adcode", city)
        except Exception:
            pass
        return city

    # ========== POI 搜索 ==========

    async def search_poi(
        self,
        keywords: str,
        city: str,
        poi_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict:
        """
        关键词搜索 POI
        API: POST /v3/place/text
        """
        params = {
            "key": self.api_key,
            "keywords": keywords,
            "city": city,
            "offset": limit,
            "page": offset // limit + 1 if limit else 1,
            "extensions": "all",
            "citylimit": "true",
        }
        if poi_type:
            params["types"] = poi_type

        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}/place/text", params=params)
        resp.raise_for_status()
        return self._check_response(resp.json())

    async def search_attractions(
        self, city: str, keywords: str = "景点", limit: int = 15
    ) -> dict:
        """搜索景点（快捷方法）"""
        return await self.search_poi(
            keywords=keywords, city=city,
            poi_type="风景名胜|公园|博物馆|展览馆|纪念馆|古迹",
            limit=limit,
        )

    async def search_food(
        self, city: str, keywords: str = "美食", limit: int = 10
    ) -> dict:
        """搜索餐饮（快捷方法）"""
        return await self.search_poi(
            keywords=keywords, city=city,
            poi_type="餐饮|中餐厅|火锅|小吃|咖啡厅",
            limit=limit,
        )

    async def search_hotels(self, city: str, limit: int = 10) -> dict:
        """搜索酒店（快捷方法）"""
        return await self.search_poi(
            keywords="酒店", city=city,
            poi_type="酒店|宾馆|青年旅社|民宿",
            limit=limit,
        )

    # ========== 天气查询 ==========

    async def get_weather(self, city: str, extensions: str = "all") -> dict:
        """
        查询天气
        API: GET /v3/weather/weatherInfo
        """
        adcode = await self._city_to_adcode(city)
        params = {
            "key": self.api_key,
            "city": adcode,
            "extensions": extensions,
        }
        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}/weather/weatherInfo", params=params)
        resp.raise_for_status()
        return self._check_response(resp.json())

    # ========== 地理编码 ==========

    async def geocode(self, address: str, city: Optional[str] = None) -> dict:
        """地址 → 经纬度"""
        params = {"key": self.api_key, "address": address}
        if city:
            params["city"] = city
        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}/geocode/geo", params=params)
        resp.raise_for_status()
        return self._check_response(resp.json())

    async def reverse_geocode(self, lng: float, lat: float) -> dict:
        """经纬度 → 地址"""
        params = {
            "key": self.api_key,
            "location": f"{lng},{lat}",
            "extensions": "base",
        }
        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}/geocode/regeo", params=params)
        resp.raise_for_status()
        return self._check_response(resp.json())

    # ========== 行政区划 ==========

    async def get_district(self, city: str) -> dict:
        """获取行政区划信息"""
        params = {"key": self.api_key, "keywords": city, "subdistrict": 0}
        client = await self._get_client()
        resp = await client.get(f"{self.BASE_URL}/config/district", params=params)
        resp.raise_for_status()
        return self._check_response(resp.json())
        # ========== Phase 5: 路径规划 ==========

    async def direction_walking(self, origin: str, destination: str) -> dict:
        """
        步行路径规划
        origin/destination: "lng,lat" 格式字符串
        """
        return await self._request("GET", "/direction/walking", {
            "key": self.api_key,
            "origin": origin,
            "destination": destination,
        })

    async def direction_driving(self, origin: str, destination: str) -> dict:
        """驾车路径规划"""
        return await self._request("GET", "/direction/driving", {
            "key": self.api_key,
            "origin": origin,
            "destination": destination,
            "strategy": "0",  # 速度优先
        })

    async def direction_transit(self, origin: str, destination: str, city: str) -> dict:
        """公交路径规划"""
        return await self._request("GET", "/direction/transit/integrated", {
            "key": self.api_key,
            "origin": origin,
            "destination": destination,
            "city": city,
        })

    async def get_route_between(self, from_lng: float, from_lat: float,
                                 to_lng: float, to_lat: float,
                                 mode: str = "walking", city: str = "") -> dict:
        """
        计算两点间路径（统一入口）

        Returns:
            {"distance": 1234, "duration": 900, "mode": "walking"}
            distance: 米, duration: 秒
        """
        origin = f"{from_lng},{from_lat}"
        destination = f"{to_lng},{to_lat}"

        try:
            if mode == "walking":
                data = await self.direction_walking(origin, destination)
            elif mode == "driving":
                data = await self.direction_driving(origin, destination)
            elif mode == "transit":
                data = await self.direction_transit(origin, destination, city)
            else:
                data = await self.direction_walking(origin, destination)

            # 提取距离和时间
            route = (data.get("route") or {})
            paths = route.get("paths", [])
            if paths:
                return {
                    "distance": int(paths[0].get("distance", 0)),    # 米
                    "duration": int(paths[0].get("duration", 0)),    # 秒
                    "mode": mode,
                }
        except AmapAPIError:
            pass

        # 失败时用直线距离估算
        import math
        dx = (to_lng - from_lng) * 111000 * math.cos(math.radians((from_lat + to_lat) / 2))
        dy = (to_lat - from_lat) * 111000
        est_dist = int(math.sqrt(dx ** 2 + dy ** 2))
        return {"distance": est_dist, "duration": est_dist // 80 * 60, "mode": "estimated"}
from .config import get_settings
_amap_service_instance = None
async def get_amap_service():
    """
    FastAPI 依赖注入工厂函数
    用法:
        @router.get("/xxx")
        async def endpoint(amap = Depends(get_amap_service)):
            ...
    """
    global _amap_service_instance
    if _amap_service_instance is None:
        settings = get_settings()
        _amap_service_instance = AmapService(api_key=settings.amap_web_api_key)
    return _amap_service_instance
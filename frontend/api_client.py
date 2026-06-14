"""
前端 API 调用封装
统一管理后端请求，处理错误
"""
import httpx
from typing import Optional

BACKEND_URL = "http://localhost:8000"


class APIClient:
    """后端 API 客户端"""

    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = base_url
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=20.0)
        return self._client

    def search_poi(
        self,
        keywords: str,
        city: str,
        poi_type: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        """搜索 POI"""
        response = self.client.post(
            f"{self.base_url}/api/poi/search",
            json={
                "keywords": keywords,
                "city": city,
                "poi_type": poi_type,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_weather(self, city: str) -> dict:
        """查询天气"""
        response = self.client.get(
            f"{self.base_url}/api/weather/now",
            params={"city": city},
        )
        response.raise_for_status()
        return response.json()

    def health_check(self) -> dict:
        """健康检查"""
        response = self.client.get(f"{self.base_url}/api/health")
        response.raise_for_status()
        return response.json()


# 全局实例
api = APIClient()
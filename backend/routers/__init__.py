"""
路由聚合模块
将所有子路由收集到统一的 APIRouter 中，
main.py 只需 include 这一个 router
"""
from fastapi import APIRouter

from .poi import router as poi_router
from .weather import router as weather_router

# 创建统一的根路由
# prefix 留空，由各子路由自行定义 prefix
api_router = APIRouter()

# 将子路由挂载到统一路由上
api_router.include_router(poi_router)
api_router.include_router(weather_router)

__all__ = ["api_router"]
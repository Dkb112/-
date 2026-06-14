"""
FastAPI 依赖注入
解决全局实例和热重载冲突问题
"""
from .amap_service import AmapService
from .config import get_settings


# 全局单例（惰性初始化）
_amap_service_instance: AmapService | None = None


async def get_amap_service()-> AmapService:
    """
    获取高德地图服务实例(FastAPI Depends)

    用法:
        @router.get("/xxx")
        async def endpoint(amap: AmapService = Depends(get_amap_service)):
            ...
    """
    global _amap_service_instance
    if _amap_service_instance is None:
        _amap_service_instance = AmapService(api_key=get_settings().amap_web_api_key)
    return _amap_service_instance
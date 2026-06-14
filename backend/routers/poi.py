"""
POI 搜索路由
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from ..amap_service import AmapService, AmapAPIError, get_amap_service
from ..schemas import (
    POISearchRequest,
    POISearchResponse,
    POIItem,
    POILocation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/poi", tags=["POI搜索"])


def _safe_int(value, default=None):
    """安全转换为 int：处理 None、空列表、空字符串、浮点数"""
    if value is None:
        return default
    if isinstance(value, list):
        # 高德偶尔返回 "distance": []
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=None):
    """安全转换为 float"""
    if value is None:
        return default
    if isinstance(value, list):
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_str(value, default=""):
    """安全转换为 str：处理 None、数字、列表"""
    if value is None:
        return default
    if isinstance(value, list):
        return default
    return str(value)


def _parse_poi_list(pois_raw) -> list[POIItem]:
    """
    将高德原始 POI 数据转为 Pydantic 模型列表
    对所有字段做防御性类型转换，避免高德返回异常数据时崩溃
    """
    result = []
    if not pois_raw:
        return result

    for idx, p in enumerate(pois_raw):
        try:
            # ---- location ----
            loc_str = _safe_str(p.get("location"), "0,0")
            lng, lat = 0.0, 0.0
            if "," in loc_str:
                parts = loc_str.split(",")
                try:
                    lng = float(parts[0])
                    lat = float(parts[1])
                except (ValueError, IndexError):
                    pass

            # ---- biz_ext → rating ----
            rating = None
            biz_ext = p.get("biz_ext")
            if isinstance(biz_ext, dict):
                rating = _safe_float(biz_ext.get("rating"))

            # ---- 构建 POIItem ----
            result.append(POIItem(
                id=_safe_str(p.get("id")),
                name=_safe_str(p.get("name"), "未知地点"),
                address=_safe_str(p.get("address")),
                location=POILocation(lng=lng, lat=lat),
                poi_type=_safe_str(p.get("typecode")),
                distance=_safe_int(p.get("distance")),     # ← 修复点
                tel=_safe_str(p.get("tel")) or None,       # ← 加固
                rating=rating,
            ))
        except Exception as e:
            logger.warning(f"跳过第 {idx} 个 POI（解析失败）: {e} | 原始数据: {p.get('name', '?')}")
            continue

    return result


# ==================== 路由端点 ====================

@router.post("/search", response_model=POISearchResponse)
async def search_poi(
    request: POISearchRequest,
    amap: AmapService = Depends(get_amap_service),
):
    """关键词搜索 POI"""
    try:
        data = await amap.search_poi(
            keywords=request.keywords,
            city=request.city,
            poi_type=request.poi_type,
            limit=request.limit,
            offset=request.offset,
        )
    except AmapAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务异常: {e}")

    pois = _parse_poi_list(data.get("pois", []))

    return POISearchResponse(
        total=int(data.get("count", 0)),
        count=len(pois),
        pois=pois,
        city=request.city,
        keywords=request.keywords,
    )


@router.get("/attractions")
async def search_attractions(
    city: str = Query(..., description="城市名称"),
    keyword: str = Query(default="景点", description="搜索关键词"),
    limit: int = Query(default=15, ge=1, le=50),
    amap: AmapService = Depends(get_amap_service),
):
    """快捷搜索景点"""
    try:
        data = await amap.search_attractions(city, keyword, limit)
        pois = _parse_poi_list(data.get("pois", []))
        return {"total": int(data.get("count", 0)), "pois": [p.model_dump() for p in pois]}
    except AmapAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/food")
async def search_food(
    city: str = Query(..., description="城市名称"),
    keyword: str = Query(default="美食", description="搜索关键词"),
    limit: int = Query(default=10, ge=1, le=50),
    amap: AmapService = Depends(get_amap_service),
):
    """快捷搜索美食"""
    try:
        data = await amap.search_food(city, keyword, limit)
        pois = _parse_poi_list(data.get("pois", []))
        return {"total": int(data.get("count", 0)), "pois": [p.model_dump() for p in pois]}
    except AmapAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/hotels")
async def search_hotels(
    city: str = Query(..., description="城市名称"),
    limit: int = Query(default=10, ge=1, le=50),
    amap: AmapService = Depends(get_amap_service),
):
    """快捷搜索酒店"""
    try:
        data = await amap.search_hotels(city, limit)
        pois = _parse_poi_list(data.get("pois", []))
        return {"total": int(data.get("count", 0)), "pois": [p.model_dump() for p in pois]}
    except AmapAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    
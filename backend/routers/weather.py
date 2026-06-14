"""
天气查询路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_amap_service
from ..amap_service import AmapService, AmapAPIError
from ..schemas import WeatherResponse, WeatherLive, WeatherForecastItem

router = APIRouter(prefix="/api/weather", tags=["天气查询"])


@router.get("/now", response_model=WeatherResponse)
async def get_current_weather(
    city: str = Query(..., description="城市名称，如「北京」「杭州」"),
    amap: AmapService = Depends(get_amap_service),
):
    """查询城市实时天气 + 未来 4 天预报"""
    try:
        data = await amap.get_weather(city, extensions="all")
    except AmapAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务异常: {e}")

    # 解析实时天气
    lives = data.get("lives", [])
    live = None
    if lives:
        li = lives[0]
        live = WeatherLive(
            city=li.get("city", city),
            weather=li.get("weather", ""),
            temperature=li.get("temperature", ""),
            winddirection=li.get("winddirection", ""),
            windpower=li.get("windpower", ""),
            humidity=li.get("humidity", ""),
            reporttime=li.get("reporttime", ""),
        )

    # 解析预报
    forecasts_raw = data.get("forecasts", [])
    forecasts: list[WeatherForecastItem] = []
    if forecasts_raw:
        for fc in forecasts_raw[0].get("casts", []):
            forecasts.append(WeatherForecastItem(
                date=fc.get("date", ""),
                week=fc.get("week", ""),
                dayweather=fc.get("dayweather", ""),
                nightweather=fc.get("nightweather", ""),
                daytemp=fc.get("daytemp", ""),
                nighttemp=fc.get("nighttemp", ""),
                daywind=fc.get("daywind", ""),
                nightwind=fc.get("nightwind", ""),
            ))

    return WeatherResponse(live=live, forecasts=forecasts, city=city)
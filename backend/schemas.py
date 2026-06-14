"""
Pydantic 数据模型
定义请求/响应结构，FastAPI 自动生成 OpenAPI 文档
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ===== 请求模型 =====

class POISearchRequest(BaseModel):
    """POI 搜索请求"""
    keywords: str = Field(
        ..., min_length=1, max_length=100,
        description="搜索关键词，如「故宫」「火锅」「酒店」"
    )
    city: str = Field(
        ..., min_length=1, max_length=50,
        description="城市名称，如「北京」「杭州」"
    )
    poi_type: Optional[str] = Field(
        default=None,
        description="POI类型：风景名胜|餐饮|酒店|购物"
    )
    limit: int = Field(
        default=10, ge=1, le=50,
        description="返回结果数量"
    )
    offset: int = Field(
        default=0, ge=0,
        description="分页偏移量"
    )


class WeatherRequest(BaseModel):
    """天气查询请求"""
    city: str = Field(
        ..., min_length=1, max_length=50,
        description="城市名称"
    )
    extensions: str = Field(
        default="all",
        pattern="^(base|all)$",
        description="base=实时天气, all=预报天气"
    )


# ===== 响应模型 =====

class POILocation(BaseModel):
    """POI 坐标"""
    lng: float
    lat: float

    @classmethod
    def from_str(cls, s: str) -> "POILocation":
        """从高德返回的 'lng,lat' 字符串解析"""
        lng, lat = s.split(",")
        return cls(lng=float(lng), lat=float(lat))


class POIItem(BaseModel):
    """单个 POI 条目"""
    id: str
    name: str
    address: str
    location: POILocation
    poi_type: str = Field(default="")
    distance: Optional[int] = None
    tel: Optional[str] = None
    rating: Optional[float] = None

   


class POISearchResponse(BaseModel):
    """POI 搜索响应"""
    total: int
    count: int
    pois: list[POIItem]
    city: str
    keywords: str


class WeatherLive(BaseModel):
    """实时天气"""
    city: str
    weather: str           # 天气现象
    temperature: str       # 温度
    winddirection: str     # 风向
    windpower: str         # 风力
    humidity: str          # 湿度
    reporttime: str        # 发布时间


class WeatherForecastItem(BaseModel):
    """单日天气预报"""
    date: str
    week: str
    dayweather: str        # 白天天气
    nightweather: str      # 夜间天气
    daytemp: str           # 白天温度
    nighttemp: str         # 夜间温度
    daywind: str           # 白天风向
    nightwind: str         # 夜间风向


class WeatherResponse(BaseModel):
    """天气查询响应"""
    live: Optional[WeatherLive] = None
    forecasts: Optional[list[WeatherForecastItem]] = None
    city: str


class ErrorResponse(BaseModel):
    """统一错误响应"""
    code: int
    message: str
    detail: Optional[str] = None
class AgentEvent(BaseModel):
    """Agent 流式事件"""
    type: str    # "status" | "intent" | "tool_result" | "plan_preview" | "done" | "error"
    content: str = ""
    data: dict = {}
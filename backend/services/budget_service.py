"""
预算估算服务
根据城市等级、天数、偏好估算旅行费用
"""

# 城市等级 → 基础费用系数
CITY_TIER = {
    "北京": 1.2, "上海": 1.3, "广州": 1.1, "深圳": 1.2,
    "杭州": 1.0, "成都": 0.8, "重庆": 0.8, "南京": 1.0,
    "武汉": 0.8, "西安": 0.8, "苏州": 1.0, "长沙": 0.7,
    "厦门": 1.0, "三亚": 1.3, "大理": 0.7, "丽江": 0.8,
    "青岛": 1.0, "大连": 0.9, "桂林": 0.7, "张家界": 0.8,
    "哈尔滨": 0.8, "昆明": 0.8, "贵阳": 0.7, "拉萨": 1.2,
}
DEFAULT_TIER = 0.9

# 基础价格（元）
BASE_COSTS = {
    "hotel_per_night": 200,       # 舒适型酒店均价
    "meal_per_person": 50,        # 正餐人均
    "attraction_ticket": 60,      # 单景点门票均价
    "transport_daily": 30,        # 每日交通
    "snack_daily": 30,            # 零食/饮料
}

# 预算等级系数
BUDGET_MULTIPLIER = {
    "经济": 0.6,
    "舒适": 1.0,
    "豪华": 2.0,
}


def estimate_budget(
    city: str,
    days: int,
    budget_level: str = "舒适",
    daily_attraction_count: int = 4,
) -> dict:
    """
    估算旅行总预算

    Returns:
        {
            "total": 估算总额,
            "items": {
                "hotel": 酒店费用,
                "meals": 餐饮费用,
                "attractions": 门票费用,
                "transport": 交通费用,
                "other": 其他
            }
        }
    """
    tier = CITY_TIER.get(city, DEFAULT_TIER)
    mult = BUDGET_MULTIPLIER.get(budget_level, 1.0)

    hotel = int(BASE_COSTS["hotel_per_night"] * tier * mult * days)
    meals = int(BASE_COSTS["meal_per_person"] * tier * mult * 2 * days)  # 每日2正餐
    attractions = int(BASE_COSTS["attraction_ticket"] * tier * mult * daily_attraction_count * days)
    transport = int(BASE_COSTS["transport_daily"] * tier * mult * days)
    other = int(BASE_COSTS["snack_daily"] * tier * mult * days)

    return {
        "total": hotel + meals + attractions + transport + other,
        "items": {
            "hotel": hotel,
            "meals": meals,
            "attractions": attractions,
            "transport": transport,
            "other": other,
        }
    }
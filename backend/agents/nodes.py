"""
LangGraph 节点实现
"""
import json
import logging
import re
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage

from .prompts import (
    SYSTEM_PROMPT,
    TRIP_DAY_PROMPT,
    FINAL_SUMMARY_PROMPT,
    FEEDBACK_PROMPT,
)
from ..amap_service import AmapService, AmapAPIError

logger = logging.getLogger(__name__)


def _parse_poi_for_prompt(pois: list, max_items: int = 8) -> str:
    if not pois: return "暂无数据"
    lines = []
    for p in pois[:max_items]:
        name = p.get("name", "未知")
        addr = p.get("address", "")
        lines.append(f"- {name} 📍{addr}")
    return "\n".join(lines)


def _get_weekday(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return ["周一","周二","周三","周四","周五","周六","周日"][dt.weekday()]
    except: return ""


async def parse_intent_node(state: dict, llm, amap_service) -> dict:
    user_input = state.get("user_input", "")
    if not user_input:
        return {"error": "用户输入为空"}

    prompt = f"""从用户输入提取旅行信息，输出严格 JSON：
用户输入：{user_input}
JSON 格式：{{"city":"","days":1,"preferences":[],"transportation":"地铁","budget_level":"舒适"}}"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"): content = content[4:]
        parsed = json.loads(content.strip())
        return {
            "city": parsed.get("city", ""),
            "days": min(parsed.get("days", 1), 7),
            "preferences": parsed.get("preferences", []),
            "transportation": parsed.get("transportation", "地铁"),
            "budget_level": parsed.get("budget_level", "舒适"),
        }
    except Exception as e:
        logger.warning(f"意图解析失败: {e}, 原始输出: {content[:200] if 'content' in dir() else 'N/A'}")
        city_m = re.search(r'"city"\s*:\s*"([^"]+)"', content) if 'content' in dir() else None
        days_m = re.search(r'"days"\s*:\s*(\d+)', content) if 'content' in dir() else None
        return {
            "city": city_m.group(1) if city_m else "北京",
            "days": int(days_m.group(1)) if days_m else 2,
            "preferences": [], "transportation": "地铁", "budget_level": "舒适",
        }


async def search_pois_node(state: dict, llm, amap_service: AmapService) -> dict:
    city = state.get("city", "北京")
    preferences = state.get("preferences", [])
    results = {"attractions": [], "food": [], "hotels": []}
    try:
        d = await amap_service.search_attractions(city, limit=15)
        results["attractions"] = d.get("pois", [])
    except AmapAPIError as e: logger.warning(f"景点搜索失败: {e}")
    try:
        kw = preferences[0] if preferences else "美食"
        d = await amap_service.search_food(city, keywords=kw, limit=10)
        results["food"] = d.get("pois", [])
    except AmapAPIError as e: logger.warning(f"美食搜索失败: {e}")
    try:
        d = await amap_service.search_hotels(city, limit=8)
        results["hotels"] = d.get("pois", [])
    except AmapAPIError as e: logger.warning(f"酒店搜索失败: {e}")
    return {"poi_results": results}


async def query_weather_node(state: dict, llm, amap_service: AmapService) -> dict:
    city = state.get("city", "北京")
    try:
        wd = await amap_service.get_weather(city, extensions="all")
        lives = wd.get("lives", [])
        forecasts = wd.get("forecasts", [])
        casts = forecasts[0].get("casts", []) if forecasts else []
        summary = f"{lives[0].get('weather','')} {lives[0].get('temperature','')}°C" if lives else ""
        return {"weather": {"live": lives[0] if lives else {}, "forecasts": casts, "summary": summary}}
    except AmapAPIError as e:
        logger.warning(f"天气查询失败: {e}")
        return {"weather": {"live": {}, "forecasts": [], "summary": "天气暂不可用"}}


async def generate_daily_plans_node(state: dict, llm, amap_service) -> dict:
    city = state.get("city", "北京")
    days = state.get("days", 1)
    preferences = state.get("preferences", [])
    transportation = state.get("transportation", "地铁")
    poi_results = state.get("poi_results", {})
    weather = state.get("weather", {})
    forecasts = weather.get("forecasts", [])

    start_date = datetime.now() + timedelta(days=1)
    daily_plans = []

    for day_num in range(1, days + 1):
        date_obj = start_date + timedelta(days=day_num - 1)
        date_str = date_obj.strftime("%Y-%m-%d")
        weekday = _get_weekday(date_str)
        dw = dt = ""
        if day_num <= len(forecasts):
            fc = forecasts[day_num - 1]
            dw = f"{fc.get('dayweather','')}转{fc.get('nightweather','')}"
            dt = f"{fc.get('daytemp','')}°C~{fc.get('nighttemp','')}°C"

        prompt = TRIP_DAY_PROMPT.format(
            day=day_num, city=city, date=date_str, weekday=weekday,
            weather=dw, temperature=dt,
            attractions=_parse_poi_for_prompt(poi_results.get("attractions", []))
                      + "\n\n美食：\n" + _parse_poi_for_prompt(poi_results.get("food", []), 5),
            preferences=", ".join(preferences) if preferences else "无特殊偏好",
            transportation=transportation,
        )
        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            content = resp.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"): content = content[4:]
            plan = json.loads(content.strip())
        except Exception as e:
            logger.warning(f"第{day_num}天解析失败: {e}")
            plan = {
                "day": day_num,
                "morning": [{"name": "自由探索", "duration": "3h", "note": "根据兴趣选择"}],
                "lunch": {"name": "当地美食", "cuisine": "特色", "estimate": "人均50元"},
                "afternoon": [{"name": "城市漫步", "duration": "2h", "note": "感受城市"}],
                "evening": {"name": "夜市或商圈", "note": "体验夜生活"},
                "tips": ["行程可灵活调整"],
            }
        plan["date"] = date_str
        plan["weekday"] = weekday
        plan["weather"] = dw
        plan["temperature"] = dt
        daily_plans.append(plan)

    return {"daily_plans": daily_plans}


async def final_summary_node(state: dict, llm, amap_service) -> dict:
    city = state.get("city", "北京")
    days = state.get("days", 1)
    daily_plans = state.get("daily_plans", [])

    prompt = FINAL_SUMMARY_PROMPT.format(
        city=city, days=days,
        daily_plans_json=json.dumps(daily_plans, ensure_ascii=False, indent=2),
    )
    try:
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"final_summary": resp.content.strip(), "status": "done"}
    except Exception as e:
        logger.error(f"摘要生成失败: {e}")
        # 回退：自己拼接
        fallback = f"## {city} {days}日游\n\n"
        for dp in daily_plans:
            fallback += f"**第{dp.get('day')}天** ({dp.get('date','')} {dp.get('weekday','')})\n\n"
            for m in dp.get("morning", []):
                fallback += f"- ☀️ {m.get('name','')} ({m.get('duration','')})\n"
            fallback += f"- 🍽️ {dp.get('lunch',{}).get('name','')}\n"
            for a in dp.get("afternoon", []):
                fallback += f"- 🌤️ {a.get('name','')} ({a.get('duration','')})\n"
            fallback += f"- 🌙 {dp.get('evening',{}).get('name','')}\n\n"
        return {"final_summary": fallback, "status": "done"}


# ========== 反馈处理 ==========

async def handle_feedback_node(state: dict, llm, amap_service) -> dict:
    """
    处理用户反馈，修改已有计划
    """
    user_feedback = state.get("user_input", "")
    daily_plans = state.get("daily_plans", [])

    if not daily_plans:
        return {"error": "没有已生成的计划可供修改"}

    # ---- 检查是否是纯确认/结束信号 ----
    # 只有短消息（≤10字）且主要是确认意图才算确认
    confirm_keywords = ["满意", "可以了", "ok", "没问题", "就这样", "不用改了", "结束", "完成", "挺好的", "不错"]
    is_short = len(user_feedback.strip()) <= 10
    has_confirm = any(kw in user_feedback.lower() for kw in confirm_keywords)
    # 检查是否包含修改意图的关键词
    modify_keywords = ["改", "换", "加", "删", "少", "多", "调整", "不要", "太", "别", "增加", "减少", "去掉", "换成", "安排"]
    has_modify = any(kw in user_feedback for kw in modify_keywords)

    if is_short and has_confirm and not has_modify:
        logger.info(f"用户确认: '{user_feedback}'")
        return {"status": "confirmed", "user_confirmed": True}

    # ---- 用 LLM 修改计划 ----
    prompt = FEEDBACK_PROMPT.format(
        current_plan_json=json.dumps(daily_plans, ensure_ascii=False, indent=2),
        user_feedback=user_feedback,
    )

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"): content = content[4:]
        content = content.strip()
        modified_plans = json.loads(content)
        if isinstance(modified_plans, dict):
            modified_plans = [modified_plans]
        logger.info(f"反馈修改成功，得到 {len(modified_plans)} 天行程")
        return {"daily_plans": modified_plans, "status": "modified"}
    except json.JSONDecodeError as e:
        logger.warning(f"反馈 JSON 解析失败: {e}, 原始输出前200字: {content[:200] if 'content' in dir() else 'N/A'}")
        # 回退：保留原计划 + 添加说明
        return {
            "daily_plans": daily_plans,
            "status": "modified",
            "final_summary": "已尝试根据你的反馈调整行程，但部分细节需人工确认。以下是当前计划：",
        }
    except Exception as e:
        logger.error(f"反馈处理异常: {e}")
        return {
            "daily_plans": daily_plans,
            "status": "modified",
            "final_summary": f"处理反馈时遇到问题（{e}），已保留原计划。请重新描述你的需求。",
        }
    




# ========== Phase 3: MCP 工具调用节点 ==========

async def mcp_search_pois_node(state: dict, llm, mcp_tools: list) -> dict:
    """
    使用 MCP 工具搜索 POI（替代直接调用 AmapService）
    将 MCP 工具绑定到 LLM，让 LLM 自主决定调用哪些工具
    """
    from langchain_core.messages import HumanMessage, ToolMessage

    city = state.get("city", "北京")
    preferences = state.get("preferences", [])
    days = state.get("days", 1)

    # 让 LLM 决定调用哪些工具
    prompt = f"""你需要为旅行规划搜索 {city} 的信息。请使用可用的工具完成以下任务：

1. 搜索 {city} 的景点（调用 search_attractions）
2. 搜索 {city} 的美食（调用 search_food）
3. 查询 {city} 的天气（调用 get_weather）

用户偏好：{', '.join(preferences) if preferences else '无特殊偏好'}
旅行天数：{days} 天

请依次调用这些工具，获取数据后汇总返回。"""

    messages = [HumanMessage(content=prompt)]
    
    # 绑定工具到 LLM
    llm_with_tools = llm.bind_tools(mcp_tools)
    response = await llm_with_tools.ainvoke(messages)
    
    tool_results = {"attractions": [], "food": [], "weather": {}}
    
    # 处理工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # 找到对应工具并调用
            for tool in mcp_tools:
                if tool.name == tool_name:
                    try:
                        result = await tool.ainvoke(tool_args)
                        parsed = json.loads(result) if isinstance(result, str) else result
                        
                        if tool_name in ("search_attractions", "search_poi"):
                            tool_results["attractions"] = parsed.get("pois", [])
                        elif tool_name == "search_food":
                            tool_results["food"] = parsed.get("pois", [])
                        elif tool_name == "get_weather":
                            tool_results["weather"] = parsed
                    except Exception as e:
                        logger.warning(f"MCP 工具 {tool_name} 调用失败: {e}")

    return {"poi_results": tool_results}




# ========== Phase 5: 预算 & RAG & 路线增强节点 ==========

from ..services.budget_service import estimate_budget
from ..services.rag_service import rag_service


async def enrich_with_rag_node(state: dict, llm, amap_service) -> dict:
    """
    从 RAG 知识库检索城市相关旅游知识
    """
    city = state.get("city", "")
    preferences = state.get("preferences", [])

    query = f"{city} " + " ".join(preferences)
    tips = rag_service.query(city, query, n_results=5)

    return {"local_tips": tips, "rag_enriched": True}


async def budget_estimate_node(state: dict, llm, amap_service) -> dict:
    """
    估算旅行预算
    """
    city = state.get("city", "北京")
    days = state.get("days", 1)
    budget_level = state.get("budget_level", "舒适")
    daily_plans = state.get("daily_plans", [])

    # 统计每天景点数
    avg_attractions = 4
    if daily_plans:
        counts = []
        for dp in daily_plans:
            morning = len(dp.get("morning", []))
            afternoon = len(dp.get("afternoon", []))
            counts.append(morning + afternoon)
        avg_attractions = sum(counts) / len(counts) if counts else 4

    budget = estimate_budget(city, days, budget_level, int(avg_attractions))

    # 用 LLM 生成预算提示
    from .prompts import BUDGET_TIP_PROMPT
    prompt = BUDGET_TIP_PROMPT.format(
        city=city, days=days, budget_level=budget_level,
        budget_json=json.dumps(budget, ensure_ascii=False),
    )
    try:
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        budget_advice = resp.content.strip()
    except Exception:
        budget_advice = ""

    budget["advice"] = budget_advice
    return {"budget": budget}


async def route_optimize_node(state: dict, llm, amap_service: AmapService) -> dict:
    """
    优化每日景点游览顺序（基于高德路径规划）
    """
    city = state.get("city", "")
    daily_plans = state.get("daily_plans", [])
    transportation = state.get("transportation", "walking")
    poi_results = state.get("poi_results", {})

    if not daily_plans or not poi_results:
        return {}

    # 构建景点名→坐标的映射
    name_to_location = {}
    for category in ("attractions", "food"):
        for p in poi_results.get(category, []):
            name = p.get("name", "")
            loc_str = p.get("location", "")
            if name and "," in loc_str:
                try:
                    lng, lat = loc_str.split(",")
                    name_to_location[name] = (float(lng), float(lat))
                except ValueError:
                    pass

    mode_map = {"地铁": "transit", "自驾": "driving", "步行": "walking"}
    route_mode = mode_map.get(transportation, "walking")

    optimized_plans = []

    for dp in daily_plans:
        day_num = dp.get("day", 0)
        morning = dp.get("morning", [])
        afternoon = dp.get("afternoon", [])

        # 合并所有景点名
        all_attractions = [m.get("name", "") for m in morning] + [a.get("name", "") for a in afternoon]
        all_attractions = [n for n in all_attractions if n and n in name_to_location]

        if len(all_attractions) < 2:
            optimized_plans.append(dp)
            continue

        # 计算距离矩阵
        matrix = []
        for a_name in all_attractions:
            row = []
            a_loc = name_to_location[a_name]
            for b_name in all_attractions:
                if a_name == b_name:
                    row.append(0)
                else:
                    b_loc = name_to_location[b_name]
                    route = await amap_service.get_route_between(
                        a_loc[0], a_loc[1], b_loc[0], b_loc[1],
                        mode=route_mode, city=city,
                    )
                    row.append(route.get("distance", 0))
            matrix.append(row)

        # 贪心排序：从最近开始
        visited = set()
        order = [all_attractions[0]]
        visited.add(0)

        while len(order) < len(all_attractions):
            last = order[-1]
            last_idx = all_attractions.index(last)
            best_dist = float("inf")
            best_idx = -1
            for i, name in enumerate(all_attractions):
                if i not in visited and matrix[last_idx][i] < best_dist:
                    best_dist = matrix[last_idx][i]
                    best_idx = i
            if best_idx >= 0:
                order.append(all_attractions[best_idx])
                visited.add(best_idx)
            else:
                break

        # 重新分配 morning / afternoon（简单二分）
        mid = len(order) // 2 + len(order) % 2
        new_morning = []
        new_afternoon = []
        for i, name in enumerate(order):
            original = None
            for m in morning:
                if m.get("name") == name:
                    original = m
                    break
            for a in afternoon:
                if a.get("name") == name:
                    original = a
                    break
            entry = original if original else {"name": name, "duration": "2h", "note": ""}
            if i < mid:
                new_morning.append(entry)
            else:
                new_afternoon.append(entry)

        dp_new = dict(dp)
        dp_new["morning"] = new_morning
        dp_new["afternoon"] = new_afternoon
        dp_new["optimized_route"] = True
        optimized_plans.append(dp_new)

    return {"daily_plans": optimized_plans, "route_optimized": True}


async def enriched_generate_plans_node(state: dict, llm, amap_service) -> dict:
    """
    增强版行程生成（集成 RAG 知识 + 预算约束）
    """
    from .prompts import ENRICHED_TRIP_DAY_PROMPT

    city = state.get("city", "北京")
    days = state.get("days", 1)
    preferences = state.get("preferences", [])
    transportation = state.get("transportation", "地铁")
    budget_level = state.get("budget_level", "舒适")
    poi_results = state.get("poi_results", {})
    weather = state.get("weather", {})
    local_tips = state.get("local_tips", [])
    budget = state.get("budget", {})

    forecasts = weather.get("forecasts", [])
    start_date = datetime.now() + timedelta(days=1)
    daily_plans = []

    tips_text = "\n".join(f"- {t}" for t in local_tips[:5]) if local_tips else "暂无"
    budget_text = json.dumps(budget, ensure_ascii=False) if budget else "未估算"

    for day_num in range(1, days + 1):
        date_obj = start_date + timedelta(days=day_num - 1)
        date_str = date_obj.strftime("%Y-%m-%d")
        weekday = _get_weekday(date_str)
        dw = dt = ""
        if day_num <= len(forecasts):
            fc = forecasts[day_num - 1]
            dw = f"{fc.get('dayweather','')}转{fc.get('nightweather','')}"
            dt = f"{fc.get('daytemp','')}°C~{fc.get('nighttemp','')}°C"

        prompt = ENRICHED_TRIP_DAY_PROMPT.format(
            day=day_num, city=city, date=date_str, weekday=weekday,
            weather=dw, temperature=dt,
            attractions=_parse_poi_for_prompt(poi_results.get("attractions", []))
                      + "\n\n美食：\n" + _parse_poi_for_prompt(poi_results.get("food", []), 5),
            preferences=", ".join(preferences) if preferences else "无特殊偏好",
            transportation=transportation,
            budget_info=budget_text,
            local_tips=tips_text,
        )
        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            content = resp.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"): content = content[4:]
            plan = json.loads(content.strip())
        except Exception:
            plan = {
                "day": day_num,
                "morning": [{"name": "自由探索", "duration": "3h", "note": "", "estimated_cost": 0}],
                "lunch": {"name": "当地美食", "cuisine": "特色", "estimate": "人均50元"},
                "afternoon": [{"name": "城市漫步", "duration": "2h", "note": "", "estimated_cost": 0}],
                "evening": {"name": "夜市", "note": "", "estimated_cost": 0},
                "tips": [],
            }
        plan["date"] = date_str
        plan["weekday"] = weekday
        plan["weather"] = dw
        plan["temperature"] = dt
        daily_plans.append(plan)

    return {"daily_plans": daily_plans, "enriched": True}


async def enriched_final_summary_node(state: dict, llm, amap_service) -> dict:
    """增强版摘要（含预算 + 本地贴士）"""
    from .prompts import ENRICHED_FINAL_PROMPT

    city = state.get("city", "北京")
    days = state.get("days", 1)
    daily_plans = state.get("daily_plans", [])
    budget = state.get("budget", {})
    local_tips = state.get("local_tips", [])

    tips_text = "\n".join(f"- {t}" for t in local_tips[:5]) if local_tips else "暂无"

    prompt = ENRICHED_FINAL_PROMPT.format(
        city=city, days=days,
        daily_plans_json=json.dumps(daily_plans, ensure_ascii=False, indent=2),
        budget_json=json.dumps(budget, ensure_ascii=False) if budget else "未估算",
        local_tips=tips_text,
    )
    try:
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        summary = resp.content.strip()
    except Exception:
        summary = f"## {city} {days}日游\n\n计划已生成"

    return {"final_summary": summary, "status": "done"}
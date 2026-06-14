"""
LangGraph 旅行规划工作流
"""
import json
import logging
import uuid
from typing import TypedDict, AsyncIterator, Optional

from .nodes import (
    parse_intent_node,
    search_pois_node,
    query_weather_node,
    generate_daily_plans_node,
    final_summary_node,
    handle_feedback_node,
)
from ..amap_service import AmapService
from ..services.llm_service import create_llm
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AgentState(TypedDict, total=False):
    user_input: str
    city: str
    days: int
    preferences: list[str]
    transportation: str
    budget_level: str
    poi_results: dict
    weather: dict
    daily_plans: list[dict]
    final_summary: str
    status: str
    error: str
    user_confirmed: bool
    session_id: str


# ===== Session 管理 =====
_sessions: dict[str, dict] = {}


def get_session(sid: str) -> dict:
    if sid not in _sessions:
        _sessions[sid] = {
            "messages": [], "daily_plans": [], "city": "",
            "days": 1, "weather": {}, "final_summary": "",
        }
    return _sessions[sid]


def clear_session(sid: str):
    _sessions.pop(sid, None)


# ===== TripAgent =====

class TripAgent:
    """
    AI 旅行规划 Agent

    MCP 工具加载失败时自动回退到直连 AmapService，不影响核心功能。
    """

    def __init__(self, amap_api_key: str):
        self.amap_api_key = amap_api_key
        self.llm = create_llm(temperature=0.7)
        self.amap = AmapService(api_key=amap_api_key)

    async def close(self):
        await self.amap.close()

    # ===== 新建规划 =====

    async def plan_stream(self, user_input: str) -> AsyncIterator[dict]:
        llm = self.llm
        amap = self.amap
        state: dict = {"user_input": user_input, "status": "running"}

        yield {"type": "status", "content": "正在分析你的需求..."}
        result = await parse_intent_node(state, llm, amap)
        state.update(result)
        if "error" in result:
            yield {"type": "error", "content": result["error"]}
            return
        yield {"type": "intent", "data": {k: state[k] for k in ["city", "days", "preferences", "transportation", "budget_level"] if k in state}}

        yield {"type": "status", "content": f"正在搜索 {state.get('city')} 的景点和美食..."}
        result = await search_pois_node(state, llm, amap)
        state.update(result)
        yield {"type": "tool_result", "content": f"找到 {len(state.get('poi_results', {}).get('attractions', []))} 个景点"}

        yield {"type": "status", "content": "正在查询天气..."}
        result = await query_weather_node(state, llm, amap)
        state.update(result)
        yield {"type": "tool_result", "content": f"天气：{state.get('weather', {}).get('summary', '')}"}

        yield {"type": "status", "content": f"正在生成 {state.get('days', 1)} 天行程..."}
        result = await generate_daily_plans_node(state, llm, amap)
        state.update(result)
        yield {"type": "plan_preview", "data": {"daily_plans": state.get("daily_plans", [])}}

        yield {"type": "status", "content": "正在生成最终计划..."}
        result = await final_summary_node(state, llm, amap)
        state.update(result)

        yield {
            "type": "done",
            "data": {
                "city": state.get("city"), "days": state.get("days"),
                "daily_plans": state.get("daily_plans", []),
                "weather": state.get("weather", {}),
                "final_summary": state.get("final_summary", ""),
                "session_id": str(uuid.uuid4()),
            }
        }

    # ===== 多轮对话 =====

    async def chat_stream(self, session_id: str, user_message: str) -> AsyncIterator[dict]:
        session = get_session(session_id)
        llm = self.llm
        amap = self.amap

        session["messages"].append({"role": "user", "content": user_message})

        # ========== 新规划 ==========
        if not session.get("daily_plans"):
            yield {"type": "status", "content": "正在分析你的需求..."}
            state = {"user_input": user_message, "status": "running"}

            result = await parse_intent_node(state, llm, amap)
            state.update(result)
            if "error" in result:
                yield {"type": "error", "content": result["error"]}
                return
            yield {"type": "intent", "data": {k: state[k] for k in ["city", "days", "preferences", "transportation", "budget_level"] if k in state}}

            yield {"type": "status", "content": f"正在搜索 {state.get('city')}..."}
            result = await search_pois_node(state, llm, amap)
            state.update(result)

            yield {"type": "status", "content": "正在查询天气..."}
            result = await query_weather_node(state, llm, amap)
            state.update(result)

            yield {"type": "status", "content": "正在生成行程..."}
            result = await generate_daily_plans_node(state, llm, amap)
            state.update(result)

            yield {"type": "status", "content": "正在润色..."}
            result = await final_summary_node(state, llm, amap)
            state.update(result)

            session.update({
                "city": state.get("city", ""),
                "days": state.get("days", 1),
                "daily_plans": state.get("daily_plans", []),
                "weather": state.get("weather", {}),
                "final_summary": state.get("final_summary", ""),
            })

            yield {
                "type": "done",
                "data": {
                    "city": session["city"], "days": session["days"],
                    "daily_plans": session["daily_plans"],
                    "weather": session["weather"],
                    "final_summary": session["final_summary"],
                    "session_id": session_id,
                }
            }
            session["messages"].append({"role": "assistant", "content": "计划已生成"})
            return

        # ========== 修改已有计划 ==========
        yield {"type": "status", "content": "正在理解你的修改需求..."}

        state = {
            "user_input": user_message,
            "daily_plans": session["daily_plans"],
            "status": "modifying",
        }

        result = await handle_feedback_node(state, llm, amap)
        state.update(result)

        if result.get("user_confirmed"):
            yield {"type": "status", "content": "✅ 计划已确认！祝你旅途愉快 ✈️"}
            yield {
                "type": "confirmed",
                "data": {
                    "message": "计划已确认，旅途愉快！",
                    "daily_plans": session["daily_plans"],
                }
            }
            clear_session(session_id)
            return

        modified_plans = result.get("daily_plans", session["daily_plans"])
        session["daily_plans"] = modified_plans

        yield {"type": "status", "content": "✨ 正在更新计划..."}
        summary_state = {
            "city": session.get("city", ""),
            "days": session.get("days", 1),
            "daily_plans": modified_plans,
        }
        summary_result = await final_summary_node(summary_state, llm, amap)
        session["final_summary"] = summary_result.get("final_summary", "")

        yield {
            "type": "done",
            "data": {
                "city": session.get("city"), "days": session.get("days"),
                "daily_plans": modified_plans,
                "weather": session.get("weather", {}),
                "final_summary": session.get("final_summary", ""),
                "session_id": session_id,
            }
        }
        session["messages"].append({"role": "assistant", "content": "计划已更新"})


# ===== MCP 工具加载（独立函数，不影响主流程） =====

async def load_mcp_tools(amap_api_key: str) -> list:
    """
    尝试加载 MCP 工具。
    成功返回工具列表，失败返回空列表（应用仍可正常运行）。
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as e:
        logger.warning(f"MCP 客户端库不可用: {e}")
        return []

    import sys
    from pathlib import Path

    server_path = Path(__file__).resolve().parent.parent / "mcp_servers" / "amap_server.py"

    try:
        client = MultiServerMCPClient({
            "amap": {
                "command": sys.executable,
                "args": [str(server_path)],
                "env": {"AMAP_API_KEY": amap_api_key},
            }
        })
        tools = await client.get_tools()
        logger.info(f"✅ MCP 工具已加载: {[t.name for t in tools]}")
        return tools
    except Exception as e:
        logger.warning(f"MCP 工具加载失败（使用直连 API）: {e}")
        return []
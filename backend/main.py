"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .dependencies import get_amap_service
from .routers import api_router          # ← 统一导入

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时打印信息，关闭时释放连接"""
    startup_msg = (
        f"\n{'='*50}\n"
        f"  ✈️  AI 旅行助手后端 v0.1.0\n"
        f"  📖 API 文档 → http://{settings.app_host}:{settings.app_port}/docs\n"
        f"  🔍 健康检查 → http://{settings.app_host}:{settings.app_port}/api/health\n"
        f"{'='*50}\n"
    )
    print(startup_msg)
    yield
    # 关闭时清理 amap_service 连接池
    amap = await get_amap_service()
    await amap.close()
    print("👋 服务已关闭")


app = FastAPI(
    title="AI 旅行助手 API",
    description="基于高德地图的旅行规划助手 — Phase 1",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 开发阶段允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 注册路由 =====
# 只需一行：所有子路由已聚合到 api_router
app.include_router(api_router)


# ===== 健康检查 =====
@app.get("/api/health", tags=["系统"])
async def health_check():
    return {"status": "ok", "service": "AI 旅行助手", "version": "0.1.0"}


# ===== 直接启动入口 =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level="info",
    )
import json
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .amap_service import get_amap_service, AmapService
from .agents.trip_graph import TripAgent
from .routers import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n{'='*50}")
    print(f"  ✈️  AI 旅行助手 v0.2.0 (Phase 2)")
    print(f"  📖 API: http://{settings.app_host}:{settings.app_port}/docs")
    print(f"  🧠 Agent: LangGraph + {settings.llm_model}")
    print(f"{'='*50}\n")
    yield
    amap = await get_amap_service()
    await amap.close()
    print("👋 服务已关闭")


app = FastAPI(title="AI 旅行助手 API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def catch_all(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": "内部错误"})


app.include_router(api_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0", "llm_model": settings.llm_model}


# ========== Agent SSE 接口 ==========

@app.post("/api/trip/plan")
async def plan_trip(user_input: str = Query(..., description="用户需求")):
    """
    AI 旅行规划 — SSE 流式返回
    """

    async def event_stream():
        agent = TripAgent(amap_api_key=settings.amap_web_api_key)
        try:
            async for event in agent.plan_stream(user_input):
                event_type = event.get("type", "message")

                # 提取 data 部分：有 data 字段就用它，否则用整个 event（去掉 type）
                if "data" in event:
                    payload = event["data"]
                else:
                    payload = {k: v for k, v in event.items() if k != "type"}

                yield {
                    "event": event_type,
                    "data": json.dumps(payload, ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"content": str(e)}, ensure_ascii=False),
            }
        finally:
            await agent.close()

    return EventSourceResponse(event_stream())




# ========== Phase 2 新增：多轮对话接口 ==========

@app.post("/api/trip/chat")
async def chat_with_agent(
    session_id: str = Query(default="", description="会话 ID，首次为空"),
    user_input: str = Query(..., description="用户消息"),
):
    """
    AI 旅行规划 — 多轮对话 SSE

    - 首次调用时 session_id 可为空，后端会返回新的 session_id
    - 后续调用传入 session_id 继续对话
    - 用户说"满意/可以/好的"结束会话
    """
    import uuid

    # 空 session_id 则创建新会话
    if not session_id:
        session_id = str(uuid.uuid4())

    async def event_stream():
        agent = TripAgent(amap_api_key=settings.amap_web_api_key)
        try:
            async for event in agent.chat_stream(session_id, user_input):
                event_type = event.get("type", "message")
                if "data" in event:
                    payload = event["data"]
                else:
                    payload = {k: v for k, v in event.items() if k != "type"}
                # 确保 session_id 始终返回
                if "session_id" not in payload:
                    payload["session_id"] = session_id
                yield {
                    "event": event_type,
                    "data": json.dumps(payload, ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"content": str(e)}, ensure_ascii=False),
            }
        finally:
            await agent.close()

    return EventSourceResponse(event_stream())






# ========== Phase 3: MCP 状态 ==========
# ========== Phase 3: MCP 状态接口 ==========

@app.get("/api/mcp/status")
async def mcp_status():
    """检查 MCP 工具是否可用"""
    import sys
    from pathlib import Path

    server_path = Path(__file__).resolve().parent / "mcp_servers" / "amap_server.py"
    server_exists = server_path.exists()

    # 尝试导入 MCP 客户端
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as e:
        return {
            "status": "unavailable",
            "reason": f"MCP 客户端库导入失败: {e}",
            "server_exists": server_exists,
            "server_path": str(server_path),
            "suggestion": "pip install pywin32 mcp langchain-mcp-adapters",
        }

    try:
        client = MultiServerMCPClient({
            "amap": {
                "command": sys.executable,
                "args": [str(server_path)],
                "env": {"AMAP_API_KEY": settings.amap_web_api_key},
            }
        })
        tools = await client.get_tools()
        return {
            "status": "ok",
            "server_path": str(server_path),
            "server_exists": server_exists,
            "tools_count": len(tools),
            "tools": [{"name": t.name, "description": t.description[:80]} for t in tools],
        }
    except Exception as e:
        return {
            "status": "error",
            "server_path": str(server_path),
            "server_exists": server_exists,
            "error": str(e),
        }
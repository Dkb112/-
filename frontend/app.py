"""
AI 旅行助手 - Streamlit 前端
纯 Python,零 HTML/CSS/JS
"""
import streamlit as st
import pandas as pd
from api_client import api

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="AI 旅行助手",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== 自定义样式 ====================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .poi-card {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 15px;
        margin: 8px 0;
        background-color: #fafafa;
    }
    .poi-card:hover {
        border-color: #1f77b4;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .weather-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
    }
    .metric-box {
        background: white;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ==================== 标题 ====================
st.markdown('<div class="main-header">✈️ AI 旅行助手</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">基于高德地图 · 智能搜索景点、美食、天气</div>', unsafe_allow_html=True)

# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("🔍 搜索设置")

    # 城市输入
    city = st.text_input(
        "📍 目的地城市",
        value="北京",
        placeholder="输入城市名，如 杭州、成都、三亚...",
    )

    # 搜索类型
    search_type = st.radio(
        "📋 搜索类型",
        options=["🏛️ 景点", "🍜 美食", "🏨 酒店", "🌤️ 天气"],
        horizontal=True,
    )

    # 关键词（天气模式不需要）
    if search_type != "🌤️ 天气":
        keyword = st.text_input(
            "🔑 关键词",
            value="",
            placeholder="如：故宫、火锅、海景房...",
        )

    # 结果数量
    limit = st.slider("📊 结果数量", min_value=5, max_value=30, value=10, step=5)

    # 搜索按钮
    search_btn = st.button("🔍 搜索", type="primary", use_container_width=True)

    st.divider()

    # 后端状态
    st.caption("🔌 后端状态")
    try:
        health = api.health_check()
        st.success(f"✅ 服务正常 ({health['version']})")
    except Exception:
        st.error("❌ 后端未连接")

# ==================== 主内容区 ====================

# 快速标签
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    if st.button("🏯 故宫", use_container_width=True):
        st.session_state.quick_search = ("北京", "故宫", "🏛️ 景点")
with col2:
    if st.button("🌊 西湖", use_container_width=True):
        st.session_state.quick_search = ("杭州", "西湖", "🏛️ 景点")
with col3:
    if st.button("🌶️ 火锅", use_container_width=True):
        st.session_state.quick_search = ("成都", "火锅", "🍜 美食")
with col4:
    if st.button("🏖️ 三亚", use_container_width=True):
        st.session_state.quick_search = ("三亚", "海滩", "🏛️ 景点")
with col5:
    if st.button("🏔️ 丽江", use_container_width=True):
        st.session_state.quick_search = ("丽江", "古城", "🏛️ 景点")

# 处理快速搜索
if "quick_search" in st.session_state:
    q_city, q_keyword, q_type = st.session_state.quick_search
    city = q_city
    search_type = q_type
    keyword = q_keyword
    search_btn = True  # 自动触发搜索
    del st.session_state.quick_search

# ==================== 天气展示 ====================
def display_weather(city: str):
    """展示天气信息"""
    with st.spinner(f"🌤️ 正在查询 {city} 天气..."):
        try:
            weather_data = api.get_weather(city)
        except Exception as e:
            st.error(f"天气查询失败: {e}")
            return

    live = weather_data.get("live")
    forecasts = weather_data.get("forecasts", [])

    if live:
        st.markdown("### 🌤️ 实时天气")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🌡️ 温度", f"{live['temperature']}°C")
        with col2:
            st.metric("☁️ 天气", live['weather'])
        with col3:
            st.metric("💧 湿度", f"{live['humidity']}%")
        with col4:
            st.metric("💨 风力", f"{live['windpower']}级 {live['winddirection']}")

    if forecasts:
        st.markdown("### 📅 未来天气预报")

        # 用列展示预报
        cols = st.columns(min(len(forecasts), 4))
        for i, fc in enumerate(forecasts[:4]):
            with cols[i]:
                st.markdown(f"""
                <div style="text-align:center; padding:10px; 
                            background:#f0f2f6; border-radius:10px;">
                    <strong>{fc['date']}</strong><br>
                    <small>{fc['week']}</small><br>
                    ☀️ {fc['daytemp']}°C / 🌙 {fc['nighttemp']}°C<br>
                    <small>{fc['dayweather']}</small>
                </div>
                """, unsafe_allow_html=True)

    # 出行建议
    if live:
        st.markdown("### 💡 出行建议")
        temp = int(live['temperature'].replace("℃", "").replace("°C", "").strip())
        weather_text = live['weather']

        tips = []
        if temp > 35:
            tips.append("🔥 高温天气，注意防暑防晒，多带饮用水")
        elif temp > 28:
            tips.append("☀️ 天气较热，建议穿轻薄透气衣物")
        elif temp > 15:
            tips.append("🌸 温度舒适，非常适合户外活动")
        elif temp > 5:
            tips.append("🍂 天气偏凉，建议携带外套")
        else:
            tips.append("❄️ 天气寒冷，注意保暖")

        if "雨" in weather_text:
            tips.append("🌧️ 有降雨可能，记得带伞！")
        if "雪" in weather_text:
            tips.append("⛄ 有降雪，注意防滑保暖")
        if "晴" in weather_text:
            tips.append("📸 晴天光线好，适合拍照")

        for tip in tips:
            st.info(tip)

# ==================== POI 结果展示 ====================
def display_poi_results(result: dict, search_type: str):
    """展示 POI 搜索结果"""
    pois = result.get("pois", [])
    total = result.get("total", 0)

    if not pois:
        st.warning("未找到相关结果，请尝试其他关键词")
        return

    st.markdown(f"### 📍 搜索结果（共 {total} 条）")

    # 表格展示
    table_data = []
    for p in pois:
        addr = p.get("address", "")
        table_data.append({
            "名称": p.get("name", "未知"),
            "地址": addr[:30] + "..." if len(addr) > 30 else addr,
            "类型": p.get("poi_type", ""),                              # ← .get
            "经度": round(p.get("location", {}).get("lng", 0), 4),
            "纬度": round(p.get("location", {}).get("lat", 0), 4),
            "电话": p.get("tel") or "无",
        })

    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 卡片展示
    st.markdown("---")
    st.markdown("### 🃏 详细卡片")

    cols = st.columns(2)
    for i, p in enumerate(pois):
        with cols[i % 2]:
            icon = {"🏛️ 景点": "🏯", "🍜 美食": "🍽️", "🏨 酒店": "🏨"}.get(search_type, "📍")
            name = p.get("name", "未知")
            address = p.get("address", "")
            tel = p.get("tel") or "无电话信息"
            loc = p.get("location", {})
            lng = loc.get("lng", 0)
            lat = loc.get("lat", 0)
            st.markdown(f"""
            <div class="poi-card">
                <h4>{icon} {name}</h4>
                <p>📍 {address}</p>
                <p>📞 {tel}</p>
                <p>🗺️ 坐标: {lng:.4f}, {lat:.4f}</p>
            </div>
            """, unsafe_allow_html=True)

    # 地图可视化
    st.markdown("---")
    st.markdown("### 🗺️ 位置分布")
    map_data = pd.DataFrame([
        {
            "name": p.get("name", ""),
            "lat": p.get("location", {}).get("lat", 0),
            "lon": p.get("location", {}).get("lng", 0),
        }
        for p in pois
    ])
    st.map(map_data, latitude="lat", longitude="lon", size=100, color="#1f77b4")

# ==================== 搜索逻辑 ====================
if search_btn:
    if not city:
        st.error("请输入城市名称")
    else:
        if search_type == "🌤️ 天气":
            display_weather(city)
        else:
            if not keyword:
                st.error("请输入搜索关键词")
            else:
                with st.spinner(f"🔍 正在搜索 {city} 的 {keyword}..."):
                    try:
                        # 映射搜索类型
                        poi_type_map = {
                            "🏛️ 景点": "风景名胜|公园|博物馆|展览馆",
                            "🍜 美食": "餐饮|中餐厅|火锅|小吃",
                            "🏨 酒店": "酒店|宾馆|青年旅社",
                        }
                        poi_type = poi_type_map.get(search_type)

                        result = api.search_poi(
                            keywords=keyword,
                            city=city,
                            poi_type=poi_type,
                            limit=limit,
                        )
                        display_poi_results(result, search_type)

                    except Exception as e:
                        st.error(f"搜索失败: {e}")

# ==================== 底部信息 ====================
st.divider()
st.caption(
    "🚧 Phase 1 - 基础功能演示 | "
    "数据来源：高德地图 Open API | "
    "后续版本将集成 LLM 智能规划 & 路线优化"
)
# 在侧边栏最上方添加
import json
mode = st.radio("🤖 模式", ["🔍 搜索模式", "🧠 AI 规划模式"], horizontal=True)
if mode == "🧠 AI 规划模式":
    st.markdown("### 💬 AI 旅行规划师")
    st.markdown("告诉我你的需求，例如：**「杭州3天休闲游，喜欢自然风景和美食」**")
    st.caption("生成计划后可提出修改意见，如「第三天太累了少安排点」。说「满意」即可结束。")

    # 初始化状态
    for key, default in [("chat_session_id", ""), ("chat_messages", []), ("chat_daily_plans", []), ("chat_summary", "")]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 显示历史
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 始终显示最新计划
    if st.session_state.chat_daily_plans:
        with st.expander("📋 当前行程", expanded=True):
            for dp in st.session_state.chat_daily_plans:
                st.markdown(f"**第{dp.get('day')}天** {dp.get('date','')} {dp.get('weekday','')} | {dp.get('weather','')}")
                for m in dp.get("morning", []):
                    st.markdown(f"☀️ {m.get('name','')} ({m.get('duration','')})")
                st.markdown(f"🍽️ {dp.get('lunch',{}).get('name','')}")
                for a in dp.get("afternoon", []):
                    st.markdown(f"🌤️ {a.get('name','')} ({a.get('duration','')})")
                st.markdown(f"🌙 {dp.get('evening',{}).get('name','')}")
                st.markdown("---")

    if st.session_state.chat_summary:
        with st.expander("📝 完整摘要"):
            st.markdown(st.session_state.chat_summary)

    # 输入
    user_query = st.chat_input("描述需求或修改意见...")
    if not user_query:
        st.stop()

    # 添加用户消息
    st.session_state.chat_messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.write(user_query)

    # 调用后端
    with st.chat_message("assistant"):
        status_ph = st.empty()
        result_ph = st.empty()
        full_response = ""

        try:
            import httpx, json
            url = "http://localhost:8000/api/trip/chat"
            params = {"session_id": st.session_state.chat_session_id, "user_input": user_query}

            with httpx.Client(timeout=120) as client:
                with client.stream("POST", url, params=params) as resp:
                    current_event = ""
                    for line in resp.iter_lines():
                        if line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            if not data_str: continue
                            try:
                                payload = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            if current_event in ("status", "tool_result"):
                                status_ph.info(payload.get("content", ""))
                            elif current_event == "intent":
                                status_ph.success(
                                    f"✅ {payload.get('city')} | {payload.get('days')}天 | "
                                    f"{'、'.join(payload.get('preferences', []))}"
                                )
                            elif current_event == "plan_preview":
                                dps = payload.get("daily_plans", [])
                                preview = ""
                                for dp in dps:
                                    preview += f"**第{dp.get('day')}天** {dp.get('date','')}\n"
                                    for m in dp.get("morning", []):
                                        preview += f"☀️ {m.get('name','')}\n"
                                    preview += f"🍽️ {dp.get('lunch',{}).get('name','')}\n"
                                    for a in dp.get("afternoon", []):
                                        preview += f"🌤️ {a.get('name','')}\n"
                                    preview += "\n"
                                result_ph.markdown(preview)
                            elif current_event == "done":
                                dps = payload.get("daily_plans", [])
                                st.session_state.chat_daily_plans = dps
                                st.session_state.chat_session_id = payload.get("session_id", "")
                                summary = payload.get("final_summary", "")
                                st.session_state.chat_summary = summary
                                result_ph.markdown(summary)
                                status_ph.success("✅ 已更新！可继续提出修改，或说「满意」结束。")
                                full_response = summary if summary else "计划已更新"
                            elif current_event == "confirmed":
                                st.session_state.chat_daily_plans = []
                                st.session_state.chat_session_id = ""
                                st.session_state.chat_summary = ""
                                status_ph.success(payload.get("message", "✅ 已确认！"))
                                full_response = "计划已确认，旅途愉快！"
                            elif current_event == "error":
                                status_ph.error(payload.get("content", str(payload)))
                                full_response = f"出错了：{payload.get('content', '')}"

        except Exception as e:
            status_ph.error(f"连接失败: {e}")
            full_response = f"网络错误: {e}"

        # 保存回复
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": full_response or "已收到，正在处理..."
        })

    st.rerun()
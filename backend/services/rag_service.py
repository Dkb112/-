"""
RAG 知识库服务
使用 ChromaDB 存储旅游知识，检索时注入到 LLM prompt
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 嵌入模型（轻量离线可用）
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ChromaDB 持久化路径
CHROMA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "chroma_db"

# ===== 内置旅游知识库 =====
TRAVEL_KNOWLEDGE = [
    # 北京
    {"city": "北京", "content": "北京最佳旅游季节是4-5月和9-10月，春秋气候宜人。避开国庆黄金周和五一假期。", "topic": "季节"},
    {"city": "北京", "content": "故宫需提前7天在官网预约，每日限流8万人。周一闭馆。门票旺季60元淡季40元。", "topic": "景点贴士"},
    {"city": "北京", "content": "北京烤鸭推荐全聚德、便宜坊、大董。人均150-300元。前门店游客较多，推荐和平门店。", "topic": "美食"},
    {"city": "北京", "content": "北京地铁覆盖主要景点，推荐办一张交通卡。早晚高峰（7-9点、17-19点）地铁非常拥挤。", "topic": "交通"},
    {"city": "北京", "content": "长城推荐慕田峪或八达岭。慕田峪游客较少，八达岭交通更方便。距市区约1.5小时车程。", "topic": "景点贴士"},
    {"city": "北京", "content": "北京冬季平均气温-5°C到5°C，夏季25°C-35°C。春季多风沙，注意防护。", "topic": "气候"},

    # 杭州
    {"city": "杭州", "content": "西湖免费开放，建议骑行环湖。苏堤春晓、断桥残雪、雷峰夕照是经典景观。", "topic": "景点贴士"},
    {"city": "杭州", "content": "灵隐寺门票75元，飞来峰45元。建议上午前往，游客较少。", "topic": "景点贴士"},
    {"city": "杭州", "content": "杭州美食：西湖醋鱼、东坡肉、龙井虾仁、叫花鸡。推荐楼外楼、知味观。", "topic": "美食"},
    {"city": "杭州", "content": "杭州最佳季节是3-5月和9-11月。西湖龙井茶园春季最美。", "topic": "季节"},

    # 成都
    {"city": "成都", "content": "成都大熊猫繁育研究基地门票55元，建议早上8点前到达，熊猫最活跃。", "topic": "景点贴士"},
    {"city": "成都", "content": "成都美食：火锅、串串香、担担面、龙抄手、夫妻肺片。春熙路和宽窄巷子是美食集中地。", "topic": "美食"},
    {"city": "成都", "content": "都江堰和青城山距成都约1小时车程，可安排一日游。都江堰门票80元。", "topic": "景点贴士"},
    {"city": "成都", "content": "成都气候湿润，夏季闷热，冬季阴冷。最佳旅游季节3-6月和9-11月。", "topic": "气候"},

    # 上海
    {"city": "上海", "content": "外滩、南京路步行街免费，东方明珠门票198元起。外滩夜景最美。", "topic": "景点贴士"},
    {"city": "上海", "content": "上海迪士尼平日门票475元，节假日665元。建议非周末前往。", "topic": "景点贴士"},
    {"city": "上海", "content": "上海美食：小笼包（南翔馒头店）、生煎、葱油拌面。城隍庙是美食集中地。", "topic": "美食"},

    # 三亚
    {"city": "三亚", "content": "三亚最佳季节11月-次年4月，避寒胜地。5-10月是雨季和台风季。", "topic": "季节"},
    {"city": "三亚", "content": "三亚海滩免费，但水上项目收费。推荐亚龙湾、海棠湾。蜈支洲岛门票+船票144元。", "topic": "景点贴士"},
    {"city": "三亚", "content": "三亚海鲜推荐第一市场，但注意防宰。人均100-200元。三亚免税店购物需提前下单。", "topic": "美食"},

    # 丽江
    {"city": "丽江", "content": "丽江古城维护费50元。最佳季节4-10月。玉龙雪山大索道票需提前抢购。", "topic": "景点贴士"},
    {"city": "丽江", "content": "丽江海拔2400米，部分人会有高原反应。建议第一天轻活动适应。", "topic": "健康"},

    # 通用
    {"city": "通用", "content": "出行前准备：身份证、充电宝、常用药、防晒霜、舒适鞋子。下载离线地图以防信号不好。", "topic": "出行准备"},
    {"city": "通用", "content": "旅行保险建议购买，包含意外医疗和行程取消。支付宝可购买短期旅行险。", "topic": "安全"},
    {"city": "通用", "content": "中国法定节假日（春节、五一、十一）景点拥挤，酒店涨价2-3倍，尽量避开。", "topic": "季节"},
]


class RAGService:
    """基于 ChromaDB 的旅游知识检索"""

    def __init__(self):
        self._collection = None
        self._embedder = None

    def _ensure_collection(self):
        """懒加载 ChromaDB collection"""
        if self._collection is not None:
            return

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            logger.warning("chromadb 未安装，RAG 功能降级为内置匹配")
            return

        try:
            os.makedirs(CHROMA_PATH, exist_ok=True)

            client = chromadb.PersistentClient(
                path=str(CHROMA_PATH),
                settings=Settings(anonymized_telemetry=False),
            )

            self._collection = client.get_or_create_collection(
                name="travel_knowledge",
                metadata={"description": "旅游知识库"},
            )

            # 如果集合为空，导入内置知识
            if self._collection.count() == 0:
                self._import_builtin_knowledge()
        except Exception as e:
            logger.warning(f"ChromaDB 初始化失败: {e}")
            self._collection = None

    def _import_builtin_knowledge(self):
        """导入内置旅游知识到 ChromaDB"""
        if self._collection is None:
            return

        docs = []
        ids = []
        metadatas = []

        for i, item in enumerate(TRAVEL_KNOWLEDGE):
            docs.append(item["content"])
            ids.append(f"knowledge_{i}")
            metadatas.append({"city": item["city"], "topic": item["topic"]})

        try:
            self._collection.add(documents=docs, ids=ids, metadatas=metadatas)
            logger.info(f"导入 {len(docs)} 条旅游知识")
        except Exception as e:
            logger.warning(f"导入知识失败: {e}")

    def query(self, city: str, query_text: str = "", n_results: int = 5) -> list[str]:
        """
        检索相关旅游知识

        Args:
            city: 目标城市
            query_text: 查询文本（可选，用于语义匹配）
            n_results: 返回结果数

        Returns:
            知识文本列表
        """
        self._ensure_collection()

        # 如果 ChromaDB 不可用，回退到内置匹配
        if self._collection is None:
            return self._fallback_search(city, query_text, n_results)

        try:
            query = query_text or f"{city} 旅游 景点 美食 交通 季节"
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results * 2,
                where={"city": {"$in": [city, "通用"]}},
            )

            # 去重
            seen = set()
            unique = []
            for doc in results.get("documents", [[]])[0]:
                if doc not in seen:
                    seen.add(doc)
                    unique.append(doc)
            return unique[:n_results]
        except Exception as e:
            logger.warning(f"RAG 查询失败: {e}")
            return self._fallback_search(city, query_text, n_results)

    def _fallback_search(self, city: str, query_text: str, n_results: int) -> list[str]:
        """内置匹配回退"""
        results = []
        for item in TRAVEL_KNOWLEDGE:
            if item["city"] in (city, "通用"):
                if query_text:
                    # 简单关键词匹配
                    if any(w in item["content"] for w in query_text):
                        results.append(item["content"])
                else:
                    results.append(item["content"])

        if not results:
            # 返回通用知识
            results = [item["content"] for item in TRAVEL_KNOWLEDGE if item["city"] == "通用"]

        return results[:n_results]


# 全局单例
rag_service = RAGService()
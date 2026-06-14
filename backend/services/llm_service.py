"""
LLM 工厂
支持 DeepSeek / OpenAI / 通义千问
"""
from langchain_openai import ChatOpenAI
from backend.config import get_settings

settings = get_settings()


def create_llm(temperature: float = 0.7) -> ChatOpenAI:
    """
    创建 LLM 实例
    通过 .env 中的 LLM_MODEL / LLM_BASE_URL / LLM_API_KEY 配置
    默认使用 DeepSeek（兼容 OpenAI 格式）
    """
    # 从环境变量读取，兼容多种配置方式
    import os
    
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "sk-placeholder"
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
    model = os.getenv("LLM_MODEL") or "deepseek-chat"

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )

"""
配置管理模块
使用 pydantic-settings 从 .env 文件加载配置
提供类型安全的环境变量访问
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """应用全局配置"""

    # ===== 高德地图 =====
    amap_web_api_key: str = ""
    amap_base_url: str = "https://restapi.amap.com/v3"

    # ===== 服务配置 =====
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    # ===== 请求配置 =====
    http_timeout: int = 15          # 高德 API 超时（秒）
    max_retries: int = 2            # 失败重试次数

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    agent_max_iterations: int = 15

@lru_cache()
def get_settings() -> Settings:
    """获取配置单例（带缓存）"""
    return Settings()

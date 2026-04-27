from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WinBid-AI Backend"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./winbid.db"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "qwen-plus"
    openai_timeout_seconds: float = 60.0
    openai_enable_draft_generation: bool = False
    openai_enable_agent_decision: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_prefix="WINBID_")


@lru_cache
def get_settings() -> Settings:
    return Settings()

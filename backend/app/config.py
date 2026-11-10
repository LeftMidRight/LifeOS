from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lifeos_port: int = 8787
    lifeos_database_url: str
    lifeos_test_database_url: str | None = None
    # 使用 LIFEOS_ 前缀，避免与本机其他工具的 LLM_* 环境变量冲突
    lifeos_llm_api_key: str = ""
    lifeos_llm_base_url: str = "https://api.deepseek.com/v1"
    lifeos_llm_model: str = "deepseek-chat"
    lifeos_llm_session_id: str = "lifeos"
    web_dist: str | None = None

    @property
    def safe_database_url(self) -> str:
        return make_url(self.lifeos_database_url).render_as_string(hide_password=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

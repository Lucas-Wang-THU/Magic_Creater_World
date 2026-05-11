from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    worlds_dir: Path = Path("worlds")
    paratera_api_key: str = ""
    openai_api_base: str = "https://llmapi.paratera.com/v1"
    openai_chat_model: str = "DeepSeek-V4-Flash"
    # 可选：「板块结构化同步」专用模型；留空则与 OPENAI_CHAT_MODEL 相同
    structure_sync_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def api_key() -> str | None:
    key = get_settings().paratera_api_key.strip()
    return key or None

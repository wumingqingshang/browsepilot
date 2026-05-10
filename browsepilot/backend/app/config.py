"""Application configuration via pydantic-settings."""

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pydantic import model_validator
from pydantic_settings import BaseSettings

# Explicit .env loading
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    logger.warning(".env not found at {}", ENV_PATH)


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_vision_enabled: bool = False
    mcp_server_url: str = "http://localhost:8090/mcp"
    mcp_server_port: int = 8090
    mcp_mode: str = "sse"
    browser_headless: bool = True
    browser_channel: str = ""
    browser_timeout: int = 15000
    allowed_domains: str = "github.com,baidu.com,wikipedia.org"
    log_level: str = "INFO"
    data_dir: str = "data"
    session_ttl_minutes: int = 60

    @model_validator(mode="after")
    def check_critical(self):
        if not self.openai_api_key.strip():
            raise ValueError(
                "OPENAI_API_KEY is required. "
                "Set it in .env or as an environment variable."
            )
        return self

    class Config:
        env_file = str(ENV_PATH)
        env_file_encoding = "utf-8"


settings = Settings()

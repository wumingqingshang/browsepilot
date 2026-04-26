"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_vision_enabled: bool = False
    mcp_server_url: str = "http://localhost:8090"
    mcp_server_port: int = 8090
    mcp_mode: str = "sse"
    browser_headless: bool = True
    browser_timeout: int = 15000
    allowed_domains: str = "github.com,baidu.com,wikipedia.org"
    log_level: str = "INFO"
    data_dir: str = "data"
    session_ttl_minutes: int = 60

    class Config:
        env_file = ".env"


settings = Settings()

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mcp_server_url: str = Field(
        default="https://order-mcp-74afyau24q-uc.a.run.app/mcp",
        alias="MCP_SERVER_URL",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    max_tool_rounds: int = Field(default=4, alias="MAX_TOOL_ROUNDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: list[str] = Field(default=["http://localhost:5173"], alias="CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()

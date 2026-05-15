from functools import lru_cache
from typing import Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GmailAccount(BaseModel):
    name: str
    email: str
    password: str  # App Password de Google


class Settings(BaseSettings):
    auth_secret: str = "change-me-please"
    auth_username: str = "jorge"
    auth_password: str = "change-me-please"

    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"

    workspace_path: str = "/opt/openclaw/workspace"
    debug: bool = False

    gmail_accounts: list[GmailAccount] = []

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

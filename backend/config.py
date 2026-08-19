from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings
from openai import AsyncOpenAI


class GmailAccount(BaseModel):
    name: str
    email: str
    password: str  # App Password de Google


class Settings(BaseSettings):
    auth_secret: str = "change-me-please"
    auth_username: str = "jorge"
    auth_password: str = "change-me-please"

    # OpenAI — motor único de Alex
    openai_api_key: Optional[str] = None
    alex_model: str = "gpt-5.6-luna"
    alex_complex_model: str = "gpt-5.6-terra"
    english_model: str = "gpt-5.6-luna"
    transcription_model: str = "gpt-4o-mini-transcribe"
    user_timezone: str = "Europe/Madrid"

    workspace_path: str = "/opt/openclaw/workspace"
    debug: bool = False

    gmail_accounts: list[GmailAccount] = []

    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    supabase_service_key: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_openai_client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(api_key=s.openai_api_key)

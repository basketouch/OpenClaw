from functools import lru_cache
from typing import Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GmailAccount(BaseModel):
    name: str
    email: str
    password: str  # App Password de Google


class WhatsAppContact(BaseModel):
    name: str
    phone: str  # número completo con código de país, ej: 34612345678


class Settings(BaseSettings):
    auth_secret: str = "change-me-please"
    auth_username: str = "jorge"
    auth_password: str = "change-me-please"

    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"

    workspace_path: str = "/opt/openclaw/workspace"
    debug: bool = False

    gmail_accounts: list[GmailAccount] = []

    waha_url: str = "http://waha:3000"
    waha_session: str = "default"
    waha_api_key: Optional[str] = None
    whatsapp_contacts: list[WhatsAppContact] = []
    tts_voice: str = "es-ES-AlvaroNeural"

    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

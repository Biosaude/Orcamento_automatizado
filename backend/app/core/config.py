"""Configuração declarativa. Ler estas opções não abre nenhuma conexão."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BIOSAUDE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    locaweb_smtp_host: str | None = None
    locaweb_smtp_port: int = Field(default=587, ge=1, le=65535)
    locaweb_smtp_username: str | None = None
    locaweb_smtp_password: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    twilio_account_sid: SecretStr | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_from_number: str | None = None
    sao_camilo_table_id: str | None = None

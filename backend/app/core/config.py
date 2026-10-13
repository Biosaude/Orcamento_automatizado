"""Configuração declarativa. Ler estas opções não abre nenhuma conexão."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BIOSAUDE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    database_ssl_root_cert: str = "/etc/ssl/certs/ca-certificates.crt"
    database_connect_timeout: int = Field(default=5, ge=1, le=30)
    database_statement_timeout_ms: int = Field(default=5000, ge=1, le=30000)
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=0, ge=0, le=20)
    database_pool_timeout: int = Field(default=5, ge=1, le=30)
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

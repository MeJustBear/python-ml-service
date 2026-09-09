"""Конфигурация сервиса: переменные окружения с префиксом ``MLWRAP_``."""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Разбираем эти поля сами: пустая переменная окружения должна давать пустое значение,
# а не ошибку разбора JSON.
StrList = Annotated[list[str], NoDecode]
JsonMapping = Annotated[dict[str, Any], NoDecode]


class AuthMode(StrEnum):
    NONE = "none"
    BASIC = "basic"
    JWT = "jwt"


class LogFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MLWRAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    app_name: str = "mlwrap"
    environment: str = "local"
    debug: bool = False
    root_path: str = ""
    api_prefix: str = "/api/v1"

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE
    access_log: bool = True

    auth_mode: AuthMode = AuthMode.NONE
    auth_users: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)
    auth_realm: str = "mlwrap"
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60
    jwt_issuer: str = "mlwrap"

    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    metrics_protected: bool = False

    plugin_modules: StrList = Field(default_factory=list)
    plugin_autodiscover: bool = True
    preload_models: StrList = Field(default_factory=list)
    auto_load: bool = True
    models_config: JsonMapping = Field(default_factory=dict)
    predict_timeout_seconds: float = 60.0

    database_url: str | None = None
    db_echo: bool = False
    db_pool_size: int = 5
    db_auto_create: bool = False
    persist_inferences: bool = True
    persist_payloads: bool = False
    payload_max_chars: int = 4000
    stats_window_size: int = 1000

    @field_validator("plugin_modules", "preload_models", mode="before")
    @classmethod
    def _split_list(cls, value: Any) -> Any:
        """Принимает и JSON-массив, и строку через запятую."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @field_validator("auth_users", "models_config", mode="before")
    @classmethod
    def _parse_mapping(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            return json.loads(text) if text else {}
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check_auth(self) -> Settings:
        if self.auth_mode is not AuthMode.NONE and not self.auth_users:
            raise ValueError(
                f"auth_mode={self.auth_mode.value} требует непустой MLWRAP_AUTH_USERS "
                'в формате {"user": "password"}'
            )
        if self.auth_mode is AuthMode.JWT and not self.jwt_secret:
            raise ValueError("auth_mode=jwt требует MLWRAP_JWT_SECRET")
        return self

    @property
    def database_enabled(self) -> bool:
        return bool(self.database_url)

    def config_for(self, model_name: str) -> dict[str, Any]:
        return self.models_config.get(model_name, {})


@lru_cache
def get_settings() -> Settings:
    return Settings()

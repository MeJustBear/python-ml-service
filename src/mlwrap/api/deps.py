"""Зависимости FastAPI: достают инфраструктуру из ``app.state``."""

from fastapi import Request

from mlwrap.config import Settings
from mlwrap.db.session import Database
from mlwrap.registry.runtime import ModelRuntime


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_runtime(request: Request) -> ModelRuntime:
    return request.app.state.runtime


def get_database(request: Request) -> Database | None:
    return request.app.state.database


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)

"""Общий контракт провайдеров аутентификации."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastapi import APIRouter


@dataclass(frozen=True)
class Principal:
    """Кто выполняет запрос."""

    subject: str
    auth_mode: str
    claims: dict[str, Any] = field(default_factory=dict)


class AuthProvider(Protocol):
    """Провайдер аутентификации, выбранный при запуске сервиса."""

    mode: str

    def dependency(self) -> Callable[..., Any]:
        """FastAPI-зависимость, возвращающая :class:`Principal`."""

    def router(self, prefix: str) -> APIRouter | None:
        """Дополнительные роуты режима (например, выдача токена)."""

"""Хранилище пользователей для basic- и jwt-режимов."""

import hmac
from collections.abc import Mapping

import bcrypt
import structlog

logger = structlog.get_logger(__name__)


class UserStore:
    """Пользователи из конфигурации: значение — либо пароль, либо bcrypt-хеш."""

    def __init__(self, users: Mapping[str, str]) -> None:
        self._users = dict(users)

    def __len__(self) -> int:
        return len(self._users)

    def __contains__(self, username: object) -> bool:
        return username in self._users

    def verify(self, username: str, password: str) -> bool:
        secret = self._users.get(username)
        if secret is None:
            # Сверяем всё равно, чтобы время ответа не выдавало существование логина.
            hmac.compare_digest(password.encode(), password.encode())
            return False
        if secret.startswith(("$2a$", "$2b$", "$2y$")):
            try:
                return bcrypt.checkpw(password.encode(), secret.encode())
            except ValueError:
                logger.warning("auth.bad_bcrypt_hash", user=username)
                return False
        return hmac.compare_digest(password.encode(), secret.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

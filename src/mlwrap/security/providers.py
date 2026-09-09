"""Три режима аутентификации: без проверки, HTTP Basic и JWT."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
)
from pydantic import BaseModel

from mlwrap.security.base import Principal
from mlwrap.security.users import UserStore

logger = structlog.get_logger(__name__)

ANONYMOUS = Principal(subject="anonymous", auth_mode="none")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class NoAuthProvider:
    """Ничего не проверяет — режим для локальных прогонов."""

    mode = "none"

    def dependency(self) -> Callable[..., Any]:
        async def _principal() -> Principal:
            return ANONYMOUS

        return _principal

    def router(self, prefix: str) -> APIRouter | None:
        return None


class BasicAuthProvider:
    """HTTP Basic по пользователям из конфигурации."""

    mode = "basic"

    def __init__(self, users: UserStore, realm: str = "mlwrap") -> None:
        self._users = users
        self._scheme = HTTPBasic(realm=realm, description="Логин и пароль из MLWRAP_AUTH_USERS")

    def dependency(self) -> Callable[..., Any]:
        users = self._users
        scheme = self._scheme

        async def _principal(
            credentials: HTTPBasicCredentials = Depends(scheme),
        ) -> Principal:
            if not users.verify(credentials.username, credentials.password):
                logger.info("auth.basic_rejected", user=credentials.username)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Неверный логин или пароль",
                    headers={"WWW-Authenticate": "Basic"},
                )
            return Principal(subject=credentials.username, auth_mode="basic")

        return _principal

    def router(self, prefix: str) -> APIRouter | None:
        return None


class JWTAuthProvider:
    """Bearer-токены HS256; ``/auth/token`` меняет логин/пароль на токен."""

    mode = "jwt"

    def __init__(
        self,
        users: UserStore,
        *,
        secret: str,
        algorithm: str = "HS256",
        ttl_minutes: int = 60,
        issuer: str = "mlwrap",
        token_url: str = "/api/v1/auth/token",
    ) -> None:
        self._users = users
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = timedelta(minutes=ttl_minutes)
        self._issuer = issuer
        self._scheme = OAuth2PasswordBearer(tokenUrl=token_url, auto_error=True)

    def issue_token(self, subject: str) -> TokenResponse:
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": self._issuer,
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return TokenResponse(access_token=token, expires_in=int(self._ttl.total_seconds()))

    def decode(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._secret,
            algorithms=[self._algorithm],
            issuer=self._issuer,
            options={"require": ["exp", "sub"]},
        )

    def dependency(self) -> Callable[..., Any]:
        scheme = self._scheme
        decode = self.decode

        async def _principal(token: str = Depends(scheme)) -> Principal:
            try:
                claims = decode(token)
            except jwt.ExpiredSignatureError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Срок действия токена истёк",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            except jwt.InvalidTokenError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Некорректный токен",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            return Principal(subject=str(claims["sub"]), auth_mode="jwt", claims=claims)

        return _principal

    def router(self, prefix: str) -> APIRouter | None:
        router = APIRouter(prefix=prefix, tags=["auth"])
        users = self._users
        issue_token = self.issue_token

        @router.post("/auth/token", response_model=TokenResponse, summary="Получить JWT")
        async def token(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
            if not users.verify(form.username, form.password):
                logger.info("auth.token_rejected", user=form.username)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Неверный логин или пароль",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return issue_token(form.username)

        return router

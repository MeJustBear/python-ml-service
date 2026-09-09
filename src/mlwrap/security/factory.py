"""Выбор провайдера аутентификации по конфигурации запуска."""

from mlwrap.config import AuthMode, Settings
from mlwrap.errors import ConfigurationError
from mlwrap.security.base import AuthProvider
from mlwrap.security.providers import BasicAuthProvider, JWTAuthProvider, NoAuthProvider
from mlwrap.security.users import UserStore


def build_auth_provider(settings: Settings) -> AuthProvider:
    if settings.auth_mode is AuthMode.NONE:
        return NoAuthProvider()

    users = UserStore(settings.auth_users)
    if not users:
        raise ConfigurationError(
            f"Режим аутентификации '{settings.auth_mode.value}' требует MLWRAP_AUTH_USERS"
        )

    if settings.auth_mode is AuthMode.BASIC:
        return BasicAuthProvider(users, realm=settings.auth_realm)

    if settings.auth_mode is AuthMode.JWT:
        if not settings.jwt_secret:
            raise ConfigurationError("Режим аутентификации 'jwt' требует MLWRAP_JWT_SECRET")
        return JWTAuthProvider(
            users,
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            ttl_minutes=settings.jwt_ttl_minutes,
            issuer=settings.jwt_issuer,
            token_url=f"{settings.api_prefix}/auth/token",
        )

    raise ConfigurationError(f"Неизвестный режим аутентификации: {settings.auth_mode}")

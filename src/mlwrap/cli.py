"""CLI: ``mlwrap serve|models|migrate|initdb|token|hash-password``.

Флаги — это тонкая обёртка над переменными окружения ``MLWRAP_*``: их выставляют до создания
Settings, поэтому режим аутентификации и набор плагинов выбираются одной командой запуска.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from mlwrap import __version__


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args) or 0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlwrap", description="FastAPI-обёртка для ML-моделей")
    parser.add_argument("-V", "--version", action="version", version=f"mlwrap {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Запустить HTTP-сервис")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument(
        "--auth",
        choices=["none", "basic", "jwt"],
        default=None,
        help="Режим аутентификации",
    )
    serve.add_argument(
        "--user",
        action="append",
        default=None,
        metavar="LOGIN:PASSWORD",
        help="Пользователь для basic/jwt; можно повторять",
    )
    serve.add_argument("--jwt-secret", default=None)
    serve.add_argument(
        "--plugin",
        action="append",
        default=None,
        metavar="MODULE",
        help="Модуль с моделями; можно повторять",
    )
    serve.add_argument(
        "--preload",
        action="append",
        default=None,
        metavar="MODEL",
        help="Загрузить модель на старте; можно повторять",
    )
    serve.add_argument("--database-url", default=None)
    serve.add_argument("--log-level", default=None)
    serve.add_argument("--log-format", choices=["console", "json"], default=None)
    serve.add_argument("--workers", type=int, default=None)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(handler=_cmd_serve)

    models = subparsers.add_parser("models", help="Показать зарегистрированные модели")
    models.add_argument("--plugin", action="append", default=None, metavar="MODULE")
    models.add_argument("--json", action="store_true", dest="as_json")
    models.set_defaults(handler=_cmd_models)

    migrate = subparsers.add_parser("migrate", help="Применить миграции Alembic")
    migrate.add_argument("--revision", default="head")
    migrate.set_defaults(handler=_cmd_migrate)

    initdb = subparsers.add_parser("initdb", help="Создать таблицы без Alembic")
    initdb.set_defaults(handler=_cmd_initdb)

    token = subparsers.add_parser("token", help="Выпустить JWT для тестов")
    token.add_argument("subject")
    token.add_argument("--ttl-minutes", type=int, default=None)
    token.set_defaults(handler=_cmd_token)

    hash_cmd = subparsers.add_parser("hash-password", help="Посчитать bcrypt-хеш пароля")
    hash_cmd.add_argument("password", nargs="?")
    hash_cmd.set_defaults(handler=_cmd_hash_password)

    return parser


def _cmd_serve(args: argparse.Namespace) -> int:
    _apply_env(args)
    settings = _fresh_settings()

    import uvicorn

    uvicorn.run(
        "mlwrap.app:app_factory",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        workers=None if args.reload else settings.workers,
        log_level=settings.log_level.lower(),
        access_log=False,  # доступ логирует ObservabilityMiddleware
    )
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    _apply_env(args)
    settings = _fresh_settings()

    from mlwrap.logging import configure_logging
    from mlwrap.registry import discover, registry

    configure_logging(settings.log_level, settings.log_format)

    discover(settings.plugin_modules, autodiscover=settings.plugin_autodiscover)
    rows: list[dict[str, Any]] = [
        {
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "requires_load": spec.requires_load,
            "has_metrics": spec.metrics_fn is not None,
        }
        for spec in registry.specs()
    ]
    if args.as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("Моделей не зарегистрировано")
        return 0
    width = max(len(row["name"]) for row in rows)
    for row in rows:
        flags = ",".join(
            filter(
                None,
                ["load" if row["requires_load"] else "", "metrics" if row["has_metrics"] else ""],
            )
        )
        print(f"{row['name']:<{width}}  {row['version']:<8} [{flags}]  {row['description']}")
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    settings = _fresh_settings()
    if not settings.database_url:
        print("MLWRAP_DATABASE_URL не задан — миграции не нужны", file=sys.stderr)
        return 1

    from alembic import command
    from alembic.config import Config

    config = Config(str(_alembic_ini()))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, args.revision)
    return 0


def _cmd_initdb(args: argparse.Namespace) -> int:
    settings = _fresh_settings()
    if not settings.database_url:
        print("MLWRAP_DATABASE_URL не задан", file=sys.stderr)
        return 1

    from mlwrap.db.session import Database

    async def run() -> None:
        database = Database(settings.database_url or "")
        try:
            await database.create_all()
        finally:
            await database.dispose()

    asyncio.run(run())
    print("Таблицы созданы")
    return 0


def _cmd_token(args: argparse.Namespace) -> int:
    settings = _fresh_settings()
    if not settings.jwt_secret:
        print("MLWRAP_JWT_SECRET не задан", file=sys.stderr)
        return 1

    from mlwrap.security.providers import JWTAuthProvider
    from mlwrap.security.users import UserStore

    provider = JWTAuthProvider(
        UserStore({}),
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        ttl_minutes=args.ttl_minutes or settings.jwt_ttl_minutes,
        issuer=settings.jwt_issuer,
    )
    print(provider.issue_token(args.subject).access_token)
    return 0


def _cmd_hash_password(args: argparse.Namespace) -> int:
    from mlwrap.security.users import hash_password

    password = args.password or getpass.getpass("Пароль: ")
    print(hash_password(password))
    return 0


def _apply_env(args: argparse.Namespace) -> None:
    mapping: dict[str, Any] = {
        "MLWRAP_HOST": getattr(args, "host", None),
        "MLWRAP_PORT": getattr(args, "port", None),
        "MLWRAP_AUTH_MODE": getattr(args, "auth", None),
        "MLWRAP_JWT_SECRET": getattr(args, "jwt_secret", None),
        "MLWRAP_DATABASE_URL": getattr(args, "database_url", None),
        "MLWRAP_LOG_LEVEL": getattr(args, "log_level", None),
        "MLWRAP_LOG_FORMAT": getattr(args, "log_format", None),
        "MLWRAP_WORKERS": getattr(args, "workers", None),
    }
    users = getattr(args, "user", None)
    if users:
        mapping["MLWRAP_AUTH_USERS"] = json.dumps(dict(_parse_user(item) for item in users))
    plugins = getattr(args, "plugin", None)
    if plugins:
        mapping["MLWRAP_PLUGIN_MODULES"] = json.dumps(plugins)
    preload = getattr(args, "preload", None)
    if preload:
        mapping["MLWRAP_PRELOAD_MODELS"] = json.dumps(preload)

    for key, value in mapping.items():
        if value is not None:
            os.environ[key] = str(value)


def _parse_user(raw: str) -> tuple[str, str]:
    login, separator, password = raw.partition(":")
    if not separator or not login:
        raise SystemExit(f"--user должен быть в формате LOGIN:PASSWORD, получено: {raw!r}")
    return login, password


def _fresh_settings() -> Any:
    from mlwrap.config import Settings, get_settings

    get_settings.cache_clear()
    return Settings()


def _alembic_ini() -> Path:
    candidates = [
        Path.cwd() / "alembic.ini",
        Path(__file__).resolve().parents[2] / "alembic.ini",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit("Не найден alembic.ini")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

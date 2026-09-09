"""Фабрика FastAPI-приложения: собирает аутентификацию, реестр моделей, метрики и БД."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mlwrap import __version__
from mlwrap.api import build_auth_router, build_models_router, build_system_router
from mlwrap.config import Settings, get_settings
from mlwrap.db import repository
from mlwrap.db.session import build_database
from mlwrap.errors import MLWrapError
from mlwrap.logging import configure_logging
from mlwrap.observability import metrics as prom
from mlwrap.observability.middleware import ObservabilityMiddleware
from mlwrap.registry import ModelRegistry, ModelRuntime, discover
from mlwrap.registry import registry as default_registry
from mlwrap.schemas import ErrorResponse
from mlwrap.security import build_auth_provider

logger = structlog.get_logger(__name__)

DESCRIPTION = """
Обёртка для быстрых тестов ML-моделей.

Модель подключается тремя функциями — загрузка, инференс, метрики, — которые регистрируются
в реестре по имени модели. Эндпоинты ниже уже готовы и работают для любой такой модели.
""".strip()


def create_app(
    settings: Settings | None = None,
    *,
    model_registry: ModelRegistry | None = None,
    configure_logs: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    if configure_logs:
        configure_logging(settings.log_level, settings.log_format)

    registry = model_registry or default_registry
    imported = discover(settings.plugin_modules, autodiscover=settings.plugin_autodiscover)
    registry.validate()
    logger.info(
        "app.registry_ready",
        modules=imported,
        models=registry.names(),
        auth_mode=settings.auth_mode.value,
    )

    auth_provider = build_auth_provider(settings)
    auth_dependency = auth_provider.dependency()
    database = build_database(settings)
    runtime = ModelRuntime(registry, settings)
    if database is not None:
        runtime.event_hook = _make_event_hook(database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if database is not None and settings.db_auto_create:
            await database.create_all()
        for name in settings.preload_models:
            try:
                await runtime.load(name)
            except MLWrapError as exc:
                logger.error("app.preload_failed", model=name, error=exc.message)
        yield
        await runtime.shutdown()
        if database is not None:
            await database.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        root_path=settings.root_path,
        debug=settings.debug,
    )
    app.state.settings = settings
    app.state.runtime = runtime
    app.state.database = database
    app.state.auth_provider = auth_provider

    app.add_middleware(
        ObservabilityMiddleware,
        access_log=settings.access_log,
        metrics_enabled=settings.metrics_enabled,
    )
    _register_exception_handlers(app)

    app.include_router(build_system_router(settings, auth_dependency))
    provider_router = auth_provider.router(settings.api_prefix)
    if provider_router is not None:
        app.include_router(provider_router)
    app.include_router(build_auth_router(settings.api_prefix, auth_dependency))
    app.include_router(
        build_models_router(auth_dependency, prefix=settings.api_prefix, runtime=runtime)
    )

    prom.set_app_info(__version__, settings.environment, settings.auth_mode.value)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MLWrapError)
    async def handle_domain_error(request: Request, exc: MLWrapError) -> JSONResponse:
        body = ErrorResponse(
            error=exc.code,
            detail=exc.message,
            request_id=getattr(request.state, "request_id", None),
            details=exc.details or None,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(
            error="invalid_payload",
            detail="Тело запроса не соответствует схеме",
            request_id=getattr(request.state, "request_id", None),
            details={"errors": jsonable_errors(exc)},
        )
        return JSONResponse(status_code=422, content=body.model_dump())


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        cleaned = {key: value for key, value in error.items() if key != "ctx"}
        cleaned["loc"] = [str(part) for part in error.get("loc", ())]
        errors.append(cleaned)
    return errors


def _make_event_hook(database: Any) -> Any:
    async def hook(
        event: str, model_name: str, duration_ms: float | None, details: dict[str, Any]
    ) -> None:
        async with database.session() as session:
            await repository.record_model_event(
                session,
                model_name=model_name,
                event=event,
                duration_ms=duration_ms,
                details=details or None,
            )

    return hook


def app_factory() -> FastAPI:
    """Точка входа для ``uvicorn mlwrap.app:app_factory --factory``."""
    return create_app()

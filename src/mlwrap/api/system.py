"""Системные эндпоинты: информация о сервисе, health-проверки, метрики, текущий субъект."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Response

from mlwrap import __version__
from mlwrap.api.deps import get_database, get_runtime, get_settings
from mlwrap.config import Settings
from mlwrap.db.session import Database
from mlwrap.observability import metrics as prom
from mlwrap.registry.runtime import ModelRuntime, ModelState
from mlwrap.schemas import HealthResponse, PrincipalInfo, ServiceInfo
from mlwrap.security.base import Principal


def build_system_router(settings: Settings, auth_dependency: Callable[..., Any]) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/", response_model=ServiceInfo, summary="Информация о сервисе")
    async def service_info(
        runtime: ModelRuntime = Depends(get_runtime),
        settings: Settings = Depends(get_settings),
    ) -> ServiceInfo:
        return ServiceInfo(
            name=settings.app_name,
            version=__version__,
            environment=settings.environment,
            auth_mode=settings.auth_mode.value,
            api_prefix=settings.api_prefix,
            docs_url="/docs",
            metrics_url=settings.metrics_path if settings.metrics_enabled else None,
            models=runtime.registry.names(),
        )

    @router.get("/health/live", response_model=HealthResponse, summary="Живость процесса")
    async def health_live() -> HealthResponse:
        return HealthResponse(status="ok", checks={"process": "ok"})

    @router.get("/health/ready", response_model=HealthResponse, summary="Готовность к работе")
    async def health_ready(
        runtime: ModelRuntime = Depends(get_runtime),
        database: Database | None = Depends(get_database),
    ) -> HealthResponse:
        checks: dict[str, str] = {}
        if database is None:
            checks["database"] = "disabled"
        else:
            checks["database"] = "ok" if await database.healthcheck() else "error"

        failed = [
            handle.spec.name for handle in runtime.handles() if handle.state is ModelState.FAILED
        ]
        checks["models"] = "error: " + ", ".join(failed) if failed else "ok"

        degraded = any(value.startswith("error") for value in checks.values())
        return HealthResponse(status="degraded" if degraded else "ok", checks=checks)

    if settings.metrics_enabled:
        dependencies = [Depends(auth_dependency)] if settings.metrics_protected else []

        @router.get(
            settings.metrics_path,
            summary="Метрики Prometheus",
            dependencies=dependencies,
            response_class=Response,
            responses={200: {"content": {"text/plain": {}}}},
        )
        async def metrics_endpoint(runtime: ModelRuntime = Depends(get_runtime)) -> Response:
            for handle in runtime.handles():
                if handle.state is ModelState.READY and handle.spec.metrics_fn is not None:
                    await runtime.custom_metrics(handle.spec.name)
            payload, content_type = prom.render()
            return Response(content=payload, media_type=content_type)

    return router


def build_auth_router(prefix: str, auth_dependency: Callable[..., Any]) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["auth"])

    @router.get("/auth/me", response_model=PrincipalInfo, summary="Текущий субъект")
    async def whoami(principal: Principal = Depends(auth_dependency)) -> PrincipalInfo:
        return PrincipalInfo(
            subject=principal.subject,
            auth_mode=principal.auth_mode,
            claims=principal.claims,
        )

    return router

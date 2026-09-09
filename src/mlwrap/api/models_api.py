"""Готовые эндпоинты, одинаковые для любой зарегистрированной модели."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Request
from pydantic import TypeAdapter

from mlwrap.api.deps import get_database, get_request_id, get_runtime, get_settings
from mlwrap.api.dynamic import ERROR_RESPONSES, add_typed_model_routes
from mlwrap.api.inference import run_predict
from mlwrap.config import Settings
from mlwrap.db import repository
from mlwrap.db.session import Database
from mlwrap.registry.runtime import ModelRuntime, ModelState
from mlwrap.schemas import (
    BatchPredictResponse,
    ModelInfo,
    ModelMetricsResponse,
    ModelSchemaInfo,
    PredictResponse,
)
from mlwrap.security.base import Principal


def build_models_router(
    auth_dependency: Callable[..., Any],
    *,
    prefix: str,
    runtime: ModelRuntime,
) -> APIRouter:
    router = APIRouter(prefix=prefix, dependencies=[Depends(auth_dependency)])

    # Типизированные роуты регистрируются первыми: конкретный путь должен выиграть у шаблонного.
    for spec in runtime.registry.specs():
        add_typed_model_routes(router, spec, auth_dependency)

    generic = APIRouter(tags=["models"])

    @generic.get("/models", response_model=list[ModelInfo], summary="Список моделей")
    async def list_models(runtime: ModelRuntime = Depends(get_runtime)) -> list[ModelInfo]:
        return [ModelInfo.from_handle(handle) for handle in runtime.handles()]

    @generic.get(
        "/models/{model_name}",
        response_model=ModelInfo,
        responses=ERROR_RESPONSES,
        summary="Состояние модели",
    )
    async def get_model(model_name: str, runtime: ModelRuntime = Depends(get_runtime)) -> ModelInfo:
        return ModelInfo.from_handle(runtime.handle(model_name))

    @generic.get(
        "/models/{model_name}/schema",
        response_model=ModelSchemaInfo,
        responses=ERROR_RESPONSES,
        summary="Схемы запроса и ответа модели",
    )
    async def get_model_schema(
        model_name: str, runtime: ModelRuntime = Depends(get_runtime)
    ) -> ModelSchemaInfo:
        spec = runtime.registry.spec(model_name)
        return ModelSchemaInfo(
            name=spec.name,
            version=spec.version,
            input_schema=_json_schema(spec.input_schema) or {},
            output_schema=_json_schema(spec.output_schema),
        )

    @generic.post(
        "/models/{model_name}/load",
        response_model=ModelInfo,
        responses=ERROR_RESPONSES,
        summary="Загрузить модель",
    )
    async def load_model(
        model_name: str,
        force: bool = Query(False, description="Перезагрузить, даже если уже готова"),
        runtime: ModelRuntime = Depends(get_runtime),
    ) -> ModelInfo:
        return ModelInfo.from_handle(await runtime.load(model_name, force=force))

    @generic.post(
        "/models/{model_name}/unload",
        response_model=ModelInfo,
        responses=ERROR_RESPONSES,
        summary="Выгрузить модель",
    )
    async def unload_model(
        model_name: str, runtime: ModelRuntime = Depends(get_runtime)
    ) -> ModelInfo:
        return ModelInfo.from_handle(await runtime.unload(model_name))

    @generic.post(
        "/models/{model_name}/predict",
        response_model=PredictResponse[Any],
        responses=ERROR_RESPONSES,
        summary="Инференс модели",
    )
    async def predict(
        model_name: str,
        request: Request,
        background: BackgroundTasks,
        payload: Any = Body(default_factory=dict),
        principal: Principal = Depends(auth_dependency),
        runtime: ModelRuntime = Depends(get_runtime),
        settings: Settings = Depends(get_settings),
        database: Database | None = Depends(get_database),
        request_id: str | None = Depends(get_request_id),
    ) -> dict[str, Any]:
        return await run_predict(
            model_name=model_name,
            payload=payload,
            runtime=runtime,
            settings=settings,
            database=database,
            background=background,
            principal=principal,
            request_id=request_id,
        )

    @generic.post(
        "/models/{model_name}/predict/batch",
        response_model=BatchPredictResponse[Any],
        responses=ERROR_RESPONSES,
        summary="Пакетный инференс модели",
    )
    async def predict_batch(
        model_name: str,
        request: Request,
        background: BackgroundTasks,
        payload: list[Any] = Body(default_factory=list),
        principal: Principal = Depends(auth_dependency),
        runtime: ModelRuntime = Depends(get_runtime),
        settings: Settings = Depends(get_settings),
        database: Database | None = Depends(get_database),
        request_id: str | None = Depends(get_request_id),
    ) -> dict[str, Any]:
        return await run_predict(
            model_name=model_name,
            payload=payload,
            runtime=runtime,
            settings=settings,
            database=database,
            background=background,
            principal=principal,
            request_id=request_id,
            batch=True,
        )

    @generic.get(
        "/models/{model_name}/metrics",
        response_model=ModelMetricsResponse,
        responses=ERROR_RESPONSES,
        summary="Метрики модели",
    )
    async def model_metrics(
        model_name: str,
        runtime: ModelRuntime = Depends(get_runtime),
        settings: Settings = Depends(get_settings),
        database: Database | None = Depends(get_database),
    ) -> ModelMetricsResponse:
        handle = runtime.handle(model_name)
        custom = await runtime.custom_metrics(model_name)
        history = None
        if database is not None:
            async with database.session() as session:
                history = await repository.inference_stats(
                    session, model_name, window=settings.stats_window_size
                )
        return ModelMetricsResponse(
            name=model_name,
            state=handle.state.value,
            runtime={
                "loaded": handle.state is ModelState.READY,
                "loaded_at": handle.loaded_at.isoformat() if handle.loaded_at else None,
                "load_duration_ms": handle.load_duration_ms,
                "predict_count": handle.predict_count,
                "error_count": handle.error_count,
                "avg_latency_ms": handle.avg_latency_ms,
                "last_latency_ms": handle.last_latency_ms,
                "last_called_at": (
                    handle.last_called_at.isoformat() if handle.last_called_at else None
                ),
            },
            custom=custom,
            history=history,
        )

    router.include_router(generic)
    return router


def _json_schema(schema: Any) -> dict[str, Any] | None:
    if schema is None:
        return None
    try:
        return TypeAdapter(schema).json_schema(ref_template="#/$defs/{model}")
    except Exception:
        return {"type": "object", "description": f"Схема недоступна для {schema!r}"}

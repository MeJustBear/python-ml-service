"""Генерация типизированных эндпоинтов под каждую зарегистрированную модель.

Путь и логика те же, что у общих роутов, но в OpenAPI подставлены реальные схемы модели,
поэтому Swagger показывает конкретное тело запроса, а не «любой JSON».
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from mlwrap.api.deps import get_database, get_runtime, get_settings
from mlwrap.api.inference import batch_schema, run_predict
from mlwrap.config import Settings
from mlwrap.db.session import Database
from mlwrap.registry.runtime import ModelRuntime
from mlwrap.registry.spec import ModelSpec
from mlwrap.schemas import BatchPredictResponse, ErrorResponse, PredictResponse
from mlwrap.security.base import Principal

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Не аутентифицирован"},
    404: {"model": ErrorResponse, "description": "Модель не зарегистрирована"},
    409: {"model": ErrorResponse, "description": "Модель не загружена"},
    422: {"model": ErrorResponse, "description": "Тело запроса не по схеме"},
    503: {"model": ErrorResponse, "description": "Не удалось загрузить модель"},
    504: {"model": ErrorResponse, "description": "Таймаут инференса"},
}


def add_typed_model_routes(
    router: APIRouter,
    spec: ModelSpec,
    auth_dependency: Callable[..., Any],
) -> None:
    output = spec.output_schema if spec.output_schema is not None else Any
    label = spec.description or f"модели '{spec.name}'"

    router.add_api_route(
        f"/models/{spec.name}/predict",
        _make_endpoint(spec, auth_dependency, batch=False),
        methods=["POST"],
        response_model=PredictResponse[output],  # type: ignore[valid-type]
        responses=ERROR_RESPONSES,
        tags=[f"model:{spec.name}"],
        summary=f"Инференс {label}",
        name=f"predict_{spec.name}",
    )
    router.add_api_route(
        f"/models/{spec.name}/predict/batch",
        _make_endpoint(spec, auth_dependency, batch=True),
        methods=["POST"],
        response_model=BatchPredictResponse[output],  # type: ignore[valid-type]
        responses=ERROR_RESPONSES,
        tags=[f"model:{spec.name}"],
        summary=f"Пакетный инференс {label}",
        name=f"predict_batch_{spec.name}",
    )


def _make_endpoint(
    spec: ModelSpec,
    auth_dependency: Callable[..., Any],
    *,
    batch: bool,
) -> Callable[..., Any]:
    payload_type: Any = spec.input_schema if spec.input_schema is not None else dict[str, Any]
    if batch:
        payload_type = batch_schema(payload_type)

    async def endpoint(
        request: Request,
        background: BackgroundTasks,
        payload: Any,
        principal: Principal,
        runtime: ModelRuntime,
        settings: Settings,
        database: Database | None,
    ) -> dict[str, Any]:
        return await run_predict(
            model_name=spec.name,
            payload=payload,
            runtime=runtime,
            settings=settings,
            database=database,
            background=background,
            principal=principal,
            request_id=getattr(request.state, "request_id", None),
            validate=False,
            batch=batch,
        )

    endpoint.__name__ = f"predict_batch_{spec.name}" if batch else f"predict_{spec.name}"
    endpoint.__doc__ = spec.description or None
    # Подменяем сигнатуру: FastAPI строит схему по ней, а тип payload известен только в рантайме.
    endpoint.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                "request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request
            ),
            inspect.Parameter(
                "background", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=BackgroundTasks
            ),
            inspect.Parameter(
                "payload", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=payload_type
            ),
            inspect.Parameter(
                "principal",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Principal,
                default=Depends(auth_dependency),
            ),
            inspect.Parameter(
                "runtime",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=ModelRuntime,
                default=Depends(get_runtime),
            ),
            inspect.Parameter(
                "settings",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Settings,
                default=Depends(get_settings),
            ),
            inspect.Parameter(
                "database",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=(Database | None),
                default=Depends(get_database),
            ),
        ]
    )
    return endpoint

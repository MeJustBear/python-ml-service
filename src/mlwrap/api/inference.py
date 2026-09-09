"""Общая реализация инференса для готовых и для сгенерированных эндпоинтов."""

from __future__ import annotations

import time
from functools import lru_cache
from types import GenericAlias
from typing import Any

import structlog
from fastapi import BackgroundTasks
from pydantic import TypeAdapter, ValidationError

from mlwrap.config import Settings
from mlwrap.db import repository
from mlwrap.db.session import Database
from mlwrap.errors import InvalidPayloadError, MLWrapError
from mlwrap.registry.runtime import ModelRuntime
from mlwrap.security.base import Principal
from mlwrap.serialization import to_jsonable, truncate

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=256)
def _adapter(schema: Any) -> TypeAdapter:
    return TypeAdapter(schema)


def batch_schema(schema: Any) -> Any:
    """``list[schema]`` для схемы, известной только в рантайме."""
    return GenericAlias(list, (schema,))


def validate_payload(schema: Any, payload: Any) -> Any:
    if schema is None:
        return payload
    try:
        return _adapter(schema).validate_python(payload)
    except ValidationError as exc:
        raise InvalidPayloadError(
            "Тело запроса не соответствует схеме модели",
            details={"errors": exc.errors(include_url=False)},
        ) from exc
    except TypeError:  # неподдерживаемая схема — пропускаем как есть
        return payload


async def run_predict(
    *,
    model_name: str,
    payload: Any,
    runtime: ModelRuntime,
    settings: Settings,
    database: Database | None,
    background: BackgroundTasks,
    principal: Principal,
    request_id: str | None,
    validate: bool = True,
    batch: bool = False,
) -> dict[str, Any]:
    spec = runtime.registry.spec(model_name)
    if validate:
        schema = batch_schema(spec.input_schema) if batch else spec.input_schema
        payload = validate_payload(schema, payload)

    batch_size = len(payload) if batch else 1
    started = time.perf_counter()
    try:
        outcome = (
            await runtime.predict_batch(model_name, list(payload))
            if batch
            else await runtime.predict(model_name, payload)
        )
    except MLWrapError as exc:
        # Ответ об ошибке формирует обработчик исключений, и background-задачи до него
        # не доживают — поэтому запись в журнал делаем сразу.
        await _record(
            database=database,
            settings=settings,
            model_name=model_name,
            model_version=spec.version,
            status="error",
            latency_ms=(time.perf_counter() - started) * 1000,
            batch_size=batch_size,
            error=f"{exc.code}: {exc.message}",
            request_id=request_id,
            principal=principal.subject,
            payload=payload,
            result=None,
        )
        raise

    result = to_jsonable(outcome.result)
    _schedule_record(
        background,
        database=database,
        settings=settings,
        model_name=model_name,
        model_version=spec.version,
        status="ok",
        latency_ms=outcome.latency_ms,
        batch_size=batch_size,
        error=None,
        request_id=request_id,
        principal=principal.subject,
        payload=payload,
        result=result,
    )

    body: dict[str, Any] = {
        "model": model_name,
        "version": spec.version,
        "latency_ms": round(outcome.latency_ms, 3),
        "request_id": request_id,
    }
    if batch:
        body["count"] = batch_size
        body["results"] = result
    else:
        body["result"] = result
    return body


def _schedule_record(background: BackgroundTasks, **kwargs: Any) -> None:
    """Журнал пишется после ответа клиенту, чтобы не удлинять инференс."""
    background.add_task(_record, **kwargs)


async def _record(
    *,
    database: Database | None,
    settings: Settings,
    payload: Any,
    result: Any,
    **fields: Any,
) -> None:
    """Ошибка записи в журнал не должна ломать инференс — только лог."""
    if database is None or not settings.persist_inferences:
        return

    stored_payload = stored_result = None
    if settings.persist_payloads:
        stored_payload = truncate(to_jsonable(payload), settings.payload_max_chars)
        stored_result = truncate(result, settings.payload_max_chars)

    try:
        async with database.session() as session:
            await repository.record_inference(
                session, payload=stored_payload, result=stored_result, **fields
            )
    except Exception as exc:
        logger.warning("db.inference_record_failed", error=str(exc))

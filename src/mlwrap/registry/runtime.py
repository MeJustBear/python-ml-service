"""Рантайм моделей: состояние, загрузка, инференс, сбор метрик."""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import anyio.to_thread
import structlog

from mlwrap.config import Settings
from mlwrap.errors import (
    ModelLoadError,
    ModelNotLoadedError,
    PredictionError,
    PredictionTimeoutError,
)
from mlwrap.observability import metrics as prom
from mlwrap.registry.registry import ModelRegistry
from mlwrap.registry.spec import ModelSpec

logger = structlog.get_logger(__name__)

EventHook = Callable[[str, str, float | None, dict[str, Any]], Awaitable[None]]


class ModelState(StrEnum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass
class ModelHandle:
    """Состояние одной модели внутри процесса."""

    spec: ModelSpec
    state: ModelState = ModelState.UNLOADED
    instance: Any = None
    loaded_at: datetime | None = None
    load_duration_ms: float | None = None
    error: str | None = None
    predict_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float | None = None
    last_called_at: datetime | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def avg_latency_ms(self) -> float | None:
        successful = self.predict_count - self.error_count
        if successful <= 0:
            return None
        return self.total_latency_ms / successful


@dataclass(slots=True)
class PredictOutcome:
    result: Any
    latency_ms: float


class ModelRuntime:
    """Единая точка работы с моделями: знает, что загружено, и умеет это вызывать."""

    def __init__(
        self,
        registry: ModelRegistry,
        settings: Settings,
        *,
        event_hook: EventHook | None = None,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._handles: dict[str, ModelHandle] = {}
        self.event_hook = event_hook

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    def handle(self, name: str) -> ModelHandle:
        spec = self._registry.spec(name)
        handle = self._handles.get(name)
        if handle is None or handle.spec is not spec:
            handle = ModelHandle(spec=spec)
            self._handles[name] = handle
            prom.MODEL_LOADED.labels(model=name).set(0)
        return handle

    def handles(self) -> list[ModelHandle]:
        return [self.handle(name) for name in self._registry.names()]

    async def load(self, name: str, *, force: bool = False) -> ModelHandle:
        handle = self.handle(name)
        async with handle.lock:
            if handle.state is ModelState.READY and not force:
                return handle
            if handle.state is ModelState.READY and force:
                await self._unload_locked(handle)

            spec = handle.spec
            if spec.loader is None:
                handle.state = ModelState.READY
                handle.instance = None
                handle.loaded_at = datetime.now(UTC)
                handle.load_duration_ms = 0.0
                handle.error = None
                prom.MODEL_LOADED.labels(model=name).set(1)
                return handle

            handle.state = ModelState.LOADING
            handle.error = None
            started = time.perf_counter()
            try:
                args = (self._settings.config_for(name),) if spec.loader_wants_config() else ()
                handle.instance = await _call(spec.loader, *args)
            except Exception as exc:
                duration_ms = (time.perf_counter() - started) * 1000
                handle.state = ModelState.FAILED
                handle.instance = None
                handle.error = f"{type(exc).__name__}: {exc}"
                prom.MODEL_LOADED.labels(model=name).set(0)
                prom.MODEL_LOAD_TOTAL.labels(model=name, status="error").inc()
                logger.error("model.load_failed", model=name, error=handle.error)
                await self._emit("load_failed", name, duration_ms, {"error": handle.error})
                raise ModelLoadError(
                    f"Не удалось загрузить модель '{name}': {handle.error}"
                ) from exc

            duration_ms = (time.perf_counter() - started) * 1000
            handle.state = ModelState.READY
            handle.loaded_at = datetime.now(UTC)
            handle.load_duration_ms = duration_ms
            prom.MODEL_LOADED.labels(model=name).set(1)
            prom.MODEL_LOAD_TOTAL.labels(model=name, status="ok").inc()
            prom.MODEL_LOAD_DURATION.labels(model=name).observe(duration_ms / 1000)
            logger.info("model.loaded", model=name, duration_ms=round(duration_ms, 2))
            await self._emit("load", name, duration_ms, {"version": spec.version})
            return handle

    async def unload(self, name: str) -> ModelHandle:
        handle = self.handle(name)
        async with handle.lock:
            await self._unload_locked(handle)
        await self._emit("unload", name, None, {})
        return handle

    async def _unload_locked(self, handle: ModelHandle) -> None:
        spec = handle.spec
        if spec.unloader is not None and handle.state is ModelState.READY:
            try:
                args = (handle.instance,) if spec.unloader_wants_model() else ()
                await _call(spec.unloader, *args)
            except Exception as exc:
                logger.warning("model.unload_failed", model=spec.name, error=str(exc))
        handle.instance = None
        handle.state = ModelState.UNLOADED
        handle.loaded_at = None
        handle.load_duration_ms = None
        prom.MODEL_LOADED.labels(model=spec.name).set(0)

    async def ensure_ready(self, name: str) -> ModelHandle:
        handle = self.handle(name)
        if handle.state is ModelState.READY:
            return handle
        if not self._settings.auto_load:
            raise ModelNotLoadedError(
                f"Модель '{name}' не загружена; вызовите POST /models/{name}/load"
            )
        return await self.load(name)

    async def predict(self, name: str, payload: Any) -> PredictOutcome:
        handle = await self.ensure_ready(name)
        spec = handle.spec
        if spec.predictor is None:  # pragma: no cover — отсекается registry.validate()
            raise PredictionError(f"У модели '{name}' нет функции инференса")

        timeout = self._settings.predict_timeout_seconds or None
        prom.PREDICT_IN_PROGRESS.labels(model=name).inc()
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                _call(spec.predictor, handle.instance, payload), timeout
            )
        except TimeoutError as exc:
            self._record_failure(handle, started)
            raise PredictionTimeoutError(
                f"Инференс модели '{name}' не уложился в {timeout} с"
            ) from exc
        except Exception as exc:
            self._record_failure(handle, started)
            logger.error("model.predict_failed", model=name, error=str(exc))
            raise PredictionError(f"Ошибка инференса модели '{name}': {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        prom.PREDICT_IN_PROGRESS.labels(model=name).dec()
        prom.PREDICT_TOTAL.labels(model=name, status="ok").inc()
        prom.PREDICT_LATENCY.labels(model=name).observe(latency_ms / 1000)
        handle.predict_count += 1
        handle.total_latency_ms += latency_ms
        handle.last_latency_ms = latency_ms
        handle.last_called_at = datetime.now(UTC)
        return PredictOutcome(result=result, latency_ms=latency_ms)

    async def predict_batch(self, name: str, payloads: list[Any]) -> PredictOutcome:
        prom.PREDICT_BATCH_SIZE.labels(model=name).observe(len(payloads))
        started = time.perf_counter()
        results = [(await self.predict(name, payload)).result for payload in payloads]
        return PredictOutcome(result=results, latency_ms=(time.perf_counter() - started) * 1000)

    async def custom_metrics(self, name: str) -> dict[str, float]:
        handle = self.handle(name)
        spec = handle.spec
        if spec.metrics_fn is None or handle.state is not ModelState.READY:
            return {}
        try:
            args = (handle.instance,) if spec.metrics_wants_model() else ()
            raw = await _call(spec.metrics_fn, *args)
        except Exception as exc:
            logger.warning("model.metrics_failed", model=name, error=str(exc))
            return {}
        if not isinstance(raw, dict):
            logger.warning("model.metrics_not_a_dict", model=name, got=type(raw).__name__)
            return {}
        values: dict[str, float] = {}
        for key, value in raw.items():
            try:
                values[str(key)] = float(value)
            except (TypeError, ValueError):
                logger.warning("model.metric_not_numeric", model=name, metric=key)
        prom.publish_custom_metrics(name, values)
        return values

    def _record_failure(self, handle: ModelHandle, started: float) -> None:
        name = handle.spec.name
        latency_ms = (time.perf_counter() - started) * 1000
        prom.PREDICT_IN_PROGRESS.labels(model=name).dec()
        prom.PREDICT_TOTAL.labels(model=name, status="error").inc()
        prom.PREDICT_LATENCY.labels(model=name).observe(latency_ms / 1000)
        handle.predict_count += 1
        handle.error_count += 1
        handle.last_latency_ms = latency_ms
        handle.last_called_at = datetime.now(UTC)

    async def _emit(
        self, event: str, name: str, duration_ms: float | None, details: dict[str, Any]
    ) -> None:
        if self.event_hook is None:
            return
        try:
            await self.event_hook(event, name, duration_ms, details)
        except Exception as exc:
            logger.warning("model.event_hook_failed", model=name, event=event, error=str(exc))

    async def shutdown(self) -> None:
        for handle in list(self._handles.values()):
            if handle.state is ModelState.READY:
                await self.unload(handle.spec.name)


async def _call(func: Callable[..., Any], *args: Any) -> Any:
    """Вызывает пользовательскую функцию: async — напрямую, sync — в пуле потоков."""
    if inspect.iscoroutinefunction(func):
        return await func(*args)
    return await anyio.to_thread.run_sync(functools.partial(func, *args))

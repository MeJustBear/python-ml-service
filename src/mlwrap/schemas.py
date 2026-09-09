"""Схемы ответов API."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from mlwrap.registry.runtime import ModelHandle

ResultT = TypeVar("ResultT")


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str
    auth_mode: str
    api_prefix: str
    docs_url: str
    metrics_url: str | None
    models: list[str]


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok", "degraded"])
    checks: dict[str, str] = Field(default_factory=dict)


class PrincipalInfo(BaseModel):
    subject: str
    auth_mode: str
    claims: dict[str, Any] = Field(default_factory=dict)


class ModelInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str
    version: str
    description: str
    tags: list[str]
    state: str
    requires_load: bool
    has_metrics: bool
    loaded_at: datetime | None = None
    load_duration_ms: float | None = None
    error: str | None = None
    predict_count: int = 0
    error_count: int = 0
    avg_latency_ms: float | None = None
    last_latency_ms: float | None = None
    last_called_at: datetime | None = None

    @classmethod
    def from_handle(cls, handle: ModelHandle) -> "ModelInfo":
        spec = handle.spec
        return cls(
            name=spec.name,
            version=spec.version,
            description=spec.description,
            tags=spec.tags,
            state=handle.state.value,
            requires_load=spec.requires_load,
            has_metrics=spec.metrics_fn is not None,
            loaded_at=handle.loaded_at,
            load_duration_ms=_round(handle.load_duration_ms),
            error=handle.error,
            predict_count=handle.predict_count,
            error_count=handle.error_count,
            avg_latency_ms=_round(handle.avg_latency_ms),
            last_latency_ms=_round(handle.last_latency_ms),
            last_called_at=handle.last_called_at,
        )


class ModelSchemaInfo(BaseModel):
    name: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


class PredictResponse(BaseModel, Generic[ResultT]):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    version: str
    latency_ms: float
    request_id: str | None = None
    result: ResultT


class BatchPredictResponse(BaseModel, Generic[ResultT]):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    version: str
    latency_ms: float
    count: int
    request_id: str | None = None
    results: list[ResultT]


class ModelMetricsResponse(BaseModel):
    name: str
    state: str
    runtime: dict[str, Any]
    custom: dict[str, float] = Field(default_factory=dict)
    history: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None

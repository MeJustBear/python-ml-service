"""Запись истории инференсов и расчёт агрегатов по ней."""

from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mlwrap.db.models import InferenceLog, ModelEvent


async def record_inference(
    session: AsyncSession,
    *,
    model_name: str,
    model_version: str,
    status: str,
    latency_ms: float,
    batch_size: int = 1,
    error: str | None = None,
    request_id: str | None = None,
    principal: str | None = None,
    payload: Any | None = None,
    result: Any | None = None,
) -> None:
    session.add(
        InferenceLog(
            model_name=model_name,
            model_version=model_version,
            status=status,
            latency_ms=latency_ms,
            batch_size=batch_size,
            error=error,
            request_id=request_id,
            principal=principal,
            payload=payload,
            result=result,
        )
    )
    await session.commit()


async def record_model_event(
    session: AsyncSession,
    *,
    model_name: str,
    event: str,
    duration_ms: float | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        ModelEvent(
            model_name=model_name,
            event=event,
            duration_ms=duration_ms,
            details=details,
        )
    )
    await session.commit()


async def inference_stats(
    session: AsyncSession, model_name: str, *, window: int = 1000
) -> dict[str, Any]:
    """Сводка по журналу: счётчики из SQL, перцентили — по последним ``window`` успешным вызовам."""
    totals = (
        await session.execute(
            select(
                func.count(InferenceLog.id),
                func.sum(case((InferenceLog.status == "error", 1), else_=0)),
                func.min(InferenceLog.created_at),
                func.max(InferenceLog.created_at),
            ).where(InferenceLog.model_name == model_name)
        )
    ).one()
    total, errors, first_at, last_at = totals
    total = int(total or 0)
    errors = int(errors or 0)

    latencies = list(
        (
            await session.execute(
                select(InferenceLog.latency_ms)
                .where(InferenceLog.model_name == model_name, InferenceLog.status == "ok")
                .order_by(InferenceLog.created_at.desc())
                .limit(window)
            )
        ).scalars()
    )

    return {
        "total": total,
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "first_at": _iso(first_at),
        "last_at": _iso(last_at),
        "window": len(latencies),
        "latency_ms": _latency_summary(latencies),
    }


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "min": None, "max": None, "p50": None, "p95": None, "p99": None}
    ordered = sorted(values)
    return {
        "avg": round(statistics.fmean(ordered), 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "p50": round(_percentile(ordered, 0.50), 3),
        "p95": round(_percentile(ordered, 0.95), 3),
        "p99": round(_percentile(ordered, 0.99), 3),
    }


def _percentile(ordered: list[float], fraction: float) -> float:
    index = min(len(ordered) - 1, max(0, round(fraction * len(ordered) + 0.5) - 1))
    return ordered[index]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

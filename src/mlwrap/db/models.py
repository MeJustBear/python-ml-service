"""Таблицы: журнал инференсов и события жизненного цикла моделей."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB на Postgres, обычный JSON на SQLite в тестах.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class InferenceLog(Base):
    __tablename__ = "inference_log"
    __table_args__ = (Index("ix_inference_log_model_created", "model_name", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    batch_size: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    principal: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    result: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelEvent(Base):
    __tablename__ = "model_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    event: Mapped[str] = mapped_column(String(32), index=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

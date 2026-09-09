"""Приведение результатов моделей к JSON-совместимым типам."""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import enum
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

_MAX_DEPTH = 12


def to_jsonable(value: Any, _depth: int = 0) -> Any:
    """Разворачивает pydantic-модели, numpy-массивы, dataclass'ы и прочее в JSON-типы."""
    if _depth > _MAX_DEPTH:
        return repr(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, enum.Enum):
        return to_jsonable(value.value, _depth + 1)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, decimal.Decimal)):
        return str(value) if isinstance(value, uuid.UUID) else float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(dataclasses.asdict(value), _depth + 1)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item, _depth + 1) for key, item in value.items()}
    if hasattr(value, "tolist"):  # numpy.ndarray и numpy-скаляры
        return to_jsonable(value.tolist(), _depth + 1)
    if hasattr(value, "item") and getattr(value, "shape", None) == ():
        return to_jsonable(value.item(), _depth + 1)
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(item, _depth + 1) for item in value]
    if isinstance(value, Sequence):
        return [to_jsonable(item, _depth + 1) for item in value]
    return repr(value)


def truncate(value: Any, max_chars: int) -> Any:
    """Ограничивает размер того, что уходит в БД, чтобы журнал не распухал."""
    if max_chars <= 0:
        return value
    text = repr(value)
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "preview": text[:max_chars]}

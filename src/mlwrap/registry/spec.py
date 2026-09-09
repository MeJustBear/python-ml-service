"""Описание модели: набор пользовательских функций плюс выведенные из них схемы."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelSpec:
    """Всё, что сервис знает о модели до её загрузки."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)

    loader: Callable[..., Any] | None = None
    predictor: Callable[..., Any] | None = None
    unloader: Callable[..., Any] | None = None
    metrics_fn: Callable[..., Any] | None = None

    input_schema: Any = None
    output_schema: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.predictor is not None

    @property
    def requires_load(self) -> bool:
        return self.loader is not None

    def loader_wants_config(self) -> bool:
        if self.loader is None:
            return False
        return bool(_positional_params(self.loader))

    def metrics_wants_model(self) -> bool:
        if self.metrics_fn is None:
            return False
        return bool(_positional_params(self.metrics_fn))

    def unloader_wants_model(self) -> bool:
        if self.unloader is None:
            return False
        return bool(_positional_params(self.unloader))


def _positional_params(func: Callable[..., Any]) -> list[inspect.Parameter]:
    signature = inspect.signature(func)
    return [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]

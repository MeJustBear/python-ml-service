"""Реестр моделей: декораторы, которыми пользовательский код регистрирует свои функции."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from typing import Any, TypeVar, get_type_hints

from mlwrap.errors import ConfigurationError, ModelNotFoundError
from mlwrap.registry.spec import ModelSpec

F = TypeVar("F", bound=Callable[..., Any])

FREE_FORM_SCHEMA: Any = dict[str, Any]


class ModelRegistry:
    """Хранит описания моделей, собранные из декораторов.

    Функции загрузки, инференса и метрик регистрируются независимо друг от друга —
    достаточно, чтобы они указывали одно и то же имя модели.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ModelSpec] = {}

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __iter__(self) -> Iterator[ModelSpec]:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)

    def spec(self, name: str) -> ModelSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise ModelNotFoundError(f"Модель '{name}' не зарегистрирована") from None

    def names(self) -> list[str]:
        return sorted(self._specs)

    def specs(self) -> list[ModelSpec]:
        return [self._specs[name] for name in self.names()]

    def clear(self) -> None:
        self._specs.clear()

    def remove(self, name: str) -> None:
        self._specs.pop(name, None)

    def loader(
        self,
        name: str,
        *,
        version: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> Callable[[F], F]:
        """Регистрирует функцию загрузки модели.

        Функция может принимать один аргумент — словарь конфигурации из ``MLWRAP_MODELS_CONFIG``.
        """

        def decorator(func: F) -> F:
            spec = self._ensure(name, version=version, description=description, tags=tags)
            if len(_positional_names(func)) > 1:
                raise ConfigurationError(
                    f"loader модели '{name}' должен принимать 0 или 1 аргумент (config)"
                )
            spec.loader = func
            return func

        return decorator

    def predictor(
        self,
        name: str,
        *,
        input_schema: Any = None,
        output_schema: Any = None,
        version: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> Callable[[F], F]:
        """Регистрирует функцию инференса ``(model, payload) -> result``.

        Схемы запроса и ответа берутся из аннотаций, если не заданы явно.
        """

        def decorator(func: F) -> F:
            spec = self._ensure(name, version=version, description=description, tags=tags)
            positional = _positional_names(func)
            if len(positional) != 2:
                raise ConfigurationError(
                    f"predictor модели '{name}' должен принимать ровно два аргумента "
                    "(model, payload)"
                )
            inferred_input, inferred_output = _infer_schemas(func, positional[1])
            spec.predictor = func
            spec.input_schema = input_schema or inferred_input
            spec.output_schema = output_schema or inferred_output
            return func

        return decorator

    def unloader(self, name: str) -> Callable[[F], F]:
        """Регистрирует освобождение ресурсов модели."""

        def decorator(func: F) -> F:
            self._ensure(name).unloader = func
            return func

        return decorator

    def metrics(self, name: str) -> Callable[[F], F]:
        """Регистрирует сбор пользовательских метрик модели: ``(model) -> dict[str, float]``."""

        def decorator(func: F) -> F:
            self._ensure(name).metrics_fn = func
            return func

        return decorator

    def register(
        self,
        name: str,
        *,
        predict: Callable[..., Any],
        load: Callable[..., Any] | None = None,
        unload: Callable[..., Any] | None = None,
        metrics: Callable[..., Any] | None = None,
        input_schema: Any = None,
        output_schema: Any = None,
        version: str = "0.1.0",
        description: str = "",
        tags: list[str] | None = None,
    ) -> ModelSpec:
        """Императивная регистрация — удобна, когда функции живут в методах класса."""
        self.predictor(
            name,
            input_schema=input_schema,
            output_schema=output_schema,
            version=version,
            description=description,
            tags=tags,
        )(predict)
        if load is not None:
            self.loader(name)(load)
        if unload is not None:
            self.unloader(name)(unload)
        if metrics is not None:
            self.metrics(name)(metrics)
        return self.spec(name)

    def validate(self) -> None:
        broken = [spec.name for spec in self._specs.values() if not spec.is_complete]
        if broken:
            raise ConfigurationError(
                "У моделей нет функции инференса: " + ", ".join(sorted(broken)),
                details={"models": sorted(broken)},
            )

    def _ensure(
        self,
        name: str,
        *,
        version: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> ModelSpec:
        spec = self._specs.get(name)
        if spec is None:
            spec = ModelSpec(name=name)
            self._specs[name] = spec
        if version:
            spec.version = version
        if description:
            spec.description = description
        if tags:
            spec.tags = list(tags)
        return spec


def _positional_names(func: Callable[..., Any]) -> list[str]:
    signature = inspect.signature(func)
    return [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]


def _infer_schemas(func: Callable[..., Any], payload_param: str) -> tuple[Any, Any]:
    try:
        hints = get_type_hints(func)
    except Exception:  # аннотации могут ссылаться на локальные типы — не повод падать
        return FREE_FORM_SCHEMA, None
    payload_type = hints.get(payload_param)
    return_type = hints.get("return")
    if payload_type in (None, Any, inspect.Parameter.empty):
        payload_type = FREE_FORM_SCHEMA
    if return_type in (Any, inspect.Parameter.empty):
        return_type = None
    return payload_type, return_type


registry = ModelRegistry()

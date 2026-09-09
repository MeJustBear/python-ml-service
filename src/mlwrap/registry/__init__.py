"""Реестр моделей и рантайм."""

from mlwrap.registry.discovery import discover
from mlwrap.registry.registry import ModelRegistry, registry
from mlwrap.registry.runtime import ModelHandle, ModelRuntime, ModelState, PredictOutcome
from mlwrap.registry.spec import ModelSpec

__all__ = [
    "ModelHandle",
    "ModelRegistry",
    "ModelRuntime",
    "ModelSpec",
    "ModelState",
    "PredictOutcome",
    "discover",
    "registry",
]

"""mlwrap — FastAPI-обёртка для быстрого тестирования ML-моделей."""

from mlwrap.registry import ModelSpec, registry

__all__ = ["ModelSpec", "__version__", "registry"]

__version__ = "0.1.0"

"""HTTP-слой: готовые эндпоинты для любой модели."""

from mlwrap.api.models_api import build_models_router
from mlwrap.api.system import build_auth_router, build_system_router

__all__ = ["build_auth_router", "build_models_router", "build_system_router"]

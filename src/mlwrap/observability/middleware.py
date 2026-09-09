"""Middleware: request-id, метрики HTTP-слоя и access-лог."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mlwrap.observability import metrics as prom

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, access_log: bool = True, metrics_enabled: bool = True) -> None:
        super().__init__(app)
        self._access_log = access_log
        self._metrics_enabled = metrics_enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        started = time.perf_counter()
        if self._metrics_enabled:
            prom.HTTP_IN_PROGRESS.inc()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration = time.perf_counter() - started
            self._observe(request, "500", duration)
            logger.exception("http.unhandled_error", duration_ms=round(duration * 1000, 2))
            raise
        finally:
            if self._metrics_enabled:
                prom.HTTP_IN_PROGRESS.dec()

        duration = time.perf_counter() - started
        self._observe(request, str(status_code), duration)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration * 1000:.2f}"
        if self._access_log:
            logger.info("http.request", status=status_code, duration_ms=round(duration * 1000, 2))
        structlog.contextvars.clear_contextvars()
        return response

    def _observe(self, request: Request, status: str, duration: float) -> None:
        if not self._metrics_enabled:
            return
        path = _route_path(request)
        prom.HTTP_REQUESTS.labels(method=request.method, path=path, status=status).inc()
        prom.HTTP_DURATION.labels(method=request.method, path=path).observe(duration)


def _route_path(request: Request) -> str:
    """Шаблон маршрута вместо конкретного URL — иначе метки метрик разрастаются."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "unmatched"

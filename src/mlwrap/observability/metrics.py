"""Коллекторы Prometheus. Объявлены на уровне модуля — регистрируются ровно один раз."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

LATENCY_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)

PREDICT_TOTAL = Counter(
    "mlwrap_predict_total",
    "Число вызовов инференса",
    ["model", "status"],
)
PREDICT_LATENCY = Histogram(
    "mlwrap_predict_latency_seconds",
    "Длительность инференса",
    ["model"],
    buckets=LATENCY_BUCKETS,
)
PREDICT_IN_PROGRESS = Gauge(
    "mlwrap_predict_in_progress",
    "Число инференсов, выполняющихся прямо сейчас",
    ["model"],
)
PREDICT_BATCH_SIZE = Histogram(
    "mlwrap_predict_batch_size",
    "Размер пакета в batch-инференсе",
    ["model"],
    buckets=(1, 2, 5, 10, 25, 50, 100, 250, 500, 1000),
)

MODEL_LOADED = Gauge(
    "mlwrap_model_loaded",
    "1 — модель загружена и готова, 0 — нет",
    ["model"],
)
MODEL_LOAD_TOTAL = Counter(
    "mlwrap_model_load_total",
    "Число попыток загрузки модели",
    ["model", "status"],
)
MODEL_LOAD_DURATION = Histogram(
    "mlwrap_model_load_duration_seconds",
    "Длительность загрузки модели",
    ["model"],
    buckets=(0.01, 0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 300.0),
)
MODEL_CUSTOM_METRIC = Gauge(
    "mlwrap_model_custom_metric",
    "Метрики, возвращённые функцией metrics плагина",
    ["model", "metric"],
)

HTTP_REQUESTS = Counter(
    "mlwrap_http_requests_total",
    "Число HTTP-запросов",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "mlwrap_http_request_duration_seconds",
    "Длительность обработки HTTP-запроса",
    ["method", "path"],
    buckets=LATENCY_BUCKETS,
)
HTTP_IN_PROGRESS = Gauge(
    "mlwrap_http_requests_in_progress",
    "Число HTTP-запросов в обработке",
)

APP_INFO = Gauge(
    "mlwrap_app_info",
    "Информация о запущенном сервисе",
    ["version", "environment", "auth_mode"],
)


def set_app_info(version: str, environment: str, auth_mode: str) -> None:
    APP_INFO.labels(version=version, environment=environment, auth_mode=auth_mode).set(1)


def publish_custom_metrics(model: str, values: dict[str, float]) -> None:
    for key, value in values.items():
        try:
            MODEL_CUSTOM_METRIC.labels(model=model, metric=key).set(float(value))
        except (TypeError, ValueError):
            continue


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

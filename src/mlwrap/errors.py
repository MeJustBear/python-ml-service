"""Доменные исключения сервиса и их отображение в HTTP-коды."""

from __future__ import annotations


class MLWrapError(Exception):
    """Базовая ошибка сервиса."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(MLWrapError):
    status_code = 500
    code = "configuration_error"


class ModelNotFoundError(MLWrapError):
    status_code = 404
    code = "model_not_found"


class ModelNotLoadedError(MLWrapError):
    status_code = 409
    code = "model_not_loaded"


class ModelLoadError(MLWrapError):
    status_code = 503
    code = "model_load_failed"


class PredictionError(MLWrapError):
    status_code = 500
    code = "prediction_failed"


class PredictionTimeoutError(MLWrapError):
    status_code = 504
    code = "prediction_timeout"


class InvalidPayloadError(MLWrapError):
    status_code = 422
    code = "invalid_payload"


class AuthenticationError(MLWrapError):
    status_code = 401
    code = "unauthorized"

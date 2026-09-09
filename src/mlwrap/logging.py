"""Настройка логирования: structlog поверх stdlib, консольный или JSON-вывод."""

from __future__ import annotations

import logging
import sys

import structlog

from mlwrap.config import LogFormat


def configure_logging(level: str = "INFO", log_format: LogFormat = LogFormat.CONSOLE) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if log_format is LogFormat.JSON
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=log_level, force=True)
    # Запросы логирует ObservabilityMiddleware — access-лог uvicorn был бы вторым таким же.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine.Engine").handlers.clear()

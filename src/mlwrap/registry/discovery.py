"""Подключение модулей с моделями: пакет ``mlwrap.plugins`` и список из конфигурации."""

from __future__ import annotations

import importlib
import pkgutil

import structlog

from mlwrap.errors import ConfigurationError

logger = structlog.get_logger(__name__)

BUILTIN_PLUGIN_PACKAGE = "mlwrap.plugins"


def discover(modules: list[str], *, autodiscover: bool = True) -> list[str]:
    """Импортирует модули-плагины; сам импорт и выполняет регистрацию в реестре."""
    imported: list[str] = []
    targets: list[str] = []

    if autodiscover:
        targets.extend(_builtin_modules())
    targets.extend(modules)

    for module_name in dict.fromkeys(targets):
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            if module_name.startswith(f"{BUILTIN_PLUGIN_PACKAGE}."):
                # Встроенные примеры могут требовать опциональных зависимостей.
                logger.warning("plugin.skipped", module=module_name, error=str(exc))
                continue
            raise ConfigurationError(
                f"Не удалось импортировать модуль плагина '{module_name}': {exc}"
            ) from exc
        imported.append(module_name)
        logger.debug("plugin.imported", module=module_name)

    return imported


def _builtin_modules() -> list[str]:
    try:
        package = importlib.import_module(BUILTIN_PLUGIN_PACKAGE)
    except ImportError:  # pragma: no cover
        return []
    paths = list(getattr(package, "__path__", []))
    return [
        f"{BUILTIN_PLUGIN_PACKAGE}.{info.name}"
        for info in pkgutil.iter_modules(paths)
        if not info.name.startswith("_")
    ]

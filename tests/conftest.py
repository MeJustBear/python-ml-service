import asyncio
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from mlwrap.app import create_app
from mlwrap.config import Settings
from mlwrap.registry import ModelRegistry


class SumRequest(BaseModel):
    values: list[float]


class SumResponse(BaseModel):
    total: float
    count: int


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("MLWRAP_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def test_registry() -> ModelRegistry:
    return build_test_registry()


def build_test_registry() -> ModelRegistry:
    registry = ModelRegistry()

    @registry.loader("sum", version="2.0.0", description="сумматор", tags=["test"])
    def load_sum(config: dict[str, Any]) -> dict[str, Any]:
        return {"scale": float(config.get("scale", 1.0)), "calls": 0}

    @registry.predictor("sum")
    def predict_sum(model: dict[str, Any], payload: SumRequest) -> SumResponse:
        model["calls"] += 1
        return SumResponse(total=sum(payload.values) * model["scale"], count=len(payload.values))

    @registry.metrics("sum")
    def sum_metrics(model: dict[str, Any]) -> dict[str, float]:
        return {"calls": model["calls"], "scale": model["scale"]}

    @registry.unloader("sum")
    def unload_sum(model: dict[str, Any]) -> None:
        model.clear()

    @registry.predictor("free")
    def predict_free(model: Any, payload: Any) -> Any:
        return {"echo": payload}

    @registry.loader("broken")
    def load_broken() -> Any:
        raise RuntimeError("артефакт не найден")

    @registry.predictor("broken")
    def predict_broken(model: Any, payload: Any) -> Any:  # pragma: no cover
        return payload

    @registry.predictor("boom")
    def predict_boom(model: Any, payload: Any) -> Any:
        raise ValueError("модель сломалась")

    @registry.predictor("slow")
    async def predict_slow(model: Any, payload: Any) -> Any:
        await asyncio.sleep(1.0)
        return {"done": True}

    return registry


ClientFactory = Callable[..., Any]


@pytest.fixture
def make_client() -> ClientFactory:
    @asynccontextmanager
    async def factory(**overrides: Any) -> AsyncIterator[httpx.AsyncClient]:
        options: dict[str, Any] = {
            "plugin_autodiscover": False,
            "plugin_modules": [],
            "database_url": None,
            "access_log": False,
            **overrides,
        }
        settings = Settings(_env_file=None, **options)
        app = create_app(settings, model_registry=build_test_registry(), configure_logs=False)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                client.app = app  # type: ignore[attr-defined]
                yield client

    return factory


@pytest.fixture
async def client(make_client: ClientFactory) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client() as instance:
        yield instance

"""Простейшая модель-заглушка: проверить, что сервис поднялся и эндпоинты работают."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from mlwrap.registry import registry

MODEL = "echo"


class EchoRequest(BaseModel):
    text: str = Field(description="Текст, который вернётся обратно")
    repeat: int = Field(default=1, ge=1, le=100)
    delay_ms: int = Field(default=0, ge=0, le=10_000, description="Искусственная задержка")


class EchoResponse(BaseModel):
    text: str
    length: int
    calls: int


@registry.loader(MODEL, version="1.0.0", description="эхо-модель для смоук-тестов")
def load_echo(config: dict[str, Any]) -> dict[str, Any]:
    return {"calls": 0, "prefix": config.get("prefix", "")}


@registry.predictor(MODEL)
def predict_echo(model: dict[str, Any], payload: EchoRequest) -> EchoResponse:
    if payload.delay_ms:
        time.sleep(payload.delay_ms / 1000)
    text = model["prefix"] + payload.text * payload.repeat
    model["calls"] += 1
    return EchoResponse(text=text, length=len(text), calls=model["calls"])


@registry.metrics(MODEL)
def echo_metrics(model: dict[str, Any]) -> dict[str, float]:
    return {"calls": model["calls"]}

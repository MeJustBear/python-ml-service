from typing import Any

import pytest
from pydantic import BaseModel

from mlwrap.errors import ConfigurationError, ModelNotFoundError
from mlwrap.registry import ModelRegistry


class Request(BaseModel):
    text: str


class Response(BaseModel):
    length: int


def test_schemas_are_inferred_from_annotations() -> None:
    registry = ModelRegistry()

    @registry.predictor("count")
    def predict(model: None, payload: Request) -> Response:
        return Response(length=len(payload.text))

    spec = registry.spec("count")
    assert spec.input_schema is Request
    assert spec.output_schema is Response
    assert spec.requires_load is False


def test_free_form_schema_when_annotations_missing() -> None:
    registry = ModelRegistry()

    @registry.predictor("raw")
    def predict(model, payload):  # без аннотаций
        return payload

    assert registry.spec("raw").input_schema == dict[str, Any]
    assert registry.spec("raw").output_schema is None


def test_functions_are_registered_independently() -> None:
    registry = ModelRegistry()

    @registry.loader("m", version="3.1.4", description="описание")
    def load(config: dict) -> str:
        return "model"

    @registry.predictor("m")
    def predict(model: str, payload: Request) -> Response:
        return Response(length=len(payload.text))

    @registry.metrics("m")
    def metrics(model: str) -> dict[str, float]:
        return {"ok": 1.0}

    spec = registry.spec("m")
    assert spec.version == "3.1.4"
    assert spec.description == "описание"
    assert spec.requires_load is True
    assert spec.loader_wants_config() is True
    assert spec.metrics_wants_model() is True
    assert spec.is_complete is True


def test_loader_without_arguments_is_allowed() -> None:
    registry = ModelRegistry()

    @registry.loader("m")
    def load() -> str:
        return "model"

    assert registry.spec("m").loader_wants_config() is False


def test_predictor_signature_is_checked() -> None:
    registry = ModelRegistry()

    with pytest.raises(ConfigurationError):

        @registry.predictor("bad")
        def predict(payload: Request) -> Response:
            return Response(length=0)


def test_loader_signature_is_checked() -> None:
    registry = ModelRegistry()

    with pytest.raises(ConfigurationError):

        @registry.loader("bad")
        def load(a: dict, b: dict) -> None:
            return None


def test_validate_rejects_model_without_predictor() -> None:
    registry = ModelRegistry()
    registry.loader("half")(lambda: None)

    with pytest.raises(ConfigurationError, match="half"):
        registry.validate()


def test_unknown_model_raises() -> None:
    with pytest.raises(ModelNotFoundError):
        ModelRegistry().spec("missing")


def test_imperative_registration() -> None:
    registry = ModelRegistry()
    registry.register(
        "imperative",
        predict=lambda model, payload: payload,
        load=lambda: {"state": 1},
        metrics=lambda model: {"value": 2.0},
        version="1.2.3",
    )
    spec = registry.spec("imperative")
    assert spec.is_complete and spec.requires_load
    assert spec.version == "1.2.3"
    assert registry.names() == ["imperative"]

"""Пример реальной модели: RandomForest на ирисах.

Требует опциональных зависимостей (``pdm install -G examples``). Если scikit-learn нет,
модуль не импортируется и просто не попадает в реестр.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from mlwrap.registry import registry

MODEL = "iris"


class IrisRequest(BaseModel):
    features: list[float] = Field(
        min_length=4,
        max_length=4,
        description="sepal length, sepal width, petal length, petal width",
        examples=[[5.1, 3.5, 1.4, 0.2]],
    )


class IrisResponse(BaseModel):
    label: str
    probabilities: dict[str, float]


@dataclass
class IrisBundle:
    classifier: RandomForestClassifier
    class_names: list[str]
    accuracy: float


@registry.loader(MODEL, version="1.0.0", description="классификатор ирисов (RandomForest)")
def load_iris_model(config: dict[str, Any]) -> IrisBundle:
    dataset = load_iris()
    x_train, x_test, y_train, y_test = train_test_split(
        dataset.data, dataset.target, test_size=0.2, random_state=42
    )
    classifier = RandomForestClassifier(
        n_estimators=int(config.get("n_estimators", 100)), random_state=42
    )
    classifier.fit(x_train, y_train)
    return IrisBundle(
        classifier=classifier,
        class_names=list(dataset.target_names),
        accuracy=float(classifier.score(x_test, y_test)),
    )


@registry.predictor(MODEL)
def predict_iris(model: IrisBundle, payload: IrisRequest) -> IrisResponse:
    probabilities = model.classifier.predict_proba([payload.features])[0]
    best = int(probabilities.argmax())
    return IrisResponse(
        label=model.class_names[best],
        probabilities={
            name: round(float(value), 4)
            for name, value in zip(model.class_names, probabilities, strict=True)
        },
    )


@registry.metrics(MODEL)
def iris_metrics(model: IrisBundle) -> dict[str, float]:
    return {
        "test_accuracy": model.accuracy,
        "n_estimators": float(model.classifier.n_estimators),
        "n_features": float(model.classifier.n_features_in_),
    }

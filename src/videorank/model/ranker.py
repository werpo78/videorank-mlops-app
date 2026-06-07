from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videorank.features.offline import FEATURE_NAMES


def sigmoid(value: float) -> float:
    if value < -50:
        return 0.0
    if value > 50:
        return 1.0
    return 1 / (1 + math.exp(-value))


@dataclass
class SimpleLogisticRanker:
    feature_names: list[str]
    weights: list[float]
    bias: float = 0.0

    @classmethod
    def fresh(cls, feature_names: list[str] | None = None) -> "SimpleLogisticRanker":
        names = feature_names or list(FEATURE_NAMES)
        return cls(feature_names=names, weights=[0.0 for _ in names], bias=0.0)

    def fit(
        self,
        features: list[list[float]],
        labels: list[int],
        epochs: int = 120,
        learning_rate: float = 0.35,
        l2: float = 0.001,
    ) -> "SimpleLogisticRanker":
        if not features:
            raise ValueError("features must not be empty")
        for _ in range(epochs):
            grad_w = [0.0 for _ in self.weights]
            grad_b = 0.0
            for row, label in zip(features, labels, strict=True):
                prediction = self.predict_proba(row)
                error = prediction - label
                for index, value in enumerate(row):
                    grad_w[index] += error * value
                grad_b += error
            n = len(features)
            for index, weight in enumerate(self.weights):
                self.weights[index] = weight - learning_rate * ((grad_w[index] / n) + l2 * weight)
            self.bias -= learning_rate * (grad_b / n)
        return self

    def score_raw(self, features: list[float]) -> float:
        return self.bias + sum(weight * value for weight, value in zip(self.weights, features, strict=True))

    def predict_proba(self, features: list[float]) -> float:
        return sigmoid(self.score_raw(features))

    def to_dict(self) -> dict[str, Any]:
        return {"feature_names": self.feature_names, "weights": self.weights, "bias": self.bias}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SimpleLogisticRanker":
        return cls(
            feature_names=list(payload["feature_names"]),
            weights=[float(value) for value in payload["weights"]],
            bias=float(payload["bias"]),
        )

    def save(self, path: Path, extra: dict[str, Any] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ranker": self.to_dict(), **(extra or {})}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> tuple["SimpleLogisticRanker", dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(payload["ranker"]), payload


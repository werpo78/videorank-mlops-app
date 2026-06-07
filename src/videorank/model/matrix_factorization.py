from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _sigmoid(value: float) -> float:
    if value < -50:
        return 0.0
    if value > 50:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


@dataclass
class MatrixFactorizationRanker:
    user_to_index: dict[str, int]
    item_to_index: dict[str, int]
    user_factors: Any
    item_factors: Any
    user_bias: Any
    item_bias: Any
    global_bias: float

    @classmethod
    def fresh(
        cls,
        user_ids: list[str],
        item_ids: list[str],
        factors: int = 24,
        seed: int = 7,
    ) -> MatrixFactorizationRanker:
        import numpy as np

        rng = np.random.default_rng(seed)
        user_to_index = {user_id: index for index, user_id in enumerate(sorted(set(user_ids)))}
        item_to_index = {item_id: index for index, item_id in enumerate(sorted(set(item_ids)))}
        return cls(
            user_to_index=user_to_index,
            item_to_index=item_to_index,
            user_factors=rng.normal(0, 0.05, size=(len(user_to_index), factors)),
            item_factors=rng.normal(0, 0.05, size=(len(item_to_index), factors)),
            user_bias=np.zeros(len(user_to_index)),
            item_bias=np.zeros(len(item_to_index)),
            global_bias=0.0,
        )

    def fit(
        self,
        rows: list[dict[str, Any]],
        epochs: int = 8,
        learning_rate: float = 0.05,
        regularization: float = 0.002,
        seed: int = 7,
    ) -> MatrixFactorizationRanker:
        import numpy as np

        if not rows:
            raise ValueError("rows must not be empty")
        rng = np.random.default_rng(seed)
        indices = np.array(
            [
                (self.user_to_index[row["user_id"]], self.item_to_index[row["video_id"]])
                for row in rows
            ],
            dtype=np.int64,
        )
        labels = np.array([int(row["label"]) for row in rows], dtype=np.float64)
        positive_rate = min(0.99, max(0.01, float(labels.mean())))
        self.global_bias = math.log(positive_rate / (1 - positive_rate))

        for _ in range(epochs):
            order = rng.permutation(len(rows))
            for row_index in order:
                user_index, item_index = indices[row_index]
                label = labels[row_index]
                user_vector = self.user_factors[user_index].copy()
                item_vector = self.item_factors[item_index].copy()
                score = self._score_indices(user_index, item_index)
                error = _sigmoid(score) - label

                self.user_bias[user_index] -= learning_rate * (
                    error + regularization * self.user_bias[user_index]
                )
                self.item_bias[item_index] -= learning_rate * (
                    error + regularization * self.item_bias[item_index]
                )
                self.user_factors[user_index] -= learning_rate * (
                    error * item_vector + regularization * user_vector
                )
                self.item_factors[item_index] -= learning_rate * (
                    error * user_vector + regularization * item_vector
                )
        return self

    def _score_indices(self, user_index: int, item_index: int) -> float:
        dot = float((self.user_factors[user_index] * self.item_factors[item_index]).sum())
        return (
            self.global_bias
            + float(self.user_bias[user_index])
            + float(self.item_bias[item_index])
            + dot
        )

    def predict_proba(self, user_id: str, item_id: str) -> float:
        user_index = self.user_to_index.get(user_id)
        item_index = self.item_to_index.get(item_id)
        if user_index is None or item_index is None:
            return _sigmoid(self.global_bias)
        return _sigmoid(self._score_indices(user_index, item_index))

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "matrix_factorization",
            "user_to_index": self.user_to_index,
            "item_to_index": self.item_to_index,
            "user_factors": self.user_factors.tolist(),
            "item_factors": self.item_factors.tolist(),
            "user_bias": self.user_bias.tolist(),
            "item_bias": self.item_bias.tolist(),
            "global_bias": self.global_bias,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MatrixFactorizationRanker:
        import numpy as np

        return cls(
            user_to_index={key: int(value) for key, value in payload["user_to_index"].items()},
            item_to_index={key: int(value) for key, value in payload["item_to_index"].items()},
            user_factors=np.array(payload["user_factors"], dtype=np.float64),
            item_factors=np.array(payload["item_factors"], dtype=np.float64),
            user_bias=np.array(payload["user_bias"], dtype=np.float64),
            item_bias=np.array(payload["item_bias"], dtype=np.float64),
            global_bias=float(payload["global_bias"]),
        )

    def save(self, path: Path, extra: dict[str, Any] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**self.to_dict(), **(extra or {})}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> tuple[MatrixFactorizationRanker, dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(payload), payload

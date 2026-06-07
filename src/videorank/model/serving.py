from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from videorank.model.ranker import SimpleLogisticRanker


def stable_variant(user_id: str, experiment_id: str = "videorank-default") -> str:
    digest = hashlib.sha256(f"{experiment_id}:{user_id}".encode("utf-8")).hexdigest()
    return "ml_ranker" if int(digest[:8], 16) % 2 else "baseline_popularity"


class RecommendationEngine:
    def __init__(self, ranker: SimpleLogisticRanker, catalog: list[dict[str, Any]], model_version: str):
        self.ranker = ranker
        self.catalog = catalog
        self.model_version = model_version
        self.global_ctr = self._global_ctr()

    @classmethod
    def from_model_path(cls, model_path: Path) -> "RecommendationEngine":
        ranker, payload = SimpleLogisticRanker.load(model_path)
        catalog = payload.get("catalog", [])
        model_version = payload.get("model_version", "local")
        return cls(ranker=ranker, catalog=catalog, model_version=model_version)

    @classmethod
    def fallback(cls) -> "RecommendationEngine":
        catalog = [
            {
                "video_id": f"video_fallback_{index:03d}",
                "category": category,
                "impressions": 100 - index,
                "clicks": 10,
                "positive_labels": 8,
                "ctr": 0.10,
                "positive_rate": 0.08,
            }
            for index, category in enumerate(["sports", "music", "news", "gaming", "tech"])
        ]
        return cls(SimpleLogisticRanker.fresh(), catalog, "fallback")

    def recommend(
        self,
        user_id: str,
        context: dict[str, Any] | None = None,
        limit: int = 10,
        experiment_id: str = "videorank-default",
    ) -> dict[str, Any]:
        context = context or {}
        variant = stable_variant(user_id, experiment_id)
        candidates = self.catalog[: max(limit * 4, limit)]
        if variant == "baseline_popularity":
            ranked = sorted(candidates, key=lambda row: (row.get("positive_rate", 0), row.get("impressions", 0)), reverse=True)
        else:
            ranked = sorted(
                candidates,
                key=lambda row: self.ranker.predict_proba(self._features_for(row, context)),
                reverse=True,
            )
        recommendations = []
        for row in ranked[:limit]:
            features = self._features_for(row, context)
            score = (
                float(row.get("positive_rate", 0.0))
                if variant == "baseline_popularity"
                else self.ranker.predict_proba(features)
            )
            recommendations.append(
                {
                    "video_id": row["video_id"],
                    "score": round(score, 6),
                    "reason": f"{variant}:{row.get('category', 'unknown')}",
                }
            )
        return {
            "variant": variant,
            "model_version": self.model_version,
            "recommendations": recommendations,
        }

    def _global_ctr(self) -> float:
        impressions = sum(int(row.get("impressions", 0)) for row in self.catalog)
        clicks = sum(int(row.get("clicks", 0)) for row in self.catalog)
        return clicks / impressions if impressions else 0.08

    def _features_for(self, video: dict[str, Any], context: dict[str, Any]) -> list[float]:
        category_match = 1.0 if context.get("preferred_category") == video.get("category") else 0.08
        device_match = 0.14 if context.get("device") in {"mobile", "tv"} else 0.08
        country_match = 0.10 if context.get("country") in {"FR", "US", "GB"} else 0.08
        return [
            self.global_ctr,
            category_match,
            float(video.get("ctr", 0.08)),
            device_match,
            country_match,
            math.log1p(float(video.get("impressions", 0))) / 10.0,
        ]


def load_engine(model_path: str) -> RecommendationEngine:
    path = Path(model_path)
    if path.exists():
        return RecommendationEngine.from_model_path(path)
    return RecommendationEngine.fallback()


def write_prediction_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from videorank.model.matrix_factorization import MatrixFactorizationRanker
from videorank.model.ranker import SimpleLogisticRanker


def stable_variant(user_id: str, experiment_id: str = "videorank-default") -> str:
    digest = hashlib.sha256(f"{experiment_id}:{user_id}".encode()).hexdigest()
    return "ml_ranker" if int(digest[:8], 16) % 2 else "baseline_popularity"


def _model_file_from_path(path: Path) -> Path:
    return path / "model.json" if path.is_dir() else path


def _model_file_from_gcs_uri(uri: str) -> Path:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-storage is required to load a promoted model from GCS"
        ) from exc

    parsed = urlparse(uri)
    bucket_name = parsed.netloc
    object_name = parsed.path.lstrip("/")
    if not bucket_name or not object_name:
        raise ValueError(f"invalid GCS model URI: {uri}")
    if not object_name.endswith(".json"):
        object_name = f"{object_name.rstrip('/')}/model.json"

    cache_root = Path(tempfile.gettempdir()) / "videorank" / "model-cache"
    cache_key = hashlib.sha256(f"{bucket_name}/{object_name}".encode()).hexdigest()[:16]
    output_path = cache_root / cache_key / "model.json"
    if output_path.exists():
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.download_to_filename(output_path)
    return output_path


def materialize_model_uri(model_uri: str) -> Path:
    if model_uri.startswith("gs://"):
        return _model_file_from_gcs_uri(model_uri)
    if model_uri.startswith("file://"):
        return _model_file_from_path(Path(urlparse(model_uri).path))
    return _model_file_from_path(Path(model_uri))


class RecommendationEngine:
    def __init__(
        self,
        ranker: SimpleLogisticRanker | MatrixFactorizationRanker,
        catalog: list[dict[str, Any]],
        model_version: str,
        model_type: str = "simple_logistic",
    ):
        self.ranker = ranker
        self.catalog = catalog
        self.model_version = model_version
        self.model_type = model_type
        self.global_ctr = self._global_ctr()

    @classmethod
    def from_model_path(
        cls,
        model_path: Path,
        model_version_override: str | None = None,
    ) -> RecommendationEngine:
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        model_type = payload.get("model_type", "simple_logistic")
        catalog = payload.get("catalog", [])
        model_version = model_version_override or payload.get("model_version", "local")
        if model_type == "matrix_factorization":
            ranker = MatrixFactorizationRanker.from_dict(payload)
            return cls(
                ranker=ranker,
                catalog=catalog,
                model_version=model_version,
                model_type="matrix_factorization",
            )
        ranker = SimpleLogisticRanker.from_dict(payload["ranker"])
        return cls(
            ranker=ranker,
            catalog=catalog,
            model_version=model_version,
            model_type="simple_logistic",
        )

    @classmethod
    def fallback(cls) -> RecommendationEngine:
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
            ranked = sorted(candidates, key=self._baseline_sort_key, reverse=True)
        else:
            ranked = sorted(
                candidates,
                key=lambda row: self._ml_score(user_id, row, context),
                reverse=True,
            )
        recommendations = []
        for row in ranked[:limit]:
            score = (
                self._baseline_score(row)
                if variant == "baseline_popularity"
                else self._ml_score(user_id, row, context)
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

    def _baseline_score(self, video: dict[str, Any]) -> float:
        return float(video.get("positive_rate", video.get("ctr", 0.0)))

    def _baseline_sort_key(self, video: dict[str, Any]) -> tuple[float, float]:
        return (
            self._baseline_score(video),
            float(video.get("impressions", video.get("ratings", 0))),
        )

    def _ml_score(self, user_id: str, video: dict[str, Any], context: dict[str, Any]) -> float:
        if self.model_type == "matrix_factorization":
            ranker = self.ranker
            assert isinstance(ranker, MatrixFactorizationRanker)
            return ranker.predict_proba(user_id, video["video_id"])
        ranker = self.ranker
        assert isinstance(ranker, SimpleLogisticRanker)
        return ranker.predict_proba(self._features_for(video, context))

    def _global_ctr(self) -> float:
        impressions = sum(
            int(row.get("impressions", row.get("ratings", 0))) for row in self.catalog
        )
        clicks = sum(
            int(row.get("clicks", row.get("positive_labels", 0))) for row in self.catalog
        )
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
            math.log1p(float(video.get("impressions", video.get("ratings", 0)))) / 10.0,
        ]


def load_engine(
    model_uri_or_path: str,
    model_version_override: str | None = None,
) -> RecommendationEngine:
    try:
        path = materialize_model_uri(model_uri_or_path)
        if path.exists():
            return RecommendationEngine.from_model_path(
                path,
                model_version_override=model_version_override,
            )
    except Exception:
        return RecommendationEngine.fallback()
    return RecommendationEngine.fallback()


def write_prediction_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")

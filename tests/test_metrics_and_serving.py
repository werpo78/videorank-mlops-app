from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from videorank.data.generate import generate_events, write_jsonl
from videorank.model.metrics import auc_score, population_stability_index
from videorank.model.serving import RecommendationEngine, stable_variant
from videorank.model.train import train_from_events


class MetricsAndServingTests(unittest.TestCase):
    def test_auc_handles_ranked_scores(self) -> None:
        self.assertEqual(auc_score([1, 0], [0.9, 0.1]), 1.0)
        self.assertEqual(auc_score([1, 0], [0.1, 0.9]), 0.0)

    def test_psi_detects_distribution_change(self) -> None:
        stable = population_stability_index([0.1, 0.2, 0.3], [0.1, 0.2, 0.3])
        shifted = population_stability_index([0.1, 0.2, 0.3], [0.8, 0.9, 1.0])
        self.assertLess(stable, shifted)

    def test_variant_assignment_is_stable(self) -> None:
        self.assertEqual(stable_variant("user_1", "exp"), stable_variant("user_1", "exp"))

    def test_training_artifact_can_serve_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            events_path = tmp / "events.jsonl"
            model_dir = tmp / "model"
            write_jsonl(generate_events(users=20, videos=12, events=300, seed=11), events_path)
            metrics = train_from_events(events_path, model_dir, model_version="test")
            engine = RecommendationEngine.from_model_path(model_dir / "model.json")
            response = engine.recommend("user_00001", {"preferred_category": "sports"}, limit=5)
        self.assertIn("auc", metrics)
        self.assertEqual(len(response["recommendations"]), 5)
        self.assertEqual(response["model_version"], "test")

    def test_matrix_factorization_artifact_can_serve_recommendations(self) -> None:
        try:
            import numpy  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("numpy is not installed")

        from videorank.model.matrix_factorization import MatrixFactorizationRanker

        rows = [
            {"user_id": "user_1", "video_id": "movie_1", "label": 1},
            {"user_id": "user_1", "video_id": "movie_2", "label": 0},
            {"user_id": "user_2", "video_id": "movie_1", "label": 1},
            {"user_id": "user_2", "video_id": "movie_2", "label": 0},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model" / "model.json"
            ranker = MatrixFactorizationRanker.fresh(
                [row["user_id"] for row in rows],
                [row["video_id"] for row in rows],
                factors=4,
            ).fit(rows, epochs=1)
            ranker.save(
                model_path,
                extra={
                    "model_version": "mf-promoted",
                    "catalog": [
                        {
                            "video_id": "movie_1",
                            "category": "drama",
                            "ratings": 2,
                            "positive_labels": 2,
                            "positive_rate": 0.8,
                        },
                        {
                            "video_id": "movie_2",
                            "category": "comedy",
                            "ratings": 2,
                            "positive_labels": 0,
                            "positive_rate": 0.2,
                        },
                    ],
                },
            )
            engine = RecommendationEngine.from_model_path(model_path)
            response = engine.recommend("user_1", limit=2, experiment_id="force")
        self.assertEqual(response["model_version"], "mf-promoted")
        self.assertEqual(len(response["recommendations"]), 2)

    def test_api_health_and_readiness_routes_when_fastapi_is_installed(self) -> None:
        try:
            from fastapi.testclient import TestClient

            from videorank.api.app import create_app
        except ModuleNotFoundError:
            self.skipTest("FastAPI test dependencies are not installed")

        client = TestClient(create_app())

        self.assertEqual(client.get("/health").json(), {"status": "ok"})
        self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
        self.assertEqual(client.get("/readyz").json()["status"], "ready")


if __name__ == "__main__":
    unittest.main()

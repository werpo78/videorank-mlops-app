from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from videorank.data.movielens import prepare_movielens_events


class MovieLensPipelineTests(unittest.TestCase):
    def test_movielens_csvs_are_converted_to_videorank_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dataset = tmp / "ml-latest-small"
            dataset.mkdir()
            (dataset / "movies.csv").write_text(
                "\n".join(
                    [
                        "movieId,title,genres",
                        "1,Toy Story (1995),Adventure|Animation|Children",
                        "2,Jumanji (1995),Adventure|Children|Fantasy",
                    ]
                ),
                encoding="utf-8",
            )
            (dataset / "ratings.csv").write_text(
                "\n".join(
                    [
                        "userId,movieId,rating,timestamp",
                        "10,1,5.0,964982703",
                        "10,2,2.5,964982704",
                    ]
                ),
                encoding="utf-8",
            )
            output = tmp / "events.jsonl"
            summary = prepare_movielens_events(dataset, output)
            rows = output.read_text(encoding="utf-8").splitlines()

        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["users"], 1)
        self.assertEqual(summary["items"], 2)
        self.assertIn('"video_id": "movie_1"', rows[0])
        self.assertIn('"label": 1', rows[0])
        self.assertIn('"label": 0', rows[1])

    def test_matrix_factorization_training_writes_model_artifact(self) -> None:
        try:
            import numpy  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("numpy is not installed")

        from videorank.model.train_movielens import train_movielens_model

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            events = tmp / "events.jsonl"
            events.write_text(
                "\n".join(
                    [
                        '{"event_id":"1","user_id":"u1","video_id":"v1","timestamp":"2024-01-01T00:00:00+00:00","label":1,"rating":5,"category":"drama"}',
                        '{"event_id":"2","user_id":"u1","video_id":"v2","timestamp":"2024-01-02T00:00:00+00:00","label":0,"rating":2,"category":"drama"}',
                        '{"event_id":"3","user_id":"u2","video_id":"v1","timestamp":"2024-01-03T00:00:00+00:00","label":1,"rating":4,"category":"drama"}',
                        '{"event_id":"4","user_id":"u2","video_id":"v2","timestamp":"2024-01-04T00:00:00+00:00","label":0,"rating":1,"category":"drama"}',
                        '{"event_id":"5","user_id":"u3","video_id":"v1","timestamp":"2024-01-05T00:00:00+00:00","label":1,"rating":5,"category":"drama"}',
                    ]
                ),
                encoding="utf-8",
            )
            model_dir = tmp / "model"
            metrics = train_movielens_model(events, model_dir, epochs=1, factors=4)
            self.assertTrue((model_dir / "model.json").exists())
            self.assertTrue((model_dir / "metrics.json").exists())

        self.assertIn("model_ndcg_at_10", metrics)


if __name__ == "__main__":
    unittest.main()

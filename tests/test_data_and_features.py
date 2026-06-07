from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from videorank.data.generate import generate_events, write_jsonl
from videorank.features.offline import (
    build_training_examples,
    read_events,
    temporal_train_eval_split,
)


class DataAndFeatureTests(unittest.TestCase):
    def test_generation_is_deterministic(self) -> None:
        first = [
            event.to_dict() for event in generate_events(users=4, videos=3, events=10, seed=42)
        ]
        second = [
            event.to_dict() for event in generate_events(users=4, videos=3, events=10, seed=42)
        ]
        self.assertEqual(first, second)

    def test_jsonl_roundtrip_and_temporal_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            write_jsonl(generate_events(users=5, videos=4, events=20, seed=3), path)
            events = read_events(path)
        train, eval_rows = temporal_train_eval_split(events, eval_fraction=0.25)
        self.assertEqual(len(train), 15)
        self.assertEqual(len(eval_rows), 5)
        self.assertLessEqual(train[-1]["timestamp"], eval_rows[0]["timestamp"])

    def test_features_are_emitted_before_current_event_updates_stats(self) -> None:
        events = [event.to_dict() for event in generate_events(users=1, videos=1, events=3, seed=9)]
        examples = build_training_examples(events)
        self.assertEqual(len(examples), 3)
        self.assertEqual(examples[0].features[5], 0.0)
        self.assertGreaterEqual(examples[1].features[5], 0.0)


if __name__ == "__main__":
    unittest.main()

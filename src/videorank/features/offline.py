from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

FEATURE_NAMES = [
    "global_ctr",
    "user_category_ctr",
    "video_ctr",
    "device_category_ctr",
    "country_category_ctr",
    "video_impressions_log",
]


@dataclass(frozen=True)
class TrainingExample:
    event_id: str
    user_id: str
    video_id: str
    timestamp: str
    features: list[float]
    label: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "video_id": self.video_id,
            "timestamp": self.timestamp,
            "features": self.features,
            "label": self.label,
        }


def read_events(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(rows: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def temporal_train_eval_split(
    events: list[dict[str, Any]], eval_fraction: float = 0.2
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 0 < eval_fraction < 1:
        raise ValueError("eval_fraction must be between 0 and 1")
    sorted_events = sorted(events, key=lambda row: row["timestamp"])
    split_at = max(1, int(len(sorted_events) * (1 - eval_fraction)))
    return sorted_events[:split_at], sorted_events[split_at:]


def _ratio(clicks: int, impressions: int, prior: float = 0.08, strength: int = 20) -> float:
    return (clicks + prior * strength) / (impressions + strength)


def build_training_examples(events: list[dict[str, Any]]) -> list[TrainingExample]:
    """Build examples using only historical aggregates before each event.

    This online aggregation pattern is intentionally used to prevent feature leakage:
    the current event updates statistics only after its feature vector is emitted.
    """

    global_impressions = 0
    global_clicks = 0
    user_category: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    video: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    device_category: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    country_category: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    examples: list[TrainingExample] = []

    for event in sorted(events, key=lambda row: row["timestamp"]):
        category = event["category"]
        user_key = (event["user_id"], category)
        device_key = (event["device"], category)
        country_key = (event["country"], category)
        video_stats = video[event["video_id"]]
        label = int(event.get("label", 0))
        features = [
            _ratio(global_clicks, global_impressions),
            _ratio(user_category[user_key][1], user_category[user_key][0]),
            _ratio(video_stats[1], video_stats[0]),
            _ratio(device_category[device_key][1], device_category[device_key][0]),
            _ratio(country_category[country_key][1], country_category[country_key][0]),
            math.log1p(video_stats[0]) / 10.0,
        ]
        examples.append(
            TrainingExample(
                event_id=event["event_id"],
                user_id=event["user_id"],
                video_id=event["video_id"],
                timestamp=event["timestamp"],
                features=features,
                label=label,
            )
        )

        global_impressions += int(event.get("impression", 1))
        global_clicks += int(event.get("clicked", label))
        user_category[user_key][0] += 1
        user_category[user_key][1] += label
        video[event["video_id"]][0] += 1
        video[event["video_id"]][1] += label
        device_category[device_key][0] += 1
        device_category[device_key][1] += label
        country_category[country_key][0] += 1
        country_category[country_key][1] += label

    return examples


def build_video_catalog(events: list[dict[str, Any]], top_n: int = 200) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for event in events:
        row = stats.setdefault(
            event["video_id"],
            {
                "video_id": event["video_id"],
                "category": event["category"],
                "impressions": 0,
                "clicks": 0,
                "positive_labels": 0,
            },
        )
        row["impressions"] += int(event.get("impression", 1))
        row["clicks"] += int(event.get("clicked", 0))
        row["positive_labels"] += int(event.get("label", 0))

    catalog = []
    for row in stats.values():
        impressions = row["impressions"]
        row["ctr"] = _ratio(row["clicks"], impressions)
        row["positive_rate"] = _ratio(row["positive_labels"], impressions)
        catalog.append(row)
    return sorted(catalog, key=lambda row: (row["positive_rate"], row["impressions"]), reverse=True)[:top_n]


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


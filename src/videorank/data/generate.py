from __future__ import annotations

import argparse
import json
import random
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from videorank.data.schema import User, Video, WatchEvent

CATEGORIES = ["sports", "music", "news", "gaming", "fashion", "travel", "food", "tech"]
COUNTRIES = ["FR", "US", "GB", "DE", "ES", "BR", "IN"]
DEVICES = ["mobile", "desktop", "tablet", "tv"]


def build_users(count: int, rng: random.Random) -> list[User]:
    return [
        User(
            user_id=f"user_{idx:05d}",
            country=rng.choice(COUNTRIES),
            device=rng.choices(DEVICES, weights=[0.58, 0.24, 0.10, 0.08])[0],
            signup_days_ago=rng.randint(1, 1200),
        )
        for idx in range(count)
    ]


def build_videos(count: int, rng: random.Random) -> list[Video]:
    return [
        Video(
            video_id=f"video_{idx:05d}",
            category=rng.choice(CATEGORIES),
            creator_id=f"creator_{rng.randint(1, max(5, count // 8)):04d}",
            duration_s=rng.randint(20, 900),
            age_days=rng.randint(0, 365),
        )
        for idx in range(count)
    ]


def _user_preferences(users: Iterable[User], rng: random.Random) -> dict[str, dict[str, float]]:
    preferences: dict[str, dict[str, float]] = {}
    for user in users:
        favorite = rng.choice(CATEGORIES)
        second = rng.choice([category for category in CATEGORIES if category != favorite])
        weights = {category: 0.05 for category in CATEGORIES}
        weights[favorite] = 0.55
        weights[second] = 0.20
        preferences[user.user_id] = weights
    return preferences


def generate_events(
    users: int = 500,
    videos: int = 200,
    events: int = 20_000,
    seed: int = 7,
    start: datetime | None = None,
) -> list[WatchEvent]:
    rng = random.Random(seed)
    user_rows = build_users(users, rng)
    video_rows = build_videos(videos, rng)
    preferences = _user_preferences(user_rows, rng)
    start_time = start or datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[WatchEvent] = []

    for idx in range(events):
        user = rng.choice(user_rows)
        video = rng.choice(video_rows)
        preference = preferences[user.user_id][video.category]
        recency_boost = max(0.0, 1.0 - video.age_days / 365.0) * 0.08
        device_boost = 0.04 if user.device in {"mobile", "tv"} else 0.0
        click_probability = min(0.92, 0.05 + preference + recency_boost + device_boost)
        clicked = 1 if rng.random() < click_probability else 0
        short_video_boost = 0.15 if video.duration_s <= 180 else 0.0
        completion_probability = min(0.9, 0.12 + preference + short_video_boost)
        completed = 1 if clicked and rng.random() < completion_probability else 0
        watch_time = 0
        if clicked:
            base_watch = int(video.duration_s * rng.uniform(0.05, 0.55))
            watch_time = (
                video.duration_s if completed else min(video.duration_s, max(3, base_watch))
            )
        rows.append(
            WatchEvent(
                event_id=f"event_{idx:08d}",
                user_id=user.user_id,
                video_id=video.video_id,
                category=video.category,
                country=user.country,
                device=user.device,
                timestamp=start_time + timedelta(seconds=idx * 180 + rng.randint(0, 120)),
                impression=1,
                clicked=clicked,
                watch_time_s=watch_time,
                completed=completed,
            )
        )
    return rows


def write_jsonl(events: Iterable[WatchEvent], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic video events.")
    parser.add_argument("--output", type=Path, default=Path("data/events.jsonl"))
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--videos", type=int, default=200)
    parser.add_argument("--events", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    write_jsonl(generate_events(args.users, args.videos, args.events, args.seed), args.output)
    print(f"wrote {args.events} events to {args.output}")


if __name__ == "__main__":
    main()

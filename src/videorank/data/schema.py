from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class User:
    user_id: str
    country: str
    device: str
    signup_days_ago: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Video:
    video_id: str
    category: str
    creator_id: str
    duration_s: int
    age_days: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchEvent:
    event_id: str
    user_id: str
    video_id: str
    category: str
    country: str
    device: str
    timestamp: datetime
    impression: int
    clicked: int
    watch_time_s: int
    completed: int

    @property
    def label(self) -> int:
        return 1 if self.clicked and (self.completed or self.watch_time_s >= 30) else 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.astimezone(UTC).isoformat()
        payload["label"] = self.label
        return payload


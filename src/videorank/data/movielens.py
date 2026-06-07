from __future__ import annotations

import argparse
import csv
import json
import shutil
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MOVIELENS_LATEST_SMALL_URL = (
    "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
)


@dataclass(frozen=True)
class MovieLensMovie:
    movie_id: str
    title: str
    genres: list[str]

    @property
    def primary_genre(self) -> str:
        if not self.genres or self.genres == ["(no genres listed)"]:
            return "unknown"
        return self.genres[0].lower().replace(" ", "_")


@dataclass(frozen=True)
class MovieLensInteraction:
    user_id: str
    video_id: str
    rating: float
    timestamp: int
    title: str
    category: str

    @property
    def label(self) -> int:
        return int(self.rating >= 4.0)

    def to_event(self) -> dict[str, Any]:
        timestamp = datetime.fromtimestamp(self.timestamp, UTC).isoformat()
        watch_time_s = int(max(30, min(900, self.rating / 5.0 * 600)))
        return {
            "event_id": f"movielens_{self.user_id}_{self.video_id}_{self.timestamp}",
            "user_id": f"user_{self.user_id}",
            "video_id": f"movie_{self.video_id}",
            "video_title": self.title,
            "category": self.category,
            "country": "US",
            "device": "web",
            "timestamp": timestamp,
            "impression": 1,
            "clicked": int(self.rating >= 3.0),
            "watch_time_s": watch_time_s,
            "completed": int(self.rating >= 4.5),
            "rating": self.rating,
            "label": self.label,
        }


def download_movielens(output_zip: Path, dataset_url: str = MOVIELENS_LATEST_SMALL_URL) -> Path:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(dataset_url, timeout=60) as response, output_zip.open(
        "wb"
    ) as handle:
        shutil.copyfileobj(response, handle)
    return output_zip


def extract_movielens(zip_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(output_dir)
    extracted_dirs = [path for path in output_dir.iterdir() if path.is_dir()]
    if not extracted_dirs:
        raise ValueError(f"no dataset directory found in {zip_path}")
    return extracted_dirs[0]


def read_movies(path: Path) -> dict[str, MovieLensMovie]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            row["movieId"]: MovieLensMovie(
                movie_id=row["movieId"],
                title=row["title"],
                genres=row["genres"].split("|"),
            )
            for row in rows
        }


def read_interactions(
    ratings_path: Path,
    movies: dict[str, MovieLensMovie],
    max_ratings: int | None = None,
) -> list[MovieLensInteraction]:
    interactions: list[MovieLensInteraction] = []
    with ratings_path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        for index, row in enumerate(rows):
            if max_ratings is not None and index >= max_ratings:
                break
            movie = movies.get(row["movieId"])
            if movie is None:
                continue
            interactions.append(
                MovieLensInteraction(
                    user_id=row["userId"],
                    video_id=row["movieId"],
                    rating=float(row["rating"]),
                    timestamp=int(row["timestamp"]),
                    title=movie.title,
                    category=movie.primary_genre,
                )
            )
    return sorted(interactions, key=lambda item: item.timestamp)


def write_events_jsonl(interactions: Iterable[MovieLensInteraction], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for interaction in interactions:
            count += 1
            handle.write(json.dumps(interaction.to_event(), sort_keys=True) + "\n")
    return count


def prepare_movielens_events(
    dataset_dir: Path,
    output_path: Path,
    max_ratings: int | None = None,
) -> dict[str, int]:
    movies = read_movies(dataset_dir / "movies.csv")
    interactions = read_interactions(dataset_dir / "ratings.csv", movies, max_ratings=max_ratings)
    rows = write_events_jsonl(interactions, output_path)
    users = {interaction.user_id for interaction in interactions}
    items = {interaction.video_id for interaction in interactions}
    positives = sum(interaction.label for interaction in interactions)
    return {"rows": rows, "users": len(users), "items": len(items), "positives": positives}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare MovieLens events.")
    parser.add_argument("--dataset-url", default=MOVIELENS_LATEST_SMALL_URL)
    parser.add_argument("--work-dir", type=Path, default=Path("data/movielens"))
    parser.add_argument("--output", type=Path, default=Path("data/movielens/events.jsonl"))
    parser.add_argument("--max-ratings", type=int, default=100000)
    args = parser.parse_args()

    zip_path = download_movielens(args.work_dir / "ml-latest-small.zip", args.dataset_url)
    dataset_dir = extract_movielens(zip_path, args.work_dir)
    summary = prepare_movielens_events(
        dataset_dir,
        args.output,
        max_ratings=args.max_ratings if args.max_ratings > 0 else None,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

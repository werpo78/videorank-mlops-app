from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videorank.features.offline import read_events, temporal_train_eval_split
from videorank.model.matrix_factorization import MatrixFactorizationRanker
from videorank.model.metrics import auc_score, brier_score, grouped_by_user, ndcg_at_k, recall_at_k


def _catalog(rows: list[dict[str, Any]], top_n: int = 500) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = stats.setdefault(
            row["video_id"],
            {
                "video_id": row["video_id"],
                "video_title": row.get("video_title", row["video_id"]),
                "category": row.get("category", "unknown"),
                "ratings": 0,
                "positive_labels": 0,
                "rating_sum": 0.0,
            },
        )
        item["ratings"] += 1
        item["positive_labels"] += int(row["label"])
        item["rating_sum"] += float(row.get("rating", 0.0))
    catalog = []
    for item in stats.values():
        ratings = int(item["ratings"])
        item["positive_rate"] = (item["positive_labels"] + 2.0) / (ratings + 4.0)
        item["mean_rating"] = item["rating_sum"] / ratings if ratings else 0.0
        catalog.append(item)
    return sorted(catalog, key=lambda item: (item["positive_rate"], item["ratings"]), reverse=True)[
        :top_n
    ]


def _baseline_scores(
    train_rows: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
) -> list[float]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    global_positive = 0
    for row in train_rows:
        counts[row["video_id"]][0] += 1
        counts[row["video_id"]][1] += int(row["label"])
        global_positive += int(row["label"])
    global_rate = (global_positive + 2.0) / (len(train_rows) + 4.0)
    return [
        (counts[row["video_id"]][1] + global_rate * 8.0) / (counts[row["video_id"]][0] + 8.0)
        for row in eval_rows
    ]


def _evaluate(
    eval_rows: list[dict[str, Any]],
    scores: list[float],
    prefix: str,
) -> dict[str, float]:
    labels = [int(row["label"]) for row in eval_rows]
    users = [row["user_id"] for row in eval_rows]
    groups = grouped_by_user(users, labels, scores)
    return {
        f"{prefix}_auc": auc_score(labels, scores),
        f"{prefix}_brier": brier_score(labels, scores),
        f"{prefix}_recall_at_10": recall_at_k(groups, 10),
        f"{prefix}_ndcg_at_10": ndcg_at_k(groups, 10),
    }


def train_movielens_model(
    events_path: Path,
    output_dir: Path,
    model_version: str | None = None,
    factors: int = 24,
    epochs: int = 8,
    learning_rate: float = 0.05,
    regularization: float = 0.002,
) -> dict[str, float]:
    rows = read_events(events_path)
    train_rows, eval_rows = temporal_train_eval_split(rows, eval_fraction=0.2)
    ranker = MatrixFactorizationRanker.fresh(
        [row["user_id"] for row in train_rows],
        [row["video_id"] for row in train_rows],
        factors=factors,
    )
    ranker.fit(
        train_rows,
        epochs=epochs,
        learning_rate=learning_rate,
        regularization=regularization,
    )

    model_scores = [
        ranker.predict_proba(row["user_id"], row["video_id"])
        for row in eval_rows
    ]
    baseline_scores = _baseline_scores(train_rows, eval_rows)
    metrics = {
        **_evaluate(eval_rows, baseline_scores, "baseline"),
        **_evaluate(eval_rows, model_scores, "model"),
        "train_interactions": float(len(train_rows)),
        "eval_interactions": float(len(eval_rows)),
        "users": float(len({row["user_id"] for row in rows})),
        "items": float(len({row["video_id"] for row in rows})),
    }
    metrics["ndcg_at_10_lift"] = metrics["model_ndcg_at_10"] - metrics["baseline_ndcg_at_10"]
    metrics["recall_at_10_lift"] = (
        metrics["model_recall_at_10"] - metrics["baseline_recall_at_10"]
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    version = model_version or os.getenv("GITHUB_SHA", "local-movielens")
    extra = {
        "model_version": version,
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset": "MovieLens latest-small",
        "metrics": metrics,
        "catalog": _catalog(train_rows),
    }
    ranker.save(output_dir / "model.json", extra=extra)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_model_card(output_dir / "MODEL_CARD.md", version, metrics)
    return metrics


def write_model_card(path: Path, model_version: str, metrics: dict[str, float]) -> None:
    path.write_text(
        "\n".join(
            [
                "# VideoRank MovieLens Model Card",
                "",
                f"Model version: `{model_version}`",
                "",
                "## Dataset",
                "MovieLens latest-small, adapted as user-video interaction data.",
                "",
                "## Model",
                "Implicit-style matrix factorization with user and item embeddings,",
                "trained with logistic loss on explicit ratings converted to binary labels.",
                "",
                "## Validation",
                "Temporal split. Evaluation compares the embedding ranker to popularity baseline.",
                "",
                "## Metrics",
                *[f"- `{name}`: {value:.4f}" for name, value in metrics.items()],
                "",
                "## Production Guardrails",
                "- Keep popularity baseline as fallback.",
                "- Promote only if offline ranking metrics and serving constraints pass.",
                "- Run online A/B or canary before full rollout.",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Matrix Factorization on MovieLens events.")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/movielens-model"))
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--factors", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--regularization", type=float, default=0.002)
    args = parser.parse_args()
    metrics = train_movielens_model(
        args.events,
        args.output_dir,
        model_version=args.model_version,
        factors=args.factors,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        regularization=args.regularization,
    )
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

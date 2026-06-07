from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from videorank.features.offline import (
    FEATURE_NAMES,
    build_training_examples,
    build_video_catalog,
    read_events,
    temporal_train_eval_split,
    write_jsonl,
)
from videorank.model.metrics import auc_score, brier_score, grouped_by_user, ndcg_at_k, recall_at_k
from videorank.model.ranker import SimpleLogisticRanker


def train_from_events(
    events_path: Path,
    output_dir: Path,
    model_version: str | None = None,
) -> dict[str, float]:
    events = read_events(events_path)
    train_events, eval_events = temporal_train_eval_split(events)
    train_examples = build_training_examples(train_events)
    eval_examples = build_training_examples(eval_events)

    ranker = SimpleLogisticRanker.fresh(FEATURE_NAMES)
    ranker.fit(
        [example.features for example in train_examples],
        [example.label for example in train_examples],
    )
    eval_scores = [ranker.predict_proba(example.features) for example in eval_examples]
    eval_labels = [example.label for example in eval_examples]
    eval_users = [example.user_id for example in eval_examples]
    groups = grouped_by_user(eval_users, eval_labels, eval_scores)
    metrics = {
        "auc": auc_score(eval_labels, eval_scores),
        "brier": brier_score(eval_labels, eval_scores),
        "recall_at_10": recall_at_k(groups, 10),
        "ndcg_at_10": ndcg_at_k(groups, 10),
        "train_examples": float(len(train_examples)),
        "eval_examples": float(len(eval_examples)),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    version = model_version or os.getenv("GITHUB_SHA", "local")
    catalog = build_video_catalog(train_events)
    ranker.save(
        output_dir / "model.json",
        extra={
            "model_version": version,
            "trained_at": datetime.now(UTC).isoformat(),
            "feature_names": FEATURE_NAMES,
            "metrics": metrics,
            "catalog": catalog,
        },
    )
    write_jsonl(
        (example.to_dict() for example in train_examples),
        output_dir / "training_examples.jsonl",
    )
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
                "# VideoRank Model Card",
                "",
                f"Model version: `{model_version}`",
                "",
                "## Intended Use",
                "Rank candidate videos for a synthetic recommendation API demo.",
                "",
                "## Validation",
                "Temporal split is used to avoid training on future events.",
                "",
                "## Metrics",
                *[f"- `{name}`: {value:.4f}" for name, value in metrics.items()],
                "",
                "## Production Guardrails",
                "- Keep a popularity baseline as fallback.",
                "- Promote only after offline metrics beat baseline and serving tests pass.",
                "- Monitor drift, latency, errors, fallback rate and business feedback.",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the VideoRank ranking model.")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/model"))
    parser.add_argument("--model-version", default=None)
    args = parser.parse_args()
    metrics = train_from_events(args.events, args.output_dir, args.model_version)
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

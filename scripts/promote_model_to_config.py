from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml

PROMOTION_ENV_KEYS = [
    "VIDEORANK_MODEL_URI",
    "VIDEORANK_MODEL_VERSION",
    "VIDEORANK_VERTEX_MODEL_RESOURCE",
    "VIDEORANK_DATA_SNAPSHOT_ID",
    "VIDEORANK_MODEL_GIT_SHA",
    "VIDEORANK_MODEL_PROMOTED_AT",
    "VIDEORANK_MODEL_PROMOTION_REASON",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update a VideoRank Helm values file with a promoted model."
    )
    parser.add_argument("--values-path", type=Path, required=True)
    parser.add_argument("--model-artifact-uri", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--vertex-model-resource", default="")
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--data-snapshot-id", default="")
    parser.add_argument("--promotion-reason", default="")
    parser.add_argument("--promoted-at", default="")
    return parser.parse_args()


def validate_model_artifact_uri(uri: str) -> None:
    if uri.startswith("gs://") or uri.startswith("file://"):
        return
    raise ValueError("model artifact URI must start with gs:// or file://")


def update_values(path: Path, args: argparse.Namespace) -> dict[str, str]:
    validate_model_artifact_uri(args.model_artifact_uri)
    values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    env = values.setdefault("env", {})
    promoted_at = args.promoted_at or datetime.now(UTC).isoformat()
    updates = {
        "VIDEORANK_MODEL_URI": args.model_artifact_uri,
        "VIDEORANK_MODEL_VERSION": args.model_version,
        "VIDEORANK_VERTEX_MODEL_RESOURCE": args.vertex_model_resource,
        "VIDEORANK_DATA_SNAPSHOT_ID": args.data_snapshot_id,
        "VIDEORANK_MODEL_GIT_SHA": args.git_sha,
        "VIDEORANK_MODEL_PROMOTED_AT": promoted_at,
        "VIDEORANK_MODEL_PROMOTION_REASON": args.promotion_reason,
    }
    for key in PROMOTION_ENV_KEYS:
        env[key] = updates[key]
    path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
    return updates


def main() -> None:
    args = parse_args()
    updates = update_values(args.values_path, args)
    for key, value in updates.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()

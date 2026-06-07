from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

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


def _split_comment(line: str) -> tuple[str, str]:
    prefix, sep, comment = line.partition("#")
    if not sep:
        return prefix.rstrip(), ""
    return prefix.rstrip(), f" # {comment.strip()}"


def _replace_yaml_value_preserving_comment(line: str, value: str) -> str:
    prefix, comment = _split_comment(line)
    indent = prefix[: len(prefix) - len(prefix.lstrip())]
    key = prefix.strip().split(":", 1)[0]
    rendered_value = "''" if value == "" else value
    return f"{indent}{key}: {rendered_value}{comment}"


def _render_env_line(key: str, value: str) -> str:
    rendered_value = value if value else "''"
    return f"  {key}: {rendered_value}"


def _update_env_values(text: str, updates: dict[str, str]) -> str:
    lines = text.splitlines()
    rendered: list[str] = []
    in_env = False
    env_indent: int | None = None
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "env:":
            in_env = True
            env_indent = indent
            rendered.append(line)
            continue

        if in_env and stripped and env_indent is not None and indent <= env_indent:
            for key in PROMOTION_ENV_KEYS:
                if key not in seen:
                    rendered.append(_render_env_line(key, updates[key]))
                    seen.add(key)
            in_env = False
            env_indent = None

        if in_env and ":" in stripped:
            key = stripped.split(":", 1)[0]
            if key in updates:
                rendered.append(_replace_yaml_value_preserving_comment(line, updates[key]))
                seen.add(key)
                continue

        rendered.append(line)

    if in_env:
        for key in PROMOTION_ENV_KEYS:
            if key not in seen:
                rendered.append(_render_env_line(key, updates[key]))
                seen.add(key)

    if not any(line.strip() == "env:" for line in lines):
        rendered.append("env:")
        for key in PROMOTION_ENV_KEYS:
            rendered.append(_render_env_line(key, updates[key]))

    return "\n".join(rendered) + "\n"


def update_values(path: Path, args: argparse.Namespace) -> dict[str, str]:
    validate_model_artifact_uri(args.model_artifact_uri)
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
    text = path.read_text(encoding="utf-8")
    path.write_text(_update_env_values(text, updates), encoding="utf-8")
    return updates


def main() -> None:
    args = parse_args()
    updates = update_values(args.values_path, args)
    for key, value in updates.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from pipeline import MOVIELENS_LATEST_SMALL_URL, compile_pipeline

_LABEL_PATTERN = re.compile(r"[^a-z0-9_-]")


def sanitize_label_value(value: str, *, fallback: str = "unknown") -> str:
    sanitized = _LABEL_PATTERN.sub("_", value.lower()).strip("_-.")
    if sanitized and not sanitized[0].isalpha():
        sanitized = f"v_{sanitized}"
    return (sanitized[:63].strip("_-.") or fallback)


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


def parse_labels(values: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise SystemExit(f"invalid label {raw!r}; expected key=value")
        key, value = raw.split("=", 1)
        labels[sanitize_label_value(key)] = sanitize_label_value(value)
    return labels


def build_parameter_values(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "dataset_url": args.dataset_url,
        "max_ratings": args.max_ratings,
        "data_snapshot_id": args.data_snapshot_id,
        "git_sha": args.git_sha,
        "run_id": args.run_id,
        "project_id": args.project_id,
        "location": args.region,
        "bigquery_dataset": args.bigquery_dataset,
        "bigquery_location": args.bigquery_location,
        "feature_table_id": args.feature_table_id,
        "feature_online_store_id": args.feature_online_store_id,
        "feature_view_id": args.feature_view_id,
        "experiment_name": args.experiment_name,
        "serving_container_image_uri": args.serving_container_image_uri,
        "enable_vertex_datasets": args.enable_vertex_datasets,
        "enable_vertex_feature_store": args.enable_vertex_feature_store,
        "enable_vertex_experiments": args.enable_vertex_experiments,
        "enable_vertex_model_registry": args.enable_vertex_model_registry,
        "factors": args.factors,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "regularization": args.regularization,
        "seed": args.seed,
        "min_model_ndcg_at_10": args.min_model_ndcg_at_10,
        "min_ndcg_lift": args.min_ndcg_lift,
    }


def submit_pipeline(
    project_id: str,
    region: str,
    pipeline_root: str,
    service_account: str,
    template_path: Path,
    display_name: str,
    sync: bool,
    parameter_values: dict[str, Any],
    labels: dict[str, str],
) -> None:
    try:
        from google.cloud import aiplatform
    except ImportError as exc:
        raise SystemExit(
            "google-cloud-aiplatform is not installed. Install with `pip install -e .[pipelines]`."
        ) from exc

    access_token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    credentials = None
    if access_token:
        from google.oauth2.credentials import Credentials

        credentials = Credentials(token=access_token)

    aiplatform.init(
        project=project_id,
        location=region,
        staging_bucket=pipeline_root,
        credentials=credentials,
    )
    job = aiplatform.PipelineJob(
        display_name=display_name,
        template_path=str(template_path),
        pipeline_root=pipeline_root,
        parameter_values=parameter_values,
        labels=labels,
        enable_caching=True,
    )
    job.submit(service_account=service_account)
    print(f"submitted Vertex AI PipelineJob: {job.resource_name}")
    if sync:
        job.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit the VideoRank KFP pipeline to Vertex AI.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", default="europe-west1")
    parser.add_argument("--pipeline-root", required=True)
    parser.add_argument("--service-account", required=True)
    parser.add_argument(
        "--template-path",
        type=Path,
        default=Path("artifacts/pipelines/videorank_movielens_training.yaml"),
    )
    parser.add_argument("--display-name", default="videorank-movielens-training")
    parser.add_argument("--dataset-url", default=MOVIELENS_LATEST_SMALL_URL)
    parser.add_argument("--max-ratings", type=int, default=25000)
    parser.add_argument("--data-snapshot-id", default="movielens-latest-small-static")
    parser.add_argument("--git-sha", default=os.getenv("GITHUB_SHA", "local"))
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", "local"))
    parser.add_argument("--bigquery-dataset", default="videorank")
    parser.add_argument("--bigquery-location", default="EU")
    parser.add_argument("--feature-table-id", default="vertex_user_features")
    parser.add_argument("--feature-online-store-id", default="videorank_dev_store")
    parser.add_argument("--feature-view-id", default="user_features")
    parser.add_argument("--experiment-name", default="videorank-continuous-training")
    parser.add_argument("--serving-container-image-uri", default="")
    parser.add_argument("--enable-vertex-datasets", type=parse_bool, default=True)
    parser.add_argument("--enable-vertex-feature-store", type=parse_bool, default=False)
    parser.add_argument("--enable-vertex-experiments", type=parse_bool, default=True)
    parser.add_argument("--enable-vertex-model-registry", type=parse_bool, default=True)
    parser.add_argument("--factors", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--regularization", type=float, default=0.002)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-model-ndcg-at-10", type=float, default=0.05)
    parser.add_argument("--min-ndcg-lift", type=float, default=-0.02)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()

    if not args.template_path.exists():
        compile_pipeline(args.template_path)

    submit_pipeline(
        project_id=args.project_id,
        region=args.region,
        pipeline_root=args.pipeline_root,
        service_account=args.service_account,
        template_path=args.template_path,
        display_name=args.display_name,
        sync=args.sync,
        parameter_values=build_parameter_values(args),
        labels=parse_labels(args.label),
    )


if __name__ == "__main__":
    main()

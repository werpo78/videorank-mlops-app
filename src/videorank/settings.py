from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    environment: str
    model_path: str
    prediction_log_table: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "videorank-mlops-dev")
        dataset = os.getenv("VIDEORANK_BQ_DATASET", "videorank")
        return cls(
            project_id=project_id,
            region=os.getenv("GCP_REGION", "europe-west1"),
            environment=os.getenv("VIDEORANK_ENV", "dev"),
            model_path=os.getenv(
                "VIDEORANK_MODEL_PATH",
                "src/videorank/resources/seed_model.json",
            ),
            prediction_log_table=os.getenv(
                "VIDEORANK_PREDICTION_LOG_TABLE",
                f"{project_id}.{dataset}.prediction_logs",
            ),
        )

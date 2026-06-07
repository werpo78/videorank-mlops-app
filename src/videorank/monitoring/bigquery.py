from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from videorank.model.serving import write_prediction_log


class PredictionLogger:
    def __init__(self, table_id: str | None, local_path: Path):
        self.table_id = table_id
        self.local_path = local_path
        self.enabled = os.getenv("VIDEORANK_ENABLE_BIGQUERY_LOGGING", "false").lower() == "true"
        self._client: Any | None = None

    def write(self, payload: dict[str, Any]) -> None:
        write_prediction_log(self.local_path, payload)
        if not self.enabled or not self.table_id:
            return
        client = self._bigquery_client()
        row = dict(payload)
        if isinstance(row.get("recommendations"), list):
            row["recommendations"] = row["recommendations"]
        errors = client.insert_rows_json(self.table_id, [row])
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")

    def _bigquery_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import bigquery
            except ImportError as exc:
                raise RuntimeError(
                    "google-cloud-bigquery is required when VIDEORANK_ENABLE_BIGQUERY_LOGGING=true"
                ) from exc
            self._client = bigquery.Client()
        return self._client


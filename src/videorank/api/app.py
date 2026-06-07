from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

from videorank.model.serving import load_engine, write_prediction_log
from videorank.monitoring.bigquery import PredictionLogger
from videorank.settings import Settings

REQUESTS = Counter(
    "videorank_recommendation_requests_total",
    "Recommendation requests by variant and status.",
    ["variant", "status"],
)
LATENCY = Histogram(
    "videorank_recommendation_latency_seconds",
    "Recommendation request latency in seconds.",
    ["variant"],
)
FEEDBACK = Counter("videorank_feedback_events_total", "Feedback events by type.", ["event_type"])


class RecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)
    experiment_id: str = "videorank-default"


class RecommendationItem(BaseModel):
    video_id: str
    score: float
    reason: str


class RecommendationResponse(BaseModel):
    request_id: str
    variant: str
    model_version: str
    recommendations: list[RecommendationItem]


class FeedbackRequest(BaseModel):
    request_id: str
    user_id: str
    video_id: str
    event_type: str
    watch_time_s: int = Field(default=0, ge=0)
    timestamp: str | None = None


def create_app() -> FastAPI:
    settings = Settings.from_env()
    engine = load_engine(settings.model_path)
    app = FastAPI(title="VideoRank Recommendation API", version="0.1.0")
    prediction_logger = PredictionLogger(
        table_id=settings.prediction_log_table,
        local_path=Path("artifacts/prediction_logs.jsonl"),
    )

    def health_payload() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_payload()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return health_payload()

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ready", "model_version": engine.model_version}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/recommendations", response_model=RecommendationResponse)
    def recommendations(request: RecommendationRequest) -> RecommendationResponse:
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        result = engine.recommend(
            request.user_id,
            context=request.context,
            limit=request.limit,
            experiment_id=request.experiment_id,
        )
        variant = result["variant"]
        REQUESTS.labels(variant=variant, status="ok").inc()
        LATENCY.labels(variant=variant).observe(time.perf_counter() - start)
        payload = {
            "request_id": request_id,
            "user_id": request.user_id,
            "variant": variant,
            "model_version": result["model_version"],
            "limit": request.limit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recommendations": result["recommendations"],
        }
        prediction_logger.write(payload)
        return RecommendationResponse(request_id=request_id, **result)

    @app.post("/feedback")
    def feedback(request: FeedbackRequest) -> dict[str, str]:
        FEEDBACK.labels(event_type=request.event_type).inc()
        payload = request.model_dump()
        payload["timestamp"] = payload["timestamp"] or datetime.now(timezone.utc).isoformat()
        write_prediction_log(Path("artifacts/feedback_logs.jsonl"), payload)
        return {"status": "accepted"}

    return app


def main() -> None:
    import uvicorn

    uvicorn.run("videorank.api.app:create_app", factory=True, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()

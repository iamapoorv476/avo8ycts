"""
All three endpoints are pure reads over precomputed data -- there is no
forecast/metric computation in the request path, only in the offline
ingestion pipeline (ingestion/run_ingestion_pipeline.py). See docs/api.md.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import forecast_detail, metrics, risk_floor

app = FastAPI(
    title="Wind Generation Forecast Accuracy API",
    description="Read-only API over precomputed day-ahead wind forecast accuracy data (January 2026, GB).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(forecast_detail.router, prefix="/api/v1", tags=["forecast"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(risk_floor.router, prefix="/api/v1", tags=["risk-floor"])


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
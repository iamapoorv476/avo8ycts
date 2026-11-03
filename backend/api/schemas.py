"""Pydantic response models for the three read-only API endpoints.

All three endpoints are pure reads over precomputed data (populated by the
offline ingestion pipeline, ingestion/run_ingestion_pipeline.py) -- no
forecast/metric business logic lives in this request path, only shaping
precomputed rows into a response.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ForecastDetailPeriod(BaseModel):
    settlementPeriod: int
    startTime: str
    forecastMw: Optional[float]
    sourcePublishTime: Optional[str]
    actualMw: Optional[float]
    status: str


class ForecastDetailResponse(BaseModel):
    date: str
    cutoffApplied: str
    periods: list[ForecastDetailPeriod]


class MetricsResponse(BaseModel):
    scopeType: str
    scopePeriod: str
    segment: str
    mbe: float
    mae: float
    rmse: float
    sigmaResidual: float
    n: int
    excludedCount: int
    exclusionBreakdown: dict[str, int]


class RiskFloorPeriod(BaseModel):
    settlementPeriod: int
    segment: str
    forecastMw: float
    floorMw: float
    advisoryText: str


class RiskFloorResponse(BaseModel):
    date: str
    periods: list[RiskFloorPeriod]
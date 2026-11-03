"""GET /api/v1/forecast-detail -- AC 1.1-1.5.

Pure read over matched_series for a single delivery date: the step-held
decision-time forecast, its source publishTime (audit trail, AC 1.3), the
actual, and a status derived from the precomputed inclusion/exclusion flag.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db
from api.schemas import ForecastDetailPeriod, ForecastDetailResponse

router = APIRouter()

DECISION_CUTOFF_HOUR_UTC = 11


def _cutoff_for_date(delivery_date: date_type) -> str:
    cutoff_date = delivery_date - timedelta(days=1)
    return f"{cutoff_date.isoformat()}T{DECISION_CUTOFF_HOUR_UTC:02d}:00:00Z"


def _status_for(included: int, exclusion_reason: str | None) -> str:
    return "OK" if included else exclusion_reason


@router.get("/forecast-detail", response_model=ForecastDetailResponse)
def get_forecast_detail(
    date: date_type = Query(..., description="Delivery date, YYYY-MM-DD"),
    conn=Depends(get_db),
):
    rows = conn.execute(
        "SELECT settlementPeriod, startTime, forecast_mw, source_publish_time, actual_mw, included, exclusion_reason "
        "FROM matched_series WHERE startTime LIKE ? ORDER BY startTime",
        (f"{date.isoformat()}%",),
    ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast-detail data for {date.isoformat()} -- date may be outside the ingested scope.",
        )

    periods = [
        ForecastDetailPeriod(
            settlementPeriod=row["settlementPeriod"],
            startTime=row["startTime"],
            forecastMw=row["forecast_mw"],
            sourcePublishTime=row["source_publish_time"],
            actualMw=row["actual_mw"],
            status=_status_for(row["included"], row["exclusion_reason"]),
        )
        for row in rows
    ]

    return ForecastDetailResponse(
        date=date.isoformat(),
        cutoffApplied=_cutoff_for_date(date),
        periods=periods,
    )
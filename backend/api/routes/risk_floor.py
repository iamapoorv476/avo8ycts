"""GET /api/v1/risk-floor -- AC 2.4, AC 2.5.

Pure read over matched_series.floor_mw/advisory_text (precomputed by
RiskFloorCalculator) for a single delivery date. Only rows with a forecast
(floor_mw IS NOT NULL) are returned -- a NO_FORECAST_BEFORE_CUTOFF period has
no floor to show, by design (see risk_floor_calculator.py).
"""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db
from api.schemas import RiskFloorPeriod, RiskFloorResponse

router = APIRouter()


@router.get("/risk-floor", response_model=RiskFloorResponse)
def get_risk_floor(
    date: date_type = Query(..., description="Delivery date, YYYY-MM-DD"),
    conn=Depends(get_db),
):
    rows = conn.execute(
        "SELECT settlementPeriod, segment, forecast_mw, floor_mw, advisory_text "
        "FROM matched_series WHERE startTime LIKE ? AND floor_mw IS NOT NULL ORDER BY startTime",
        (f"{date.isoformat()}%",),
    ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No risk-floor data for {date.isoformat()} -- date may be outside the ingested "
                "scope, or no periods that day had a forecast to base a floor on."
            ),
        )

    periods = [
        RiskFloorPeriod(
            settlementPeriod=row["settlementPeriod"],
            segment=row["segment"],
            forecastMw=row["forecast_mw"],
            floorMw=row["floor_mw"],
            advisoryText=row["advisory_text"],
        )
        for row in rows
    ]

    return RiskFloorResponse(date=date.isoformat(), periods=periods)
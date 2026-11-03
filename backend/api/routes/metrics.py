"""GET /api/v1/metrics -- AC 2.2, AC 2.3, AC 2.6.

Pure read over metrics_summary (precomputed by MetricsCalculator) for a
given scope/segment. The exclusion-reason breakdown is the one deliberate
exception to "no computation in the request path": exclusion_reason is
already precomputed per-row at ingest time by SeriesMatcher, so grouping it
by reason for the same scope/segment at request time is a cheap read-side
view over an already-precomputed column, not a recomputation of any
forecast or metric. See docs/api.md for this tradeoff written up explicitly.
"""

from __future__ import annotations

import calendar

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db
from api.schemas import MetricsResponse

router = APIRouter()


def _date_bounds_for_scope(scope_type: str, scope_period: str) -> tuple[str, str]:

    if scope_type == "MONTH":
        year_str, month_str = scope_period.split("-")
        year, month = int(year_str), int(month_str)
        last_day = calendar.monthrange(year, month)[1]
        return f"{scope_period}-01T00:00:00Z", f"{scope_period}-{last_day:02d}T23:59:59Z"
    elif scope_type == "RANGE":
        from_date, to_date = scope_period.split("_")
        return f"{from_date}T00:00:00Z", f"{to_date}T23:59:59Z"
    raise ValueError(f"Unknown scope_type: {scope_type!r}")


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    scopeType: str = Query(..., description="MONTH or RANGE"),
    scopePeriod: str = Query(..., description="e.g. '2026-01' for MONTH, or '2026-01-01_2026-01-31' for RANGE"),
    segment: str = Query("ALL", description="ALL, PEAK or OFFPEAK"),
    conn=Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM metrics_summary WHERE scope_type = ? AND scope_period = ? AND segment = ?",
        (scopeType, scopePeriod, segment),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No precomputed metrics for scopeType={scopeType!r}, scopePeriod={scopePeriod!r}, "
                f"segment={segment!r}. Metrics are precomputed at ingest time, not calculated live -- "
                "run the ingestion pipeline for this scope first."
            ),
        )

    try:
        start_from, start_to = _date_bounds_for_scope(scopeType, scopePeriod)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    segment_clause = "" if segment == "ALL" else "AND segment = ?"
    params: list = [start_from, start_to]
    if segment != "ALL":
        params.append(segment)
    exclusion_rows = conn.execute(
        f"SELECT exclusion_reason, COUNT(*) as cnt FROM matched_series "
        f"WHERE included = 0 AND startTime >= ? AND startTime <= ? {segment_clause} "
        f"GROUP BY exclusion_reason",
        params,
    ).fetchall()
    exclusion_breakdown = {r["exclusion_reason"]: r["cnt"] for r in exclusion_rows}

    return MetricsResponse(
        scopeType=row["scope_type"],
        scopePeriod=row["scope_period"],
        segment=row["segment"],
        mbe=row["mbe"],
        mae=row["mae"],
        rmse=row["rmse"],
        sigmaResidual=row["sigma_residual"],
        n=row["n"],
        excludedCount=row["excluded_count"],
        exclusionBreakdown=exclusion_breakdown,
    )
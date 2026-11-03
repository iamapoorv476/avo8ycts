"""Tests for the three read-only API endpoints.

Like test_run_ingestion_pipeline.py, this seeds the real file-backed DB
(api/deps.get_db always opens db.connection.get_connection(), the project's
single DB file -- no connection injection, deliberately simple for this
project's scope) and cleans it up afterward.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import DB_PATH, get_connection, init_schema  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture
def seeded_db():
    init_schema()
    conn = get_connection()

    # One clean PEAK pair (included), one OFFPEAK pair excluded for
    # NO_FORECAST_BEFORE_CUTOFF -- mirrors test_run_ingestion_pipeline's
    # fixture shape, but inserted directly into matched_series/
    # metrics_summary/decision_time_forecast so this test is independent of
    # the pipeline's own correctness (that's covered elsewhere).
    conn.execute(
        "INSERT INTO decision_time_forecast (startTime, generation, source_publishTime) "
        "VALUES ('2026-01-01T16:00:00Z', 950.0, '2025-12-31T09:00:00Z')"
    )
    conn.execute(
        "INSERT INTO matched_series "
        "(startTime, settlementPeriod, segment, forecast_mw, source_publish_time, actual_mw, included, exclusion_reason, floor_mw, advisory_text) "
        "VALUES ('2026-01-01T16:00:00Z', 33, 'PEAK', 950.0, '2025-12-31T09:00:00Z', 900.0, 1, NULL, 700.0, 'Peak: tends to over-forecast')"
    )
    conn.execute(
        "INSERT INTO matched_series "
        "(startTime, settlementPeriod, segment, forecast_mw, source_publish_time, actual_mw, included, exclusion_reason, floor_mw, advisory_text) "
        "VALUES ('2026-01-01T00:00:00Z', 1, 'OFFPEAK', NULL, NULL, 400.0, 0, 'NO_FORECAST_BEFORE_CUTOFF', NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO metrics_summary (scope_type, scope_period, segment, mbe, mae, rmse, sigma_residual, n, excluded_count) "
        "VALUES ('MONTH', '2026-01', 'ALL', 50.0, 50.0, 50.0, 0.0, 1, 1)"
    )
    conn.execute(
        "INSERT INTO metrics_summary (scope_type, scope_period, segment, mbe, mae, rmse, sigma_residual, n, excluded_count) "
        "VALUES ('MONTH', '2026-01', 'PEAK', 50.0, 50.0, 50.0, 0.0, 1, 0)"
    )
    conn.execute(
        "INSERT INTO metrics_summary (scope_type, scope_period, segment, mbe, mae, rmse, sigma_residual, n, excluded_count) "
        "VALUES ('MONTH', '2026-01', 'OFFPEAK', 0.0, 0.0, 0.0, 0.0, 0, 1)"
    )
    conn.commit()
    conn.close()

    yield

    if DB_PATH.exists():
        DB_PATH.unlink()


def test_forecast_detail_returns_both_periods_with_correct_status(seeded_db):
    resp = client.get("/api/v1/forecast-detail", params={"date": "2026-01-01"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["date"] == "2026-01-01"
    assert body["cutoffApplied"] == "2025-12-31T11:00:00Z"  # day before, 11:00 UTC

    periods = {p["settlementPeriod"]: p for p in body["periods"]}
    assert periods[33]["status"] == "OK"
    assert periods[33]["forecastMw"] == 950.0
    assert periods[33]["sourcePublishTime"] == "2025-12-31T09:00:00Z"
    assert periods[33]["actualMw"] == 900.0

    assert periods[1]["status"] == "NO_FORECAST_BEFORE_CUTOFF"
    assert periods[1]["forecastMw"] is None
    assert periods[1]["sourcePublishTime"] is None
    assert periods[1]["actualMw"] == 400.0


def test_forecast_detail_404s_outside_ingested_scope(seeded_db):
    resp = client.get("/api/v1/forecast-detail", params={"date": "2026-06-01"})
    assert resp.status_code == 404


def test_metrics_returns_precomputed_row_plus_scoped_exclusion_breakdown(seeded_db):
    resp = client.get(
        "/api/v1/metrics",
        params={"scopeType": "MONTH", "scopePeriod": "2026-01", "segment": "ALL"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["mbe"] == 50.0
    assert body["n"] == 1
    assert body["excludedCount"] == 1
    assert body["exclusionBreakdown"] == {"NO_FORECAST_BEFORE_CUTOFF": 1}


def test_metrics_404s_for_unknown_scope(seeded_db):
    resp = client.get(
        "/api/v1/metrics",
        params={"scopeType": "MONTH", "scopePeriod": "2026-02", "segment": "ALL"},
    )
    assert resp.status_code == 404


def test_risk_floor_only_returns_periods_with_a_forecast(seeded_db):
    resp = client.get("/api/v1/risk-floor", params={"date": "2026-01-01"})
    assert resp.status_code == 200
    body = resp.json()

    # Only the PEAK period has a floor; OFFPEAK (no forecast) is excluded.
    assert len(body["periods"]) == 1
    assert body["periods"][0]["settlementPeriod"] == 33
    assert body["periods"][0]["floorMw"] == 700.0


def test_risk_floor_404s_outside_ingested_scope(seeded_db):
    resp = client.get("/api/v1/risk-floor", params={"date": "2026-06-01"})
    assert resp.status_code == 404
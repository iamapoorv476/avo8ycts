"""Tests for the three read-only API endpoints.

Like test_run_ingestion_pipeline.py, this seeds a DB via db.connection
(api/deps.get_db always opens db.connection.get_connection() -- no
connection injection, deliberately simple for this project's scope). The
seeded_db fixture below redirects db.connection.DB_PATH to a pytest
tmp_path file before seeding, so this suite never touches or deletes the
real backend/db/wind_forecast.db, and there's no manual file cleanup --
tmp_path is pytest's own disposable per-test directory.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db.connection as db_connection  
from db.connection import get_connection, init_schema  
from api.main import app  

client = TestClient(app)


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_connection, "DB_PATH", tmp_path / "test.db")
    init_schema()
    conn = get_connection()

    conn.execute(
        "INSERT INTO decision_time_forecast (startTime, generation, source_publish_time) "
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


def test_forecast_detail_returns_both_periods_with_correct_status(seeded_db):
    resp = client.get("/api/v1/forecast-detail", params={"date": "2026-01-01"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["date"] == "2026-01-01"
    assert body["cutoffApplied"] == "2025-12-31T11:00:00Z"  

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


def test_metrics_computes_and_caches_an_unseen_range_scope(seeded_db):
    """AC 2.2 requires metrics for 'a calendar month, or an explicit date
    range.' RANGE scopes aren't precomputed at ingest time (there's an
    unbounded number of possible ranges), so the first request for a given
    range computes it live from matched_series and persists it to
    metrics_summary -- see the comment in api/routes/metrics.py. This test
    only has the one seeded PEAK pair (2026-01-01, see seeded_db), so a
    range covering that date should match the same precomputed MONTH values
    (same single pair), and the write-through cache should make a second
    request read-only."""
    params = {"scopeType": "RANGE", "scopePeriod": "2026-01-01_2026-01-01", "segment": "ALL"}

    first = client.get("/api/v1/metrics", params=params)
    assert first.status_code == 200
    body = first.json()
    assert body["mbe"] == 50.0  
    assert body["n"] == 1
    assert body["excludedCount"] == 1

    second = client.get("/api/v1/metrics", params=params)
    assert second.status_code == 200
    assert second.json() == body


def test_metrics_400s_for_malformed_range_scope_period(seeded_db):
    resp = client.get(
        "/api/v1/metrics",
        params={"scopeType": "RANGE", "scopePeriod": "not-a-range", "segment": "ALL"},
    )
    assert resp.status_code == 400


def test_risk_floor_only_returns_periods_with_a_forecast(seeded_db):
    resp = client.get("/api/v1/risk-floor", params={"date": "2026-01-01"})
    assert resp.status_code == 200
    body = resp.json()

    
    assert len(body["periods"]) == 1
    assert body["periods"][0]["settlementPeriod"] == 33
    assert body["periods"][0]["floorMw"] == 700.0


def test_risk_floor_404s_outside_ingested_scope(seeded_db):
    resp = client.get("/api/v1/risk-floor", params={"date": "2026-06-01"})
    assert resp.status_code == 404
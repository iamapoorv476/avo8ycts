"""Integration test for run_ingestion_pipeline (steps 2-5; step 1 skipped).

Unlike the other test modules, this one can't inject an in-memory
connection — run_ingestion_pipeline uses db.connection.get_connection()
directly, which always points at whatever db.connection.DB_PATH currently
is (deliberately simple for this project's scope: one pipeline, one
database, no need for dependency injection of the connection — YAGNI). Both
get_connection() and init_schema() look up DB_PATH as a module-global at
call time, so this fixture redirects db.connection.DB_PATH to a pytest
tmp_path file before calling either one -- the real backend/db/wind_forecast.db
is never touched, and there's nothing to clean up afterward since tmp_path
is its own disposable, pytest-managed directory.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db.connection as db_connection  
from db.connection import get_connection, init_schema  
from ingestion.run_ingestion_pipeline import run_ingestion_pipeline  

@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_connection, "DB_PATH", tmp_path / "test.db")
    init_schema()
    conn = get_connection()

    conn.execute(
        "INSERT INTO fuelhh_actuals (startTime, settlementDate, settlementPeriod, generation) "
        "VALUES ('2026-01-01T16:00:00Z', '2026-01-01', 33, 900.0)"
    )
    conn.execute(
        "INSERT INTO fuelhh_actuals (startTime, settlementDate, settlementPeriod, generation) "
        "VALUES ('2026-01-01T00:00:00Z', '2026-01-01', 1, 400.0)"
    )
    
    conn.execute(
        "INSERT INTO windfor_forecasts (startTime, publishTime, generation) "
        "VALUES ('2026-01-01T16:00:00Z', '2025-12-31T09:00:00Z', 950.0)"
    )
    
    conn.commit()
    conn.close()

    yield


def test_pipeline_produces_consistent_results_end_to_end(seeded_db):
    result = run_ingestion_pipeline(
        run_raw_ingestion=False,
        scope_type="MONTH",
        scope_period="2026-01",
        start_time_from="2026-01-01T00:00:00Z",
        start_time_to="2026-01-31T23:59:59Z",
    )

    assert result["decision_time_forecast_rows"] == 1  
    assert result["matched_series_rows"] == 2  
    assert result["metrics_summary_rows"] == 3  
    assert result["risk_floor_rows_backfilled"] == 1  

    conn = get_connection()
    try:
        peak_row = conn.execute(
            "SELECT * FROM matched_series WHERE startTime = '2026-01-01T16:00:00Z'"
        ).fetchone()
        offpeak_row = conn.execute(
            "SELECT * FROM matched_series WHERE startTime = '2026-01-01T00:00:00Z'"
        ).fetchone()

        assert peak_row["included"] == 1
        assert peak_row["segment"] == "PEAK"
        assert peak_row["error_mw"] == 50.0  
        assert peak_row["floor_mw"] is not None  
        assert offpeak_row["included"] == 0
        assert offpeak_row["exclusion_reason"] == "NO_FORECAST_BEFORE_CUTOFF"
        assert offpeak_row["floor_mw"] is None  
        all_metrics = conn.execute(
            "SELECT * FROM metrics_summary WHERE scope_period = '2026-01' AND segment = 'ALL'"
        ).fetchone()
        assert all_metrics["n"] == 1  
        assert all_metrics["excluded_count"] == 1
    finally:
        conn.close()
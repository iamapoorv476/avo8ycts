"""Integration test for run_ingestion_pipeline (steps 2-5; step 1 skipped).

Unlike the other test modules, this one can't inject an in-memory
connection — run_ingestion_pipeline uses db.connection.get_connection()
directly, which always points at the project's single DB file (deliberately
simple for this project's scope: one pipeline, one database, no need for
dependency injection of the connection — YAGNI). So this test seeds that
real file-backed DB with fixture raw data, runs the pipeline with
run_raw_ingestion=False, and cleans the file up afterward.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import DB_PATH, get_connection, init_schema  # noqa: E402
from ingestion.run_ingestion_pipeline import run_ingestion_pipeline  # noqa: E402


@pytest.fixture
def seeded_db():
    init_schema()
    conn = get_connection()

    # Two settlement periods on 2026-01-01: one fully clean pair (peak),
    # one with no forecast available before cutoff (off-peak) -> excluded.
    conn.execute(
        "INSERT INTO fuelhh_actuals (startTime, settlementDate, settlementPeriod, generation) "
        "VALUES ('2026-01-01T16:00:00Z', '2026-01-01', 33, 900.0)"
    )
    conn.execute(
        "INSERT INTO fuelhh_actuals (startTime, settlementDate, settlementPeriod, generation) "
        "VALUES ('2026-01-01T00:00:00Z', '2026-01-01', 1, 400.0)"
    )
    # Forecast vintage for the peak period, published before the
    # 2025-12-31T11:00:00Z cutoff for 2026-01-01 deliveries.
    conn.execute(
        "INSERT INTO windfor_forecasts (startTime, publishTime, generation) "
        "VALUES ('2026-01-01T16:00:00Z', '2025-12-31T09:00:00Z', 950.0)"
    )
    # Deliberately no forecast row for 2026-01-01T00:00:00Z -> NO_FORECAST_BEFORE_CUTOFF.
    conn.commit()
    conn.close()

    yield

    if DB_PATH.exists():
        DB_PATH.unlink()


def test_pipeline_produces_consistent_results_end_to_end(seeded_db):
    result = run_ingestion_pipeline(
        run_raw_ingestion=False,
        scope_type="MONTH",
        scope_period="2026-01",
        start_time_from="2026-01-01T00:00:00Z",
        start_time_to="2026-01-31T23:59:59Z",
    )

    assert result["decision_time_forecast_rows"] == 1  # only the peak startTime has a vintage
    assert result["matched_series_rows"] == 2  # both actual rows get a matched_series row
    assert result["metrics_summary_rows"] == 3  # ALL, PEAK, OFFPEAK
    assert result["risk_floor_rows_backfilled"] == 1  # only the row with a forecast

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
        assert peak_row["error_mw"] == 50.0  # 950 - 900
        assert peak_row["floor_mw"] is not None  # backfilled by RiskFloorCalculator

        assert offpeak_row["included"] == 0
        assert offpeak_row["exclusion_reason"] == "NO_FORECAST_BEFORE_CUTOFF"
        assert offpeak_row["floor_mw"] is None  # no forecast, so no floor either

        all_metrics = conn.execute(
            "SELECT * FROM metrics_summary WHERE scope_period = '2026-01' AND segment = 'ALL'"
        ).fetchone()
        assert all_metrics["n"] == 1  # only the included peak pair
        assert all_metrics["excluded_count"] == 1
    finally:
        conn.close()
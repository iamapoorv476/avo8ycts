"""Tests for RiskFloorCalculator (AC 2.4, AC 2.5)."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import SCHEMA_PATH  # noqa: E402
from ingestion.risk_floor_calculator import RiskFloorCalculator, Z_90  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        c.executescript(f.read())
    yield c
    c.close()


def insert_metrics(conn, scope_type, scope_period, segment, mbe, sigma_residual):
    conn.execute(
        """
        INSERT INTO metrics_summary
            (scope_type, scope_period, segment, mbe, mae, rmse, sigma_residual, n, excluded_count)
        VALUES (?, ?, ?, ?, 0, 0, ?, 10, 0)
        """,
        (scope_type, scope_period, segment, mbe, sigma_residual),
    )
    conn.commit()


def insert_matched(conn, start_time, segment, forecast_mw, included=1):
    conn.execute(
        """
        INSERT INTO matched_series (startTime, settlementPeriod, segment, forecast_mw, actual_mw, included)
        VALUES (?, 1, ?, ?, ?, ?)
        """,
        (start_time, segment, forecast_mw, forecast_mw, included),
    )
    conn.commit()


def test_floor_formula_known_value(conn):
    # forecast=1000, MBE=50 (over-forecasts by 50), sigma=20
    # floor = max(0, (1000 - 50) - 1.28*20) = 950 - 25.6 = 924.4
    insert_metrics(conn, "MONTH", "2026-01", "PEAK", mbe=50.0, sigma_residual=20.0)
    insert_metrics(conn, "MONTH", "2026-01", "OFFPEAK", mbe=0.0, sigma_residual=0.0)
    insert_matched(conn, "2026-01-01T16:00:00Z", "PEAK", forecast_mw=1000.0)

    calc = RiskFloorCalculator(conn)
    n = calc.calculate("MONTH", "2026-01")

    assert n == 1
    row = conn.execute("SELECT floor_mw FROM matched_series").fetchone()
    assert abs(row["floor_mw"] - 924.4) < 1e-6


def test_floor_never_negative(conn):
    # forecast=10, MBE=0, sigma=100 -> raw floor would be deeply negative
    insert_metrics(conn, "MONTH", "2026-01", "PEAK", mbe=0.0, sigma_residual=100.0)
    insert_metrics(conn, "MONTH", "2026-01", "OFFPEAK", mbe=0.0, sigma_residual=0.0)
    insert_matched(conn, "2026-01-01T16:00:00Z", "PEAK", forecast_mw=10.0)

    calc = RiskFloorCalculator(conn)
    calc.calculate("MONTH", "2026-01")

    row = conn.execute("SELECT floor_mw FROM matched_series").fetchone()
    assert row["floor_mw"] == 0.0


def test_different_segments_use_their_own_stats(conn):
    insert_metrics(conn, "MONTH", "2026-01", "PEAK", mbe=100.0, sigma_residual=10.0)
    insert_metrics(conn, "MONTH", "2026-01", "OFFPEAK", mbe=0.0, sigma_residual=0.0)
    insert_matched(conn, "2026-01-01T16:00:00Z", "PEAK", forecast_mw=500.0)
    insert_matched(conn, "2026-01-01T00:00:00Z", "OFFPEAK", forecast_mw=500.0)

    calc = RiskFloorCalculator(conn)
    calc.calculate("MONTH", "2026-01")

    rows = {r["segment"]: r["floor_mw"] for r in conn.execute("SELECT segment, floor_mw FROM matched_series")}
    # PEAK: (500-100) - 1.28*10 = 400 - 12.8 = 387.2
    # OFFPEAK: (500-0) - 1.28*0 = 500
    assert abs(rows["PEAK"] - 387.2) < 1e-6
    assert rows["OFFPEAK"] == 500.0


def test_row_without_forecast_is_left_untouched(conn):
    insert_metrics(conn, "MONTH", "2026-01", "PEAK", mbe=0.0, sigma_residual=0.0)
    insert_metrics(conn, "MONTH", "2026-01", "OFFPEAK", mbe=0.0, sigma_residual=0.0)
    conn.execute(
        """
        INSERT INTO matched_series (startTime, settlementPeriod, segment, forecast_mw, actual_mw, included, exclusion_reason)
        VALUES ('2026-01-01T00:00:00Z', 1, 'OFFPEAK', NULL, NULL, 0, 'NO_FORECAST_BEFORE_CUTOFF')
        """
    )
    conn.commit()

    calc = RiskFloorCalculator(conn)
    n = calc.calculate("MONTH", "2026-01")

    assert n == 0
    row = conn.execute("SELECT floor_mw, advisory_text FROM matched_series").fetchone()
    assert row["floor_mw"] is None
    assert row["advisory_text"] is None


def test_missing_metrics_summary_raises_not_silently_defaults(conn):
    insert_matched(conn, "2026-01-01T16:00:00Z", "PEAK", forecast_mw=500.0)
    calc = RiskFloorCalculator(conn)

    with pytest.raises(ValueError, match="No metrics_summary row"):
        calc.calculate("MONTH", "2026-01")  # metrics_summary never populated
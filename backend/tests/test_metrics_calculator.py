"""Tests for MetricsCalculator (AC 2.2, AC 2.3)."""

import math
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import SCHEMA_PATH  # noqa: E402
from ingestion.metrics_calculator import MetricsCalculator  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        c.executescript(f.read())
    yield c
    c.close()


def insert_matched(conn, start_time, segment, forecast_mw, actual_mw, included, exclusion_reason=None):
    conn.execute(
        """
        INSERT INTO matched_series
            (startTime, settlementPeriod, segment, forecast_mw, actual_mw, included, exclusion_reason)
        VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (start_time, segment, forecast_mw, actual_mw, included, exclusion_reason),
    )
    conn.commit()


def test_mbe_mae_rmse_known_values(conn):
    # Errors (forecast - actual): +10, -10, +20 -> MBE = 20/3, MAE = 40/3, RMSE = sqrt((100+100+400)/3)
    insert_matched(conn, "2026-01-01T00:00:00Z", "OFFPEAK", 110.0, 100.0, 1)  # error +10
    insert_matched(conn, "2026-01-01T00:30:00Z", "OFFPEAK", 90.0, 100.0, 1)  # error -10
    insert_matched(conn, "2026-01-01T01:00:00Z", "OFFPEAK", 120.0, 100.0, 1)  # error +20

    calc = MetricsCalculator(conn)
    calc.calculate("MONTH", "2026-01", "2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")

    row = conn.execute(
        "SELECT * FROM metrics_summary WHERE segment = 'ALL'"
    ).fetchone()
    assert row["n"] == 3
    assert math.isclose(row["mbe"], 20 / 3, rel_tol=1e-9)
    assert math.isclose(row["mae"], 40 / 3, rel_tol=1e-9)
    assert math.isclose(row["rmse"], math.sqrt((100 + 100 + 400) / 3), rel_tol=1e-9)


def test_segments_are_isolated(conn):
    insert_matched(conn, "2026-01-01T16:00:00Z", "PEAK", 110.0, 100.0, 1)  # error +10
    insert_matched(conn, "2026-01-01T00:00:00Z", "OFFPEAK", 150.0, 100.0, 1)  # error +50

    calc = MetricsCalculator(conn)
    calc.calculate("MONTH", "2026-01", "2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")

    peak = conn.execute("SELECT * FROM metrics_summary WHERE segment = 'PEAK'").fetchone()
    offpeak = conn.execute("SELECT * FROM metrics_summary WHERE segment = 'OFFPEAK'").fetchone()
    all_seg = conn.execute("SELECT * FROM metrics_summary WHERE segment = 'ALL'").fetchone()

    assert peak["n"] == 1 and peak["mbe"] == 10.0
    assert offpeak["n"] == 1 and offpeak["mbe"] == 50.0
    assert all_seg["n"] == 2  # combines both


def test_excluded_rows_counted_but_not_in_metrics(conn):
    insert_matched(conn, "2026-01-01T00:00:00Z", "OFFPEAK", 100.0, 100.0, 1)
    insert_matched(conn, "2026-01-01T00:30:00Z", "OFFPEAK", None, None, 0, "NO_FORECAST_BEFORE_CUTOFF")

    calc = MetricsCalculator(conn)
    calc.calculate("MONTH", "2026-01", "2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")

    row = conn.execute("SELECT * FROM metrics_summary WHERE segment = 'ALL'").fetchone()
    assert row["n"] == 1  # only the included row
    assert row["excluded_count"] == 1  # but the exclusion is still visible, not hidden


def test_sigma_residual_zero_when_fewer_than_two_points(conn):
    insert_matched(conn, "2026-01-01T00:00:00Z", "OFFPEAK", 110.0, 100.0, 1)

    calc = MetricsCalculator(conn)
    calc.calculate("MONTH", "2026-01", "2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")

    row = conn.execute("SELECT * FROM metrics_summary WHERE segment = 'ALL'").fetchone()
    assert row["n"] == 1
    assert row["sigma_residual"] == 0.0  # undefined with n=1, not a crash


def test_range_scope_filters_by_date_bound(conn):
    insert_matched(conn, "2026-01-01T00:00:00Z", "OFFPEAK", 110.0, 100.0, 1)  # in range
    insert_matched(conn, "2026-01-15T00:00:00Z", "OFFPEAK", 200.0, 100.0, 1)  # out of range

    calc = MetricsCalculator(conn)
    calc.calculate("RANGE", "2026-01-01_2026-01-02", "2026-01-01T00:00:00Z", "2026-01-02T23:59:59Z")

    row = conn.execute("SELECT * FROM metrics_summary WHERE segment = 'ALL'").fetchone()
    assert row["n"] == 1
    assert row["mbe"] == 10.0
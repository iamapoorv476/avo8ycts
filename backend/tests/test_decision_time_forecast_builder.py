"""Tests for DecisionTimeForecastBuilder (AC 1.1, AC 1.4).

Covers the two things most likely to be subtly wrong: the cutoff boundary
(off-by-one on "<=") and the step-hold mapping (off-by-one on which half-hour
maps to which hour).
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import SCHEMA_PATH  # noqa: E402
from ingestion.decision_time_forecast_builder import DecisionTimeForecastBuilder  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        c.executescript(f.read())
    yield c
    c.close()


def insert_windfor(conn, rows):
    conn.executemany(
        "INSERT INTO windfor_forecasts (startTime, publishTime, generation) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def test_picks_latest_vintage_at_or_before_cutoff(conn):
    # Target delivery startTime is 2026-01-15T12:00:00Z -> cutoff is
    # 2026-01-14T11:00:00Z (day-ahead, 11:00 UTC day before).
    insert_windfor(
        conn,
        [
            ("2026-01-15T12:00:00Z", "2026-01-13T22:30:00Z", 1000.0),  # before cutoff, older
            ("2026-01-15T12:00:00Z", "2026-01-14T11:00:00Z", 1100.0),  # exactly at cutoff
            ("2026-01-15T12:00:00Z", "2026-01-14T15:30:00Z", 1200.0),  # after cutoff, excluded
        ],
    )
    builder = DecisionTimeForecastBuilder(conn, cutoff_hour_utc=11)
    n = builder.build()

    assert n == 1
    row = conn.execute("SELECT * FROM decision_time_forecast").fetchone()
    assert row["generation"] == 1100.0
    assert row["source_publish_time"] == "2026-01-14T11:00:00Z"  # boundary is inclusive


def test_startTime_with_no_vintage_before_cutoff_is_excluded(conn):
    insert_windfor(
        conn,
        [("2026-01-15T12:00:00Z", "2026-01-14T15:30:00Z", 1200.0)],  # only a too-late vintage
    )
    builder = DecisionTimeForecastBuilder(conn, cutoff_hour_utc=11)
    n = builder.build()

    assert n == 0
    assert conn.execute("SELECT COUNT(*) FROM decision_time_forecast").fetchone()[0] == 0


def test_step_hold_applies_hourly_value_to_both_half_hours(conn):
    insert_windfor(conn, [("2026-01-15T00:00:00Z", "2026-01-14T09:00:00Z", 500.0)])
    builder = DecisionTimeForecastBuilder(conn, cutoff_hour_utc=11)
    builder.build()

    result = builder.step_hold_half_hourly(
        ["2026-01-15T00:00:00Z", "2026-01-15T00:30:00Z", "2026-01-15T01:00:00Z"]
    )

    assert result["2026-01-15T00:00:00Z"]["generation"] == 500.0
    assert result["2026-01-15T00:30:00Z"]["generation"] == 500.0  # forward-filled, not interpolated
    assert "2026-01-15T01:00:00Z" not in result  # no hourly forecast covers this hour


def test_step_hold_omits_half_hours_with_no_covering_forecast(conn):
    builder = DecisionTimeForecastBuilder(conn, cutoff_hour_utc=11)
    builder.build()  # no windfor rows at all

    result = builder.step_hold_half_hourly(["2026-01-15T00:00:00Z", "2026-01-15T00:30:00Z"])

    assert result == {}  
"""Tests for SeriesMatcher (AC 2.1, AC 1.5, AC 2.5)."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import SCHEMA_PATH  # noqa: E402
from ingestion.series_matcher import SeriesMatcher  # noqa: E402


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        c.executescript(f.read())
    yield c
    c.close()


def insert_actual(conn, start_time, settlement_period, generation):
    conn.execute(
        "INSERT INTO fuelhh_actuals (startTime, settlementDate, settlementPeriod, generation) VALUES (?, ?, ?, ?)",
        (start_time, start_time[:10], settlement_period, generation),
    )
    conn.commit()


def test_included_pair_has_error_mw_and_correct_segment(conn):
    insert_actual(conn, "2026-01-15T16:00:00Z", 33, 950.0)  # SP 33 -> PEAK
    matcher = SeriesMatcher(conn)
    n = matcher.match({"2026-01-15T16:00:00Z": {"generation": 1000.0, "source_publish_time": "x"}})

    assert n == 1
    row = conn.execute("SELECT * FROM matched_series").fetchone()
    assert row["included"] == 1
    assert row["exclusion_reason"] is None
    assert row["segment"] == "PEAK"
    assert row["forecast_mw"] == 1000.0
    assert row["actual_mw"] == 950.0
    assert row["error_mw"] == 50.0  # forecast - actual = 1000 - 950


def test_offpeak_segment_outside_peak_window(conn):
    insert_actual(conn, "2026-01-15T00:00:00Z", 1, 500.0)  # SP 1 -> OFFPEAK
    matcher = SeriesMatcher(conn)
    matcher.match({"2026-01-15T00:00:00Z": {"generation": 520.0, "source_publish_time": "x"}})

    row = conn.execute("SELECT segment FROM matched_series").fetchone()
    assert row["segment"] == "OFFPEAK"


def test_missing_forecast_is_excluded_not_dropped(conn):
    insert_actual(conn, "2026-01-15T00:00:00Z", 1, 500.0)
    matcher = SeriesMatcher(conn)
    n = matcher.match({})  # no forecast available for this startTime

    assert n == 1  # row still written, not dropped
    row = conn.execute("SELECT * FROM matched_series").fetchone()
    assert row["included"] == 0
    assert row["exclusion_reason"] == "NO_FORECAST_BEFORE_CUTOFF"
    assert row["forecast_mw"] is None


def test_negative_actual_is_invalid_and_excluded(conn):
    insert_actual(conn, "2026-01-15T00:00:00Z", 1, -5.0)  # wind generation can't be negative
    matcher = SeriesMatcher(conn)
    matcher.match({"2026-01-15T00:00:00Z": {"generation": 520.0, "source_publish_time": "x"}})

    row = conn.execute("SELECT * FROM matched_series").fetchone()
    assert row["included"] == 0
    assert row["exclusion_reason"] == "MISSING_OR_INVALID_ACTUAL"
    assert row["actual_mw"] is None  # invalid value not carried through


def test_peak_window_boundaries_inclusive(conn):
    insert_actual(conn, "2026-01-15T16:00:00Z", 33, 100.0)
    insert_actual(conn, "2026-01-15T18:30:00Z", 38, 100.0)
    insert_actual(conn, "2026-01-15T15:30:00Z", 32, 100.0)  # just before peak
    insert_actual(conn, "2026-01-15T19:00:00Z", 39, 100.0)  # just after peak
    matcher = SeriesMatcher(conn)
    matcher.match(
        {ts: {"generation": 100.0, "source_publish_time": "x"} for ts in [
            "2026-01-15T16:00:00Z", "2026-01-15T18:30:00Z", "2026-01-15T15:30:00Z", "2026-01-15T19:00:00Z",
        ]}
    )

    rows = {r["settlementPeriod"]: r["segment"] for r in conn.execute("SELECT * FROM matched_series")}
    assert rows[33] == "PEAK"
    assert rows[38] == "PEAK"
    assert rows[32] == "OFFPEAK"
    assert rows[39] == "OFFPEAK"
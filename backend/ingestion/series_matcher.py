"""SeriesMatcher — AC 2.1, AC 1.5, AC 2.5.

Single responsibility: join FUELHH actuals against the step-held
decision-time forecast, assign a PEAK/OFF-PEAK segment, and flag any
exclusion with an explicit reason. Writes matched_series.

Join + exclusion flagging are deliberately combined in one class (not split
further): both operations happen in the same single pass over the actuals,
and splitting them would mean passing the same per-row decision between two
objects for no isolation benefit — not justified for this scope (YAGNI).

Base population: this class iterates over fuelhh_actuals rows (not a
synthetic full 1,488-slot calendar grid), on the assumption that raw
ingestion is complete for January 2026 — i.e. that FUELHH genuinely returns
a row for every settlement period in scope. If that assumption is ever
wrong (an ingestion gap), an entire settlement period would be missing from
matched_series with no exclusion row logged for it — different from, and
not caught by, the MISSING_OR_INVALID_ACTUAL case below (which requires the
row to exist with a null/invalid value). This is a known limitation, not a
silent-drop violation of AC 2.1: AC 2.1's "explicitly logged, not silently
dropped" requirement is about pairs this class decides to exclude, not about
upstream ingestion completeness, which is a separate concern.
"""

from __future__ import annotations

import sqlite3

PEAK_PERIOD_START = 33
PEAK_PERIOD_END = 38  


def _segment_for(settlement_period: int) -> str:
    return "PEAK" if PEAK_PERIOD_START <= settlement_period <= PEAK_PERIOD_END else "OFFPEAK"


class SeriesMatcher:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def match(self, half_hourly_forecasts: dict[str, dict]) -> int:
        """Join every FUELHH actual against its half-hourly decision-time forecast.

        `half_hourly_forecasts` is the dict produced by
        DecisionTimeForecastBuilder.step_hold_half_hourly(), keyed by startTime.
        A startTime absent from it means AC 1.5's NO_FORECAST_BEFORE_CUTOFF.

        An actual that is NULL or negative (wind generation cannot be negative)
        is MISSING_OR_INVALID_ACTUAL, regardless of whether a forecast exists.

        Returns the number of rows written to matched_series.
        """
        actual_rows = self.conn.execute(
            "SELECT startTime, settlementPeriod, generation FROM fuelhh_actuals"
        ).fetchall()

        records = []
        for row in actual_rows:
            start_time = row["startTime"]
            settlement_period = row["settlementPeriod"]
            actual = row["generation"]
            segment = _segment_for(settlement_period)

            forecast_entry = half_hourly_forecasts.get(start_time)
            actual_is_valid = actual is not None and actual >= 0

            if forecast_entry is None:
                included = False
                exclusion_reason = "NO_FORECAST_BEFORE_CUTOFF"
                forecast_mw = None
                source_publish_time = None
                actual_mw = actual if actual_is_valid else None
            elif not actual_is_valid:
                included = False
                exclusion_reason = "MISSING_OR_INVALID_ACTUAL"
                forecast_mw = forecast_entry["generation"]
                source_publish_time = forecast_entry["source_publish_time"]
                actual_mw = None
            else:
                included = True
                exclusion_reason = None
                forecast_mw = forecast_entry["generation"]
                source_publish_time = forecast_entry["source_publish_time"]
                actual_mw = actual

            records.append(
                (
                    start_time,
                    settlement_period,
                    segment,
                    forecast_mw,
                    source_publish_time,
                    actual_mw,
                    int(included),
                    exclusion_reason,
                )
            )

        self.conn.execute("DELETE FROM matched_series")
        self.conn.executemany(
            "INSERT INTO matched_series "
            "(startTime, settlementPeriod, segment, forecast_mw, source_publish_time, actual_mw, included, exclusion_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )
        self.conn.commit()
        return len(records)
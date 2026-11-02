"""DecisionTimeForecastBuilder — AC 1.1 and AC 1.4.

Single responsibility: given the raw WINDFOR vintages, determine what a
trader actually had in front of them at the day-ahead decision cutoff, at
both the native hourly resolution (persisted to `decision_time_forecast`)
and step-held onto a half-hourly grid (returned in-memory, since no table in
the schema stores a separate half-hourly forecast series — the only
persisted destination for that is `matched_series.forecast_mw`, populated by
SeriesMatcher using this class's output).
"""

from __future__ import annotations

import sqlite3


def _floor_to_hour(iso_timestamp: str) -> str:
    """'2026-01-15T00:30:00Z' -> '2026-01-15T00:00:00Z'.

    Assumes the consistent Elexon UTC ISO-8601 format confirmed against real
    sample data during design (always 'Z'-suffixed, seconds included).
    """
    date_part, time_part = iso_timestamp.split("T")
    hour = time_part[:2]
    return f"{date_part}T{hour}:00:00Z"


class DecisionTimeForecastBuilder:
    """Selects the latest WINDFOR vintage available before the day-ahead cutoff
    (AC 1.1), and step-holds it onto a half-hourly grid (AC 1.4)."""

    def __init__(self, conn: sqlite3.Connection, cutoff_hour_utc: int = 11):
        self.conn = conn
        self.cutoff_hour_utc = cutoff_hour_utc

    def build(self) -> int:
        
        cutoff_expr = f"date(startTime, '-1 day') || 'T{self.cutoff_hour_utc:02d}:00:00Z'"
        self.conn.execute("DELETE FROM decision_time_forecast")
        cur = self.conn.execute(
            f"""
            INSERT INTO decision_time_forecast (startTime, generation, source_publishTime)
            SELECT startTime, generation, publishTime
            FROM (
                SELECT
                    startTime,
                    generation,
                    publishTime,
                    ROW_NUMBER() OVER (
                        PARTITION BY startTime ORDER BY publishTime DESC
                    ) AS rn
                FROM windfor_forecasts
                WHERE publishTime <= {cutoff_expr}
            )
            WHERE rn = 1
            """
        )
        self.conn.commit()
        return cur.rowcount

    def step_hold_half_hourly(self, half_hourly_timestamps: list[str]) -> dict[str, dict]:
        
        hourly_rows = {
            row["startTime"]: {
                "generation": row["generation"],
                "source_publishTime": row["source_publishTime"],
            }
            for row in self.conn.execute(
                "SELECT startTime, generation, source_publishTime FROM decision_time_forecast"
            )
        }

        result: dict[str, dict] = {}
        for ts in half_hourly_timestamps:
            hour_ts = _floor_to_hour(ts)
            if hour_ts in hourly_rows:
                result[ts] = hourly_rows[hour_ts]
        return result
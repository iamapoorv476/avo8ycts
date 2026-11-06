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
    
    date_part, time_part = iso_timestamp.split("T")
    hour = time_part[:2]
    return f"{date_part}T{hour}:00:00Z"


class DecisionTimeForecastBuilder:
    

    def __init__(self, conn: sqlite3.Connection, cutoff_hour_utc: int = 11):
        self.conn = conn
        self.cutoff_hour_utc = cutoff_hour_utc

    def build(self) -> int:
        """AC 1.1: for every WINDFOR startTime, pick the row with the latest
        publishTime that is still <= the day-ahead cutoff (11:00 UTC on the day
        before delivery), and persist it to decision_time_forecast.

        If no such vintage exists for a given startTime, that startTime simply
        gets no row here — callers (step_hold_half_hourly, and ultimately
        SeriesMatcher) must treat a missing entry as AC 1.5's
        NO_FORECAST_BEFORE_CUTOFF, not as a fetch error.

        Returns the number of rows written.
        """
        cutoff_expr = f"date(startTime, '-1 day') || 'T{self.cutoff_hour_utc:02d}:00:00Z'"
        self.conn.execute("DELETE FROM decision_time_forecast")
        cur = self.conn.execute(
            f"""
            INSERT INTO decision_time_forecast (startTime, generation, source_publish_time)
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
        """AC 1.4: forward-fill each hourly decision-time forecast onto the two
        half-hour settlement periods it covers.

        Must be called after build(). Returns a dict keyed by half-hourly
        startTime; a timestamp with no covering hourly forecast is simply
        absent from the result — the caller decides what that means (AC 1.5),
        this method does not silently invent a value or drop the request.
        """
        hourly_rows = {
            row["startTime"]: {
                "generation": row["generation"],
                "source_publish_time": row["source_publish_time"],
            }
            for row in self.conn.execute(
                "SELECT startTime, generation, source_publish_time FROM decision_time_forecast"
            )
        }

        result: dict[str, dict] = {}
        for ts in half_hourly_timestamps:
            hour_ts = _floor_to_hour(ts)
            if hour_ts in hourly_rows:
                result[ts] = hourly_rows[hour_ts]
        return result
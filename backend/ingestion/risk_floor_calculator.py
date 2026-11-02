"""RiskFloorCalculator — AC 2.4, AC 2.5.

Single responsibility: compute the bias-corrected, conservative generation
floor for every settlement period that has a forecast, and backfill
matched_series.floor_mw / .advisory_text.

Runs after MetricsCalculator, because the floor formula needs each
segment's own MBE and residual standard deviation:

    Floor_t = max(0, (forecast_t - MBE_group) - Z_90 * sigma_residual_group)

"""

from __future__ import annotations

import sqlite3


Z_90 = 1.28

SEGMENT_LABELS = {
    "PEAK": "Peak (16:00-19:00 GMT)",
    "OFFPEAK": "Off-peak",
}


class RiskFloorCalculator:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def calculate(self, scope_type: str, scope_period: str) -> int:

        segment_stats = {
            segment: self._load_segment_stats(scope_type, scope_period, segment)
            for segment in ("PEAK", "OFFPEAK")
        }

        rows = self.conn.execute(
            "SELECT startTime, segment, forecast_mw FROM matched_series WHERE forecast_mw IS NOT NULL"
        ).fetchall()

        updates = []
        for row in rows:
            mbe, sigma_residual = segment_stats[row["segment"]]
            floor_mw = max(0.0, (row["forecast_mw"] - mbe) - Z_90 * sigma_residual)
            advisory_text = self._advisory_text(row["segment"], mbe, sigma_residual)
            updates.append((floor_mw, advisory_text, row["startTime"]))

        self.conn.executemany(
            "UPDATE matched_series SET floor_mw = ?, advisory_text = ? WHERE startTime = ?",
            updates,
        )
        self.conn.commit()
        return len(updates)

    def _load_segment_stats(self, scope_type: str, scope_period: str, segment: str) -> tuple[float, float]:
        row = self.conn.execute(
            "SELECT mbe, sigma_residual FROM metrics_summary "
            "WHERE scope_type = ? AND scope_period = ? AND segment = ?",
            (scope_type, scope_period, segment),
        ).fetchone()
        if row is None:
            
            raise ValueError(
                f"No metrics_summary row for scope_type={scope_type!r}, "
                f"scope_period={scope_period!r}, segment={segment!r}. "
                "Run MetricsCalculator.calculate() for this scope before RiskFloorCalculator."
            )
        return row["mbe"], row["sigma_residual"]

    @staticmethod
    def _advisory_text(segment: str, mbe: float, sigma_residual: float) -> str:
        if mbe > 0:
            bias_description = f"tends to over-forecast (MBE {mbe:+.1f} MW)"
        elif mbe < 0:
            bias_description = f"tends to under-forecast (MBE {mbe:+.1f} MW)"
        else:
            bias_description = "shows no systematic bias (MBE 0.0 MW)"

        return (
            f"{SEGMENT_LABELS[segment]}: forecast {bias_description}, with a residual "
            f"spread of {sigma_residual:.1f} MW. This floor removes the known segment "
            f"bias and applies a one-sided ~90% downside buffer ({Z_90} \u03c3) — a "
            f"conservative planning number, not a point forecast."
        )
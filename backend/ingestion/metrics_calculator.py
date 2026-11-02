"""MetricsCalculator — AC 2.2, AC 2.3.

Single responsibility: aggregate matched_series into MBE/MAE/RMSE and the
residual standard deviation, per segment (ALL / PEAK / OFF-PEAK), for a
given scope, and persist to metrics_summary.

The scope's date bounds are the caller's responsibility (turning "January
2026" or an explicit date range into concrete ISO-8601 timestamp bounds) —
this class only knows how to aggregate over a bound it's given, keeping it
reusable for both a MONTH scope and an arbitrary RANGE scope without caring
which one it's computing.
"""

from __future__ import annotations

import sqlite3
import statistics


class MetricsCalculator:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def calculate(
        self,
        scope_type: str,
        scope_period: str,
        start_time_from: str,
        start_time_to: str,
    ) -> int:
        """Compute and persist metrics for ALL, PEAK and OFF-PEAK segments over
        matched_series rows with startTime in [start_time_from, start_time_to]
        (inclusive; caller supplies full ISO-8601 bounds, e.g. end-of-day for
        the "to" side so the last day isn't cut off at midnight).

        Returns the number of metrics_summary rows written (always 3).
        """
        rows_to_write = []
        for segment in ("ALL", "PEAK", "OFFPEAK"):
            errors = self._included_errors(segment, start_time_from, start_time_to)
            excluded_count = self._excluded_count(segment, start_time_from, start_time_to)

            n = len(errors)
            mbe = statistics.mean(errors) if n else 0.0
            mae = statistics.mean(abs(e) for e in errors) if n else 0.0
            rmse = statistics.mean(e * e for e in errors) ** 0.5 if n else 0.0
            # Sample std dev (ddof=1) of residuals around this segment's OWN
            # mean error — needs at least 2 points to be defined.
            sigma_residual = statistics.stdev(errors) if n > 1 else 0.0

            rows_to_write.append(
                (scope_type, scope_period, segment, mbe, mae, rmse, sigma_residual, n, excluded_count)
            )

        self.conn.executemany(
            "INSERT OR REPLACE INTO metrics_summary "
            "(scope_type, scope_period, segment, mbe, mae, rmse, sigma_residual, n, excluded_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows_to_write,
        )
        self.conn.commit()
        return len(rows_to_write)

    def _included_errors(self, segment: str, start_time_from: str, start_time_to: str) -> list[float]:
        segment_clause, params = self._segment_clause(segment, start_time_from, start_time_to)
        rows = self.conn.execute(
            f"SELECT error_mw FROM matched_series WHERE included = 1 {segment_clause}",
            params,
        ).fetchall()
        return [r["error_mw"] for r in rows]

    def _excluded_count(self, segment: str, start_time_from: str, start_time_to: str) -> int:
        segment_clause, params = self._segment_clause(segment, start_time_from, start_time_to)
        return self.conn.execute(
            f"SELECT COUNT(*) FROM matched_series WHERE included = 0 {segment_clause}",
            params,
        ).fetchone()[0]

    @staticmethod
    def _segment_clause(segment: str, start_time_from: str, start_time_to: str) -> tuple[str, list]:
        params: list = [start_time_from, start_time_to]
        clause = "AND startTime >= ? AND startTime <= ?"
        if segment != "ALL":
            clause += " AND segment = ?"
            params.append(segment)
        return clause, params
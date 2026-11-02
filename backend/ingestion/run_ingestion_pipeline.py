"""run_ingestion_pipeline — orchestrates the full ingest -> derive pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import get_connection  # noqa: E402
from ingestion import ingest_elexon  # noqa: E402
from ingestion.decision_time_forecast_builder import DecisionTimeForecastBuilder  # noqa: E402
from ingestion.metrics_calculator import MetricsCalculator  # noqa: E402
from ingestion.risk_floor_calculator import RiskFloorCalculator  # noqa: E402
from ingestion.series_matcher import SeriesMatcher  # noqa: E402

DEFAULT_CUTOFF_HOUR_UTC = 11
DEFAULT_SCOPE_TYPE = "MONTH"
DEFAULT_SCOPE_PERIOD = "2026-01"
DEFAULT_START_TIME_FROM = "2026-01-01T00:00:00Z"
DEFAULT_START_TIME_TO = "2026-01-31T23:59:59Z"


def run_ingestion_pipeline(
    run_raw_ingestion: bool = True,
    scope_type: str = DEFAULT_SCOPE_TYPE,
    scope_period: str = DEFAULT_SCOPE_PERIOD,
    start_time_from: str = DEFAULT_START_TIME_FROM,
    start_time_to: str = DEFAULT_START_TIME_TO,
    cutoff_hour_utc: int = DEFAULT_CUTOFF_HOUR_UTC,
) -> dict:
    
    if run_raw_ingestion:
        ingest_elexon.run()  

    conn = get_connection()
    try:
        builder = DecisionTimeForecastBuilder(conn, cutoff_hour_utc=cutoff_hour_utc)
        decision_time_forecast_rows = builder.build()  

        half_hourly_timestamps = [
            row["startTime"] for row in conn.execute("SELECT startTime FROM fuelhh_actuals")
        ]
        half_hourly_forecasts = builder.step_hold_half_hourly(half_hourly_timestamps)

        matcher = SeriesMatcher(conn)
        matched_series_rows = matcher.match(half_hourly_forecasts)  

        metrics_calculator = MetricsCalculator(conn)
        metrics_summary_rows = metrics_calculator.calculate(
            scope_type, scope_period, start_time_from, start_time_to
        )  # step 4

        risk_floor_calculator = RiskFloorCalculator(conn)
        risk_floor_rows_backfilled = risk_floor_calculator.calculate(scope_type, scope_period)  # step 5

        return {
            "decision_time_forecast_rows": decision_time_forecast_rows,
            "matched_series_rows": matched_series_rows,
            "metrics_summary_rows": metrics_summary_rows,
            "risk_floor_rows_backfilled": risk_floor_rows_backfilled,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import json

    result = run_ingestion_pipeline()
    print(json.dumps(result, indent=2))
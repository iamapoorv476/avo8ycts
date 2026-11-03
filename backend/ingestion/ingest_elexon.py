"""One-off ingestion of raw FUELHH and WINDFOR data from the Elexon BMRS API.

This is a plain script, not a service: the project's data window is a fixed
historical period (January 2026 + a short lookback buffer), so there is no
need for live/on-request fetching (YAGNI). Re-run it whenever the raw tables
need to be rebuilt; inserts are idempotent (INSERT OR REPLACE on the natural
PK), so re-running is safe.

NETWORK NOTE: this script makes real outbound HTTPS calls to
data.elexon.co.uk. It will not run inside a sandboxed session whose egress
allowlist excludes that host (see PROGRESS.md) — run it from an environment
with normal internet access (local machine, CI, or the deploy target).

QUERY PARAM NOTE (confirmed against Elexon's own Swagger docs for this exact
endpoint, see PROGRESS.md): FUELHH's settlementDateFrom/settlementDateTo is
correct. WINDFOR's /datasets/WINDFOR/stream params are publishDateTimeFrom
and publishDateTimeTo, NOT from/to — an earlier version of this script used
from/to (inferred from a response's shape rather than the documented
contract, without ever confirming the actual request that produced it);
those params aren't recognized by this endpoint, so they were silently
ignored and the endpoint fell back to returning its current/live snapshot
regardless of the requested range. Confirmed correct now by reading the
endpoint's own Swagger parameter list directly.
"""

import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import get_connection, init_schema  # noqa: E402

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
REQUEST_TIMEOUT_SECONDS = 30

# Fixed historical window for this project (see docs/requirements.md).
# WINDFOR needs a lookback buffer before Jan 1 so that early-January decision
# times have a forecast vintage published before their 11:00 UTC cutoff.
FUELHH_FROM = date(2026, 1, 1)
FUELHH_TO = date(2026, 1, 31)
WINDFOR_FROM = date(2025, 12, 29)  # lookback buffer (WINDFOR horizon is ~67h)
WINDFOR_TO = date(2026, 1, 31)


def _fetch_stream(dataset: str, params: dict) -> list[dict]:
    """GET a dataset's /stream endpoint and return the raw JSON array.

    /stream returns a flat, unpaginated JSON array (confirmed against real
    sample responses during design) — no pagination handling needed.
    """
    url = f"{BASE_URL}/datasets/{dataset}/stream"
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()  # fail loudly on a bad request/response, never swallow
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array from {dataset}/stream, got {type(data).__name__}. "
            f"Response may be an error payload: {data!r}"
        )
    return data


def fetch_fuelhh(from_date: date, to_date: date) -> list[dict]:
    """Fetch FUELHH rows for the given settlement-date range (inclusive)."""
    params = {
        "settlementDateFrom": from_date.isoformat(),
        "settlementDateTo": to_date.isoformat(),
    }
    return _fetch_stream("FUELHH", params)


def fetch_windfor(from_date: date, to_date: date) -> list[dict]:
    """Fetch WINDFOR rows (all forecast vintages published in this date range),
    per the endpoint's documented publishDateTimeFrom/publishDateTimeTo params."""
    params = {
        "publishDateTimeFrom": from_date.isoformat() + "T00:00:00Z",
        "publishDateTimeTo": to_date.isoformat() + "T23:59:59Z",
    }
    return _fetch_stream("WINDFOR", params)


def load_fuelhh_actuals(conn, rows: list[dict]) -> int:
    """Insert FUELHH rows, filtered to wind generation only (AC scope)."""
    wind_rows = [r for r in rows if r.get("fuelType") == "WIND"]
    conn.executemany(
        """
        INSERT OR REPLACE INTO fuelhh_actuals (startTime, settlementDate, settlementPeriod, generation)
        VALUES (?, ?, ?, ?)
        """,
        [
            (r["startTime"], r["settlementDate"], r["settlementPeriod"], r["generation"])
            for r in wind_rows
        ],
    )
    return len(wind_rows)


def load_windfor_forecasts(conn, rows: list[dict]) -> int:
    """Insert all WINDFOR forecast vintages as-is (every row is already a wind forecast)."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO windfor_forecasts (startTime, publishTime, generation)
        VALUES (?, ?, ?)
        """,
        [(r["startTime"], r["publishTime"], r["generation"]) for r in rows],
    )
    return len(rows)


def _sanity_check_windfor_rows(rows: list[dict]) -> None:
    """Fail loudly if the fetched WINDFOR data doesn't actually cover the
    requested historical window.

    This exists to catch the exact failure mode found during a real
    ingestion run: wrong/unrecognized query params don't error, they get
    silently ignored and the endpoint falls back to its current-snapshot
    default. Kept as a permanent guard even now that the params are
    confirmed correct, since it's cheap insurance against this exact
    silent-wrong-data failure mode recurring (e.g. if Elexon changes the
    API later).
    """
    if not rows:
        raise ValueError("WINDFOR fetch returned no rows at all.")

    publish_dates = {r["publishTime"][:10] for r in rows}
    out_of_range = {
        d for d in publish_dates if not (WINDFOR_FROM.isoformat() <= d <= WINDFOR_TO.isoformat())
    }
    if out_of_range:
        raise ValueError(
            f"WINDFOR fetch returned publishTime dates outside the requested "
            f"{WINDFOR_FROM} to {WINDFOR_TO} window: {sorted(out_of_range)}. "
            "This is the known failure mode where the API silently ignores "
            "unrecognized/wrong query params and returns its current-snapshot "
            "default instead — double check the param names against Swagger."
        )


def run() -> None:
    init_schema()
    conn = get_connection()
    try:
        print(f"Fetching FUELHH {FUELHH_FROM} to {FUELHH_TO}...")
        fuelhh_rows = fetch_fuelhh(FUELHH_FROM, FUELHH_TO)
        wind_count = load_fuelhh_actuals(conn, fuelhh_rows)
        print(f"  -> {len(fuelhh_rows)} rows fetched, {wind_count} WIND rows loaded")

        print(f"Fetching WINDFOR {WINDFOR_FROM} to {WINDFOR_TO}...")
        windfor_rows = fetch_windfor(WINDFOR_FROM, WINDFOR_TO)
        _sanity_check_windfor_rows(windfor_rows)
        forecast_count = load_windfor_forecasts(conn, windfor_rows)
        print(f"  -> {forecast_count} forecast-vintage rows loaded")

        conn.commit()
    finally:
        conn.close()
    print("Raw ingestion complete.")


if __name__ == "__main__":
    run()
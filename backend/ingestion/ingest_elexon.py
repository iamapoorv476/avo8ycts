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

QUERY PARAM NOTE (verified): FUELHH's settlementDateFrom/settlementDateTo
and WINDFOR's from/to are both confirmed correct against real sample pulls
(see PROGRESS.md) — FUELHH's row count matched exactly (settlement dates x
periods x fuel types), and WINDFOR's from/to was confirmed to bound
publishTime specifically, not startTime: a sample pull with from=2025-12-29,
to=~2026-01-01 returned 32 distinct publishTime vintages inside that window,
each carrying its own ~73h-forward startTime horizon that extends past the
"to" bound — exactly the shape a publishTime-bounded query produces.

WINDFOR RANGE LIMIT (discovered via a real ingestion run, see PROGRESS.md):
a single WINDFOR /stream request spanning ~34 days (the full lookback-to-
January window) does NOT error — it silently ignores from/to and returns
the single current "live" forecast vintage instead, with no indication
anything went wrong. A verified-working manual request spanned ~4 days.
To work around this, WINDFOR is fetched in WINDFOR_CHUNK_DAYS-sized windows
and the results are stitched together (fetch_windfor_chunked).
"""

import sys
from datetime import date, timedelta
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
WINDFOR_CHUNK_DAYS = 3  # stay safely under the ~4-day span confirmed to work (see module docstring)


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
    """Fetch WINDFOR rows (all forecast vintages) for the given date range (inclusive).

    Callers wanting a wide date range should use fetch_windfor_chunked instead —
    a single request spanning too many days silently returns the wrong data
    (see module docstring).
    """
    params = {
        "from": from_date.isoformat() + "T00:00:00Z",
        "to": to_date.isoformat() + "T23:59:59Z",
    }
    return _fetch_stream("WINDFOR", params)


def _date_chunks(start: date, end: date, chunk_days: int):
    """Yield (chunk_start, chunk_end) pairs covering [start, end] inclusive, each
    spanning at most chunk_days calendar days."""
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def fetch_windfor_chunked(
    from_date: date, to_date: date, chunk_days: int = WINDFOR_CHUNK_DAYS
) -> list[dict]:
    """Fetch WINDFOR across a wide date range by stitching together several
    narrower requests (see WINDFOR RANGE LIMIT in the module docstring for why
    this is necessary rather than optional)."""
    all_rows: list[dict] = []
    for chunk_from, chunk_to in _date_chunks(from_date, to_date, chunk_days):
        print(f"  WINDFOR chunk {chunk_from} to {chunk_to}...")
        chunk_rows = fetch_windfor(chunk_from, chunk_to)
        print(f"    -> {len(chunk_rows)} rows")
        all_rows.extend(chunk_rows)
    return all_rows


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

    This exists specifically to catch the failure mode discovered during a
    real ingestion run: a too-wide date range doesn't error, it silently
    returns the single current "live" forecast vintage instead. Without this
    check, that failure would only surface downstream as a near-empty
    matched_series/risk-floor result with no obvious cause.
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
            "from/to for a too-wide single request and returns the current "
            "live forecast instead — if this fires, lower WINDFOR_CHUNK_DAYS."
        )


def run() -> None:
    init_schema()
    conn = get_connection()
    try:
        print(f"Fetching FUELHH {FUELHH_FROM} to {FUELHH_TO}...")
        fuelhh_rows = fetch_fuelhh(FUELHH_FROM, FUELHH_TO)
        wind_count = load_fuelhh_actuals(conn, fuelhh_rows)
        print(f"  -> {len(fuelhh_rows)} rows fetched, {wind_count} WIND rows loaded")

        print(f"Fetching WINDFOR {WINDFOR_FROM} to {WINDFOR_TO} (chunked)...")
        windfor_rows = fetch_windfor_chunked(WINDFOR_FROM, WINDFOR_TO)
        _sanity_check_windfor_rows(windfor_rows)
        forecast_count = load_windfor_forecasts(conn, windfor_rows)
        print(f"  -> {forecast_count} forecast-vintage rows loaded total")

        conn.commit()
    finally:
        conn.close()
    print("Raw ingestion complete.")


if __name__ == "__main__":
    run()
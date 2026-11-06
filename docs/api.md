# API reference

Base URL (local dev): `http://localhost:8000`

The API reads data that has already been processed by the ingestion pipeline. Forecast matching, metric calculations, and risk-floor calculations happen offline in `ingestion/run_ingestion_pipeline.py`, rather than on every request. This keeps the API responses fast and predictable, which is important for a tool intended for a trading desk.

There are two types of reads:
- **Precomputed data:** `forecast-detail`, `risk-floor`, and `MONTH` metrics return results stored during ingestion.
- **Computed and cached data:** `RANGE` metrics are calculated the first time a date range is requested and saved to `metrics_summary`. Subsequent requests for the same range read the stored result.

One additional read-time operation is `/metrics`'s `exclusionBreakdown`. It uses a `GROUP BY` over `matched_series.exclusion_reason`, a column already populated during ingestion. It doesn't recalculate forecasts or metrics, and avoids maintaining a separate table just for this breakdown (YAGNI).

## `GET /api/v1/forecast-detail`

Returns every settlement period for a delivery date, including the step-held decision-time forecast, the forecast vintage's `publishTime` (audit trail, AC 1.3), the actual generation, and the status.

**Query params**

| param | required | example | notes |
|---|---|---|---|
| `date` | yes | `2026-01-15` | delivery date (YYYY-MM-DD) |

**Response**

```json
{
  "date": "2026-01-15",
  "cutoffApplied": "2026-01-14T11:00:00Z",
  "periods": [
    {
      "settlementPeriod": 33,
      "startTime": "2026-01-15T16:00:00Z",
      "forecastMw": 19466.0,
      "sourcePublishTime": "2026-01-14T09:00:00Z",
      "actualMw": 13756.0,
      "status": "OK"
    }
  ]
}
```

`status` can be `OK`, `NO_FORECAST_BEFORE_CUTOFF`, or `MISSING_OR_INVALID_ACTUAL`. These are the same exclusion reasons assigned by `SeriesMatcher` during ingestion (AC 1.5, AC 2.1). The API returns the stored status without recalculating it.

Returns `404` if no row exists for the requested date, such as a date outside the ingested January 2026 period and its lookback buffer.

## `GET /api/v1/metrics`

Returns MBE, MAE, RMSE, and σ for the requested scope and segment (AC 2.2, 2.3).

**Query params**

| param | required | example | notes |
|---|---|---|---|
| `scopeType` | yes | `MONTH` | `MONTH` or `RANGE` |
| `scopePeriod` | yes | `2026-01` | `YYYY-MM` for MONTH, `YYYY-MM-DD_YYYY-MM-DD` for RANGE |
| `segment` | no (default `ALL`) | `PEAK` | `ALL`, `PEAK`, or `OFFPEAK` |

**Response**

```json
{
  "scopeType": "MONTH",
  "scopePeriod": "2026-01",
  "segment": "ALL",
  "mbe": 1840.3,
  "mae": 2126.1,
  "rmse": 2620.8,
  "sigmaResidual": 1866.6,
  "n": 1488,
  "excludedCount": 0,
  "exclusionBreakdown": {}
}
```

**MONTH** scopes are calculated during ingestion. `run_ingestion_pipeline.py` always computes the `MONTH`/`2026-01` scope. The API returns `404` if the exact `(scopeType, scopePeriod, segment)` combination requested has not been precomputed.

**RANGE** scopes are calculated on the first request rather than during ingestion. There are too many possible date ranges to precompute them all. On the first request for a range, the API aggregates `matched_series.error_mw` and uses the existing `MetricsCalculator` to calculate the metrics. The error values are already computed during ingestion, along with forecast matching, step-hold resampling, and exclusions. The resulting metrics are saved to `metrics_summary`, so subsequent requests for the same range return the cached result. The API returns `400` if `scopePeriod` isn't a valid `YYYY-MM-DD_YYYY-MM-DD` range.

## `GET /api/v1/risk-floor`

Returns the bias-corrected generation floor, representing approximately 90% downside confidence, for every period on a date with an available forecast (AC 2.4, 2.5).

**Query params**

| param | required | example | notes |
|---|---|---|---|
| `date` | yes | `2026-01-15` | delivery date (YYYY-MM-DD) |

**Response**

```json
{
  "date": "2026-01-15",
  "periods": [
    {
      "settlementPeriod": 33,
      "segment": "PEAK",
      "forecastMw": 19466.0,
      "floorMw": 15213.4,
      "advisoryText": "Peak (16:00-19:00 GMT): forecast tends to over-forecast (MBE +1840.3 MW), ..."
    }
  ]
}
```

Periods without a forecast (`NO_FORECAST_BEFORE_CUTOFF`) are omitted because there is no forecast to calculate a floor from. The API returns `404` if the requested date has no rows.

## Running it locally

From `backend/`:

pip install -r requirements.txt
python -m uvicorn api.main:app --reload

Use `python -m uvicorn` instead of running `uvicorn` directly. The `-m` form ensures the current directory is on `sys.path`, which is needed for this app's absolute imports such as `api.*`. Interactive API documentation is available at `http://localhost:8000/docs`.
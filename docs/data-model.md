# Data Model

The data model has two layers: a **raw layer**, which stores an append-only and faithful copy of the data published by Elexon, and a **derived layer**, which contains values computed during ingestion or refresh. This keeps API requests focused on reading precomputed data, with no business logic in the request path.

Storage: SQLite. The expected data volume is small (~1,488 FUELHH wind rows and ~16–17k WINDFOR rows for the January 2026 period and its lookback window). Since the workload is read-heavy and analytical, a single-file embedded database is sufficient for this scope. A client/server database would add complexity without a clear benefit (YAGNI).

Conventions:
- All timestamps are stored in UTC. The logical column type is `TIMESTAMPTZ` (represented as ISO-8601 UTC text in SQLite).
- `generation` is stored as `NUMERIC(9,3)` in MW rather than `FLOAT`, to reduce floating-point representation issues such as `1240.2999999997` instead of `1240.300`.
- `settlementPeriod` is stored as `SMALLINT`.
- **Column naming:** The raw layer retains Elexon's field names exactly as they appear in the source API (`startTime`, `settlementPeriod`, `publishTime`, and so on). This makes it easy to compare a raw database row with the original Elexon response. The derived layer uses `snake_case` for computed and internal columns (`error_mw`, `source_publish_time`, `scope_type`, etc.), since these fields are not part of Elexon's original schema.

## RAW LAYER (append-only, ingested once from Elexon API)

### `fuelhh_actuals`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | **PK.** Stored in UTC, so timestamps remain unambiguous even on UK clock-change days. DST handling is outside the January 2026 scope, as described in `requirements.md`. |
| `settlementDate` | `DATE` | |
| `settlementPeriod` | `SMALLINT` | Values range from 1–48 for the dates in scope. |
| `generation` | `NUMERIC(9,3)` | MW. `fuelType` is filtered to `WIND` during ingestion and is not stored. Every row in this table represents wind generation by construction, so retaining the filtered-out column would add no value (YAGNI). |

### `windfor_forecasts`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | Part of the PK. Represents the hourly forecast period. |
| `publishTime` | `TIMESTAMPTZ` | Part of the PK. Multiple forecast vintages can exist for the same `startTime`. |
| `generation` | `NUMERIC(9,3)` | MW. |

**PK:** `(startTime, publishTime)`

**Index:** `(startTime, publishTime DESC)` — supports the range scan used to find the latest forecast vintage at or before the cutoff for each `startTime` when building `decision_time_forecast`. The primary key already provides a B-tree index on `(startTime, publishTime)` in ascending order. A separate descending index can be considered if query-plan testing shows that it improves this lookup.

## DERIVED LAYER (computed once at ingest/refresh time, not recomputed per request)

### `decision_time_forecast`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | **PK.** |
| `generation` | `NUMERIC(9,3)` | Selected hourly forecast value before step-hold expansion. |
| `source_publish_time` | `TIMESTAMPTZ` | Audit trail showing which forecast vintage was active at the decision cutoff (AC 1.3). |

Built using a window function:

```sql
ROW_NUMBER() OVER (
    PARTITION BY startTime
    ORDER BY publishTime DESC
)
WHERE publishTime <= DECISION_GATE_CUTOFF_UTC(startTime)
-- take rank = 1
```

Only one fixed cutoff profile is required for this scope, so `startTime` is sufficient as the primary key. If multiple cutoff definitions are introduced later, the primary key can be expanded to `(cutoff_profile, startTime)`. That additional complexity is unnecessary here because only one cutoff, 11:00 UTC day-ahead, is in scope.

### `matched_series`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | **PK.** |
| `settlementPeriod` | `SMALLINT` | |
| `segment` | `TEXT` | `CHECK (segment IN ('PEAK','OFFPEAK'))` |
| `forecast_mw` | `NUMERIC(9,3)` | Step-held decision-time forecast for this half-hour period. `NULL` when the row is excluded because no forecast is available. |
| `source_publish_time` | `TIMESTAMPTZ NULL` | Carried over from `decision_time_forecast.source_publish_time` for the hourly forecast covering this half-hour period. This preserves the AC 1.3 audit trail without reconstructing it during an API request, in line with the no-business-logic-in-the-request-path rule in `api.md`. `NULL` when excluded. |
| `actual_mw` | `NUMERIC(9,3)` | `NULL` when the actual value is missing or invalid and the row is excluded. |
| `error_mw` | `NUMERIC(9,3)` | `GENERATED ALWAYS AS (forecast_mw - actual_mw) STORED`. **Sign convention: Forecast − Actual (positive = over-forecasting).** |
| `included` | `BOOLEAN` | |
| `exclusion_reason` | `TEXT NULL` | `CHECK (exclusion_reason IN ('NO_FORECAST_BEFORE_CUTOFF', 'MISSING_OR_INVALID_ACTUAL'))` |
| `floor_mw` | `NUMERIC(9,3)` | Precomputed using the AC 2.4 formula. Backfilled after `metrics_summary` has been built because the calculation requires the segment-level MBE and σ. |
| `advisory_text` | `TEXT` | Precomputed advisory text based on the relevant segment (AC 2.5). |

### `metrics_summary`

| Column | Type | Notes |
|---|---|---|
| `scope_type` | `TEXT` | Part of the PK. `CHECK (scope_type IN ('MONTH','RANGE'))` |
| `scope_period` | `TEXT` | Part of the PK. For example, `'2026-01'` or `'2026-01-01_2026-01-31'`. |
| `segment` | `TEXT` | Part of the PK. `CHECK (segment IN ('ALL','PEAK','OFFPEAK'))` |
| `mbe`, `mae`, `rmse` | `NUMERIC(9,3)` | Calculated according to AC 2.2. |
| `sigma_residual` | `NUMERIC(9,3)` | Sample standard deviation of residuals around the group's own MBE. |
| `n` | `INTEGER` | Number of included, valid observations in the group. |
| `excluded_count` | `INTEGER` | Number of excluded observations, retained for transparency. |

**PK:** `(scope_type, scope_period, segment)`

A simpler `(scope, segment)` primary key was rejected because a month-level scope alone would not distinguish different months. For example, January and February 2026 would share the same key and could overwrite each other. Including `scope_period` avoids this collision.

## Build order (dependency chain)

1. Ingest raw `fuelhh_actuals` and `windfor_forecasts` from the Elexon `/stream` endpoints.
2. Build `decision_time_forecast` by selecting the latest forecast vintage at or before the cutoff for each `startTime`.
3. Build `matched_series` by joining forecasts with actuals and assigning exclusion flags. Do not calculate `floor_mw` or `advisory_text` at this stage, since both depend on segment-level MBE and σ values that are not available until step 4.
4. Build `metrics_summary` by aggregating `matched_series` rows where `included = TRUE`.
5. Backfill `matched_series.floor_mw` and `matched_series.advisory_text` using the segment-level MBE and σ_residual values from `metrics_summary`.

This dependency chain is why `run_ingestion_pipeline` is implemented as a straightforward orchestration function rather than a class. It calls four independent, single-responsibility components in a fixed sequence. There is no shared mutable state or current extensibility requirement that would justify introducing a class. Keeping the implementation simple avoids speculative abstraction (YAGNI).
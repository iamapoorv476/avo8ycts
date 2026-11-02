# Data Model

The data model uses two layers: a **raw layer** that stores an append-only copy of the data received from Elexon, and a **derived layer** that stores the results of the calculations needed by the application.

The derived data is prepared during ingestion or refresh, so API requests only need to read precomputed results. Forecast selection, matching, and metric calculations won't need to run every time someone makes a request.

**Storage:** SQLite. The dataset is relatively small, with approximately 1,488 FUELHH wind records and 16,000–17,000 WINDFOR records for January 2026 and the lookback period. Since the tool is mainly read-heavy and used for analysis, a single-file embedded database is sufficient. A separate client/server database would add unnecessary complexity for this scope (YAGNI).

**Conventions:**
- All timestamps are stored in UTC using the `TIMESTAMPTZ` convention (in SQLite, stored as ISO-8601 text in UTC).
- `generation` is stored as `NUMERIC(9,3)` in MW rather than `FLOAT`. This avoids floating-point representation issues, such as `1240.2999999997` instead of `1240.300`.
- `settlementPeriod` is stored as `SMALLINT`.

## RAW LAYER (append-only, ingested once from Elexon API)

### `fuelhh_actuals`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | **PK.** Stored in UTC, so each settlement period has an unambiguous timestamp, including on UK clock-change days. DST handling is outside the current scope, as described in `requirements.md`. |
| `settlementDate` | `DATE` | |
| `settlementPeriod` | `SMALLINT` | 1–48 for the dates covered by this project. |
| `generation` | `NUMERIC(9,3)` | MW. Only records with `fuelType = WIND` are ingested, so there is no need to store `fuelType` separately. Every record in this table represents wind generation. |

### `windfor_forecasts`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | Part of the primary key. Represents the hourly forecast time. |
| `publishTime` | `TIMESTAMPTZ` | Part of the primary key. Multiple forecast vintages can exist for the same `startTime`. |
| `generation` | `NUMERIC(9,3)` | MW. |

**PK:** `(startTime, publishTime)`

**Index:** `(startTime, publishTime DESC)` — supports the query that selects the latest forecast vintage published on or before the decision cutoff for each `startTime`.

The primary key already provides a B-tree index on `(startTime, publishTime)` in ascending order. The additional index supports queries that need to retrieve vintages in descending `publishTime` order within each `startTime`.

## DERIVED LAYER (computed during ingestion or refresh, not per request)

### `decision_time_forecast`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | **PK.** |
| `generation` | `NUMERIC(9,3)` | Selected hourly forecast value, before expanding it to half-hourly settlement periods. |
| `source_publishTime` | `TIMESTAMPTZ` | Records which forecast vintage was selected at the decision cutoff. This provides the audit trail required by AC 1.3. |

This table is built using a window function that ranks forecast vintages for each `startTime` by `publishTime`, with the most recent eligible vintage ranked first:

```sql
ROW_NUMBER() OVER (PARTITION BY startTime ORDER BY publishTime DESC)
WHERE publishTime <= DECISION_GATE_CUTOFF_UTC(startTime)
-- take rank = 1
```

Only the latest forecast published on or before the decision cutoff is selected.

There is only one cutoff profile in the current scope: 11:00 UTC on the day before delivery. Therefore, `startTime` is sufficient as the primary key. If the system later needs to support multiple cutoff profiles, the key can be expanded to `(cutoff_profile, startTime)`. That additional complexity is not needed for this version.

### `matched_series`

| Column | Type | Notes |
|---|---|---|
| `startTime` | `TIMESTAMPTZ` | **PK.** |
| `settlementPeriod` | `SMALLINT` | |
| `segment` | `TEXT` | `CHECK (segment IN ('PEAK','OFFPEAK'))` |
| `forecast_mw` | `NUMERIC(9,3)` | Decision-time forecast expanded to half-hourly resolution using step-hold. |
| `actual_mw` | `NUMERIC(9,3)` | Actual wind generation from FUELHH. |
| `error_mw` | `NUMERIC(9,3)` | `GENERATED ALWAYS AS (forecast_mw - actual_mw) STORED`. **Sign convention: Forecast − Actual (positive = over-forecasting).** |
| `included` | `BOOLEAN` | Indicates whether the record is included in metric and generation-floor calculations. |
| `exclusion_reason` | `TEXT NULL` | `CHECK (exclusion_reason IN ('NO_FORECAST_BEFORE_CUTOFF', 'MISSING_OR_INVALID_ACTUAL'))` |
| `floor_mw` | `NUMERIC(9,3)` | Precomputed using the AC 2.4 formula. Populated after `metrics_summary` is calculated, since the calculation requires the segment's MBE and standard deviation. |
| `advisory_text` | `TEXT` | Precomputed explanation based on the period's segment, as required by AC 2.5. |

### `metrics_summary`

| Column | Type | Notes |
|---|---|---|
| `scope_type` | `TEXT` | Part of the primary key. `CHECK (scope_type IN ('MONTH','RANGE'))` |
| `scope_period` | `TEXT` | Part of the primary key. For example, `'2026-01'` or `'2026-01-01_2026-01-31'`. |
| `segment` | `TEXT` | Part of the primary key. `CHECK (segment IN ('ALL','PEAK','OFFPEAK'))` |
| `mbe`, `mae`, `rmse` | `NUMERIC` | Forecast accuracy metrics calculated for the selected scope and segment. |
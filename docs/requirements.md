# Requirements & Acceptance Criteria

**Product:** Wind Generation Forecast Accuracy Tool  
**Audience:** UK energy utility trading team  
**Scope:** Elexon BMRS `FUELHH` (actuals) and `WINDFOR` (forecasts) datasets, covering January 2026 delivery dates only.

## Context & Assumptions

- **Decision cutoff assumption:** The trading desk is assumed to make its day-ahead decision at a fixed daily cutoff of **11:00 UTC**. This is a simplifying assumption for the assignment, not a cutoff taken from the actual gate-closure schedule of a specific exchange such as EPEX or Nord Pool. The assignment datasets (`FUELHH` and `WINDFOR`) do not include a market or exchange identifier that could be used to determine different cutoffs. A configurable cutoff for each market was considered, but a single cutoff is sufficient for the current single-desk scope (YAGNI).
- **No DST handling:** UK clocks change in March and October. January 2026 has no 46- or 50-period settlement days, so the settlement-period logic only needs to support 48 periods per day for this assignment. Handling daylight saving time changes is explicitly out of scope.
- **Data window:** Actuals and forecasts will be ingested for January 2026, along with a short lookback period into late December 2025. This ensures that the system has enough forecast history to select the latest available forecast before the cutoff for the first few days of January.

## Feature 1 — View the Decision-Time Forecast

**AC 1.1** — For any delivery date in January 2026, the system must show the wind generation forecast that was available to the trader at the 11:00 UTC decision cutoff on the previous day (day-ahead). It must use the latest forecast published on or before that cutoff, never a forecast published afterwards or the final, most recent forecast vintage.

**AC 1.2** — Forecasts must be displayed at half-hourly (settlement period) resolution to match the actual generation data, even though the underlying WINDFOR dataset is published hourly.

**AC 1.3** — For every settlement period, the system must also display the `publishTime` of the forecast vintage used. This provides an audit trail and allows traders to see how recently the forecast was published at the time of their decision.

**AC 1.4** — Since WINDFOR publishes hourly forecasts while FUELHH provides half-hourly data, each hourly forecast value must be applied to both half-hourly settlement periods within that hour using **step-hold (zero-order hold / forward-fill)**. Interpolation must not be used. Step-hold preserves the value that was actually available at the hourly resolution, whereas interpolation would introduce half-hourly values that were never published or available to the trader.

**AC 1.5** — If no WINDFOR forecast exists with a `publishTime` on or before the 11:00 UTC cutoff for a given `startTime`, the settlement period must be flagged as having no decision-time forecast available (`NO_FORECAST_BEFORE_CUTOFF`). The system must not silently omit the period or fill it using a forecast published after the cutoff.

## Feature 2 — Evaluate Forecast Accuracy

**AC 2.1** — The system must join the decision-time forecast from Feature 1, already converted to half-hourly resolution using step-hold, with the actual FUELHH wind generation for the same `startTime`. This should produce up to 1,488 paired settlement-period records for January 2026 (31 days × 48 periods). Any period that cannot be paired because of AC 1.5 or AC 2.6 must still be recorded with a clear reason and included in the output. No records should be silently dropped.

**AC 2.2** — The system must calculate the following forecast-error metrics across matched records for a selectable period, either a calendar month or an explicitly selected date range:
- **MBE** (Mean Bias Error) = mean(Forecast − Actual). A positive value indicates systematic over-forecasting.
- **MAE** (Mean Absolute Error) = mean(|Forecast − Actual|).
- **RMSE** (Root Mean Square Error) = sqrt(mean((Forecast − Actual)²)).

**AC 2.3** — All three metrics must be calculated separately for the following segments: **ALL** periods, **PEAK** (settlement periods 33–38, covering 16:00–19:00 GMT) and **OFF-PEAK** (all remaining periods). This breakdown is important because forecast bias and error can vary throughout the day, and accuracy during peak hours carries greater commercial weight.

**AC 2.4** — The system must calculate a **bias-corrected, conservative generation floor** for each settlement period. This provides a more cautious generation estimate that can be used for risk-aware planning:

Floor_t = max(0, (ŷ_t − MBE_group) − 1.28 · σ_residual,group)

where `ŷ_t` is the decision-time forecast for period *t*, and `MBE_group` and `σ_residual,group` represent the mean bias and sample standard deviation of residuals (errors measured around the group's own mean error) for the PEAK or OFF-PEAK segment to which that period belongs. The multiplier `1.28` approximates a one-sided P90 confidence bound, assuming residuals follow a normal distribution.

The calculation must first correct the forecast for the segment's historical bias, then subtract a downside buffer based on the spread of its residual errors. These adjustments form one combined correction. The bias must not be subtracted twice.

**AC 2.5** — Each generation-floor value must include a short explanation based on its segment. For example, the advisory should identify whether the period is PEAK or OFF-PEAK and describe the segment's typical forecast bias and error spread. This gives traders some context behind the number instead of presenting an unexplained figure.

**AC 2.6** — A settlement period must be excluded from metric and generation-floor calculations if either of the following conditions applies. However, it must still be recorded with the corresponding reason, as required by AC 2.1:
- No decision-time forecast is available (`NO_FORECAST_BEFORE_CUTOFF`, as defined in AC 1.5).
- The corresponding FUELHH actual is missing or invalid (`MISSING_OR_INVALID_ACTUAL`).

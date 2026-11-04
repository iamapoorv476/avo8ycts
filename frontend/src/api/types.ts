

export type PeriodStatus = "OK" | "NO_FORECAST_BEFORE_CUTOFF" | "MISSING_OR_INVALID_ACTUAL";

export interface ForecastDetailPeriod {
  settlementPeriod: number;
  startTime: string;
  forecastMw: number | null;
  sourcePublishTime: string | null;
  actualMw: number | null;
  status: PeriodStatus;
}

export interface ForecastDetailResponse {
  date: string;
  cutoffApplied: string;
  periods: ForecastDetailPeriod[];
}

export type Segment = "ALL" | "PEAK" | "OFFPEAK";

export interface MetricsResponse {
  scopeType: string;
  scopePeriod: string;
  segment: Segment;
  mbe: number;
  mae: number;
  rmse: number;
  sigmaResidual: number;
  n: number;
  excludedCount: number;
  exclusionBreakdown: Record<string, number>;
}

export interface RiskFloorPeriod {
  settlementPeriod: number;
  segment: "PEAK" | "OFFPEAK";
  forecastMw: number;
  floorMw: number;
  advisoryText: string;
}

export interface RiskFloorResponse {
  date: string;
  periods: RiskFloorPeriod[];
}
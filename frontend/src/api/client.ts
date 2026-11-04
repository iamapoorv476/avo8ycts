import type { ForecastDetailResponse, MetricsResponse, RiskFloorResponse, Segment } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, params: Record<string, string>): Promise<T> {
  const url = `${API_BASE_URL}/api/v1/${path}?${new URLSearchParams(params).toString()}`;
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(body.detail ?? response.statusText, response.status);
  }
  return response.json() as Promise<T>;
}

export function fetchForecastDetail(date: string): Promise<ForecastDetailResponse> {
  return getJson<ForecastDetailResponse>("forecast-detail", { date });
}

export function fetchRiskFloor(date: string): Promise<RiskFloorResponse> {
  return getJson<RiskFloorResponse>("risk-floor", { date });
}

export function fetchMetrics(
  scopeType: string,
  scopePeriod: string,
  segment: Segment,
): Promise<MetricsResponse> {
  return getJson<MetricsResponse>("metrics", { scopeType, scopePeriod, segment });
}
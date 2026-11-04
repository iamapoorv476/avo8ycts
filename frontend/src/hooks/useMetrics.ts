import { fetchMetrics } from "../api/client";
import type { MetricsResponse } from "../api/types";
import { useAsync } from "./useAsync";

export interface SegmentedMetrics {
  all: MetricsResponse;
  peak: MetricsResponse;
  offpeak: MetricsResponse;
}

export function useMetrics(scopeType: string, scopePeriod: string) {
  return useAsync<SegmentedMetrics>(
    async () => {
      const [all, peak, offpeak] = await Promise.all([
        fetchMetrics(scopeType, scopePeriod, "ALL"),
        fetchMetrics(scopeType, scopePeriod, "PEAK"),
        fetchMetrics(scopeType, scopePeriod, "OFFPEAK"),
      ]);
      return { all, peak, offpeak };
    },
    [scopeType, scopePeriod],
  );
}

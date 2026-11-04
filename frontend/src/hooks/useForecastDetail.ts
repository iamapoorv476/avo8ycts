import { fetchForecastDetail } from "../api/client";
import { useAsync } from "./useAsync";

export function useForecastDetail(date: string) {
  return useAsync(() => fetchForecastDetail(date), [date]);
}
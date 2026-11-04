import { fetchRiskFloor } from "../api/client";
import { useAsync } from "./useAsync";

export function useRiskFloor(date: string) {
  return useAsync(() => fetchRiskFloor(date), [date]);
}
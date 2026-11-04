import { Target, ShieldAlert, Info } from "lucide-react";
import type { MetricsResponse } from "../api/types";

interface AdvisoryPanelProps {
  monthMetrics: MetricsResponse;
  peakAdvisoryText: string | null;
  cutoffApplied: string | null;
  vintagePublishTime: string | null;
}


export function AdvisoryPanel({
  monthMetrics,
  peakAdvisoryText,
  cutoffApplied,
  vintagePublishTime,
}: AdvisoryPanelProps) {
  const haircutMw = Math.round(monthMetrics.mbe);

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="rounded-lg border border-emerald-900 bg-emerald-950/30 p-4">
        <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase text-emerald-400">
          <Target className="h-3.5 w-3.5" /> Recommended Desk Action
        </div>
        <p className="text-sm leading-relaxed text-slate-300">
          Systematic over-forecasting observed across {monthMetrics.scopePeriod} (
          {haircutMw >= 0 ? "+" : ""}
          {haircutMw.toLocaleString()} MW).{" "}
          {haircutMw > 0 ? (
            <>
              Apply a <span className="font-mono text-emerald-300">-{haircutMw.toLocaleString()} MW</span>{" "}
              haircut to the nominal wind forecast before placing day-ahead orders.
            </>
          ) : (
            "No systematic haircut indicated this period."
          )}
        </p>
      </div>

      {peakAdvisoryText && (
        <div className="rounded-lg border border-amber-900 bg-amber-950/30 p-4">
          <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase text-amber-400">
            <ShieldAlert className="h-3.5 w-3.5" /> Evening Peak Safety (16:00-19:00)
          </div>
          <p className="text-sm leading-relaxed text-slate-300">{peakAdvisoryText}</p>
        </div>
      )}

      <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-4">
        <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase text-slate-400">
          <Info className="h-3.5 w-3.5" /> Point-in-Time Audit
        </div>
        <div className="space-y-1 font-mono text-xs text-slate-400">
          {vintagePublishTime && <div>Vintage frozen: {vintagePublishTime.slice(0, 16).replace("T", " ")} UTC</div>}
          {cutoffApplied && <div>Gate closure: {cutoffApplied.slice(0, 16).replace("T", " ")} UTC</div>}
        </div>
      </div>
    </div>
  );
}
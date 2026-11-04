import { Activity, TrendingDown, TrendingUp, Gauge } from "lucide-react";
import type { SegmentedMetrics } from "../hooks/useMetrics";
import { MetricCard } from "./MetricCard";

function Badge({ tone, children }: { tone: "rose" | "amber" | "cyan"; children: string }) {
  const toneClasses = {
    rose: "bg-rose-950/60 text-rose-400 border-rose-900",
    amber: "bg-amber-950/60 text-amber-400 border-amber-900",
    cyan: "bg-cyan-950/60 text-cyan-400 border-cyan-900",
  }[tone];
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${toneClasses}`}>
      {children}
    </span>
  );
}

const fmt = (n: number) => Math.round(n).toLocaleString("en-GB");

export function MetricsRow({ metrics }: { metrics: SegmentedMetrics }) {
  const { all, peak, offpeak } = metrics;

  const tailRiskRatio = all.mae > 0 ? all.rmse / all.mae : 0;
  const isHighVolatility = tailRiskRatio > 1.3;

  const peakSqueezePct = offpeak.mae > 0 ? ((peak.mae - offpeak.mae) / offpeak.mae) * 100 : 0;

  return (
    <div className="flex gap-4 px-6 py-4">
      <MetricCard
        icon={Activity}
        label="Mean Absolute Error"
        value={`${fmt(all.mae)} MW`}
        sublabel={`Avg daily exposure (n=${all.n})`}
      />

      <MetricCard
        icon={all.mbe >= 0 ? TrendingUp : TrendingDown}
        label="Systematic Bias (MBE)"
        value={`${all.mbe >= 0 ? "+" : ""}${fmt(all.mbe)} MW`}
        sublabel="Portfolio tilt"
        badge={
          <Badge tone={all.mbe >= 0 ? "rose" : "cyan"}>
            {all.mbe >= 0 ? "Over-forecast (short)" : "Under-forecast (long)"}
          </Badge>
        }
      />

      <MetricCard
        icon={Gauge}
        label="Tail Risk Ratio (RMSE/MAE)"
        value={`${tailRiskRatio.toFixed(2)}x`}
        sublabel="Volatility factor"
        badge={isHighVolatility ? <Badge tone="amber">High volatility</Badge> : undefined}
      />

      <MetricCard
        icon={peakSqueezePct >= 0 ? TrendingUp : TrendingDown}
        label="Peak Squeeze (SP 33-38, 16:00-19:00)"
        value={`${fmt(peak.mae)} MW`}
        sublabel={`${peakSqueezePct >= 0 ? "+" : ""}${peakSqueezePct.toFixed(0)}% vs off-peak`}
      />
    </div>
  );
}
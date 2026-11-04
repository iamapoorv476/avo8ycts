import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ForecastDetailPeriod, RiskFloorPeriod } from "../api/types";

interface ChartPoint {
  settlementPeriod: number;
  forecastMw: number | null;
  actualMw: number | null;
  floorMw: number | null;
  sourcePublishTime: string | null;
}

function periodToTimeLabel(settlementPeriod: number): string {
  const minutesAfterMidnight = (settlementPeriod - 1) * 30;
  const hours = Math.floor(minutesAfterMidnight / 60);
  const minutes = minutesAfterMidnight % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function formatUtc(iso: string): string {
  return iso.slice(0, 16).replace("T", " ") + " UTC";
}

function buildChartData(
  forecastPeriods: ForecastDetailPeriod[],
  riskFloorPeriods: RiskFloorPeriod[],
): ChartPoint[] {
  const floorByPeriod = new Map(riskFloorPeriods.map((p) => [p.settlementPeriod, p]));
  return forecastPeriods.map((p) => ({
    settlementPeriod: p.settlementPeriod,
    forecastMw: p.forecastMw,
    actualMw: p.actualMw,
    floorMw: floorByPeriod.get(p.settlementPeriod)?.floorMw ?? null,
    sourcePublishTime: p.sourcePublishTime,
  }));
}

function derivePeakWindow(riskFloorPeriods: RiskFloorPeriod[]): [number, number] | null {
  const peakPeriods = riskFloorPeriods.filter((p) => p.segment === "PEAK").map((p) => p.settlementPeriod);
  if (peakPeriods.length === 0) return null;
  return [Math.min(...peakPeriods), Math.max(...peakPeriods)];
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartPoint }> }) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  const { settlementPeriod, forecastMw, actualMw, sourcePublishTime } = point;
  const startLabel = periodToTimeLabel(settlementPeriod);
  const endLabel = periodToTimeLabel(settlementPeriod + 1);
  const error = forecastMw !== null && actualMw !== null ? forecastMw - actualMw : null;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs shadow-xl">
      <div className="mb-1 font-mono font-semibold text-slate-200">
        SP {settlementPeriod} ({startLabel}-{endLabel})
      </div>
      {actualMw !== null && (
        <div className="text-emerald-400">Actual: {Math.round(actualMw).toLocaleString()} MW</div>
      )}
      {forecastMw !== null && (
        <div className="text-sky-400">Forecast: {Math.round(forecastMw).toLocaleString()} MW</div>
      )}
      {error !== null && (
        <div className={error >= 0 ? "text-rose-400" : "text-cyan-400"}>
          Error: {error >= 0 ? "+" : ""}
          {Math.round(error).toLocaleString()} MW ({error >= 0 ? "Short" : "Long"})
        </div>
      )}
      {sourcePublishTime && (
        <div className="mt-1.5 border-t border-slate-800 pt-1.5 text-slate-500">
          Vintage: {formatUtc(sourcePublishTime)}
        </div>
      )}
    </div>
  );
}

export function ForecastChart({
  forecastPeriods,
  riskFloorPeriods,
}: {
  forecastPeriods: ForecastDetailPeriod[];
  riskFloorPeriods: RiskFloorPeriod[];
}) {
  const data = buildChartData(forecastPeriods, riskFloorPeriods);
  const peakWindow = derivePeakWindow(riskFloorPeriods);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 16, right: 24, bottom: 8, left: 0 }}>
        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
        <XAxis
          dataKey="settlementPeriod"
          type="number"
          domain={[1, 48]}
          ticks={[1, 9, 17, 25, 33, 41, 48]}
          tickFormatter={periodToTimeLabel}
          stroke="#475569"
          tick={{ fill: "#94a3b8", fontSize: 11 }}
        />
        <YAxis
          stroke="#475569"
          tick={{ fill: "#94a3b8", fontSize: 11 }}
          tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
          width={40}
        />
        <Tooltip content={<CustomTooltip />} />

        {peakWindow && (
          <ReferenceArea
            x1={peakWindow[0] - 0.5}
            x2={peakWindow[1] + 0.5}
            fill="#F59E0B"
            fillOpacity={0.16}
            stroke="#F59E0B"
            strokeOpacity={0.4}
            strokeWidth={1}
            label={{
              value: "Evening Demand Peak",
              position: "insideTop",
              fill: "#FBBF24",
              fontSize: 11,
              fontWeight: 600,
            }}
          />
        )}

        <Line
          type="monotone"
          dataKey="forecastMw"
          stroke="#38BDF8"
          strokeWidth={3}
          dot={false}
          name="Forecast (D-1)"
          isAnimationActive
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="actualMw"
          stroke="#34D399"
          strokeWidth={3}
          dot={false}
          name="Actual"
          isAnimationActive
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="floorMw"
          stroke="#F59E0B"
          strokeWidth={2}
          strokeDasharray="6 4"
          dot={false}
          name="P90 Conservative Floor"
          isAnimationActive
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
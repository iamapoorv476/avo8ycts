import { Wind, ShieldCheck } from "lucide-react";

interface HeaderProps {
  date: string;
  onDateChange: (date: string) => void;
  cutoffApplied: string | null;
}


export function Header({ date, onDateChange, cutoffApplied }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-4">
      <div className="flex items-center gap-2">
        <Wind className="h-5 w-5 text-sky-400" />
        <h1 className="text-sm font-bold uppercase tracking-wide text-slate-100">
          GB Wind Desk <span className="text-slate-500">|</span>{" "}
          <span className="text-slate-400">Day-Ahead Decision Portal</span>
        </h1>
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900/80 px-3 py-1.5">
          <span className="text-xs text-slate-500">Date</span>
          <input
            type="date"
            value={date}
            min="2026-01-01"
            max="2026-01-31"
            onChange={(e) => onDateChange(e.target.value)}
            className="bg-transparent font-mono text-sm text-slate-100 outline-none [color-scheme:dark]"
          />
        </label>

        {cutoffApplied && (
          <div
            className="flex items-center gap-2 rounded-md border border-emerald-900 bg-emerald-950/40 px-3 py-1.5"
            title="This date's decision-time forecast only used WINDFOR vintages published before this timestamp -- no lookahead."
          >
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span className="font-mono text-xs text-emerald-300">
              Cutoff: {cutoffApplied.slice(0, 16).replace("T", " ")} UTC
            </span>
          </div>
        )}
      </div>
    </header>
  );
}
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface MetricCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  sublabel: string;
  badge?: ReactNode;
}

export function MetricCard({ icon: Icon, label, value, sublabel, badge }: MetricCardProps) {
  return (
    <div className="flex flex-1 flex-col gap-1 rounded-lg border border-slate-800 bg-slate-900/80 p-4">
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="font-mono text-3xl font-bold text-slate-100">{value}</div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">{sublabel}</span>
        {badge}
      </div>
    </div>
  );
}
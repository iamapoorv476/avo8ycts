import { Loader2 } from "lucide-react";

export function LoadingState() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-slate-950 text-slate-400">
      <Loader2 className="mr-3 h-6 w-6 animate-spin text-sky-400" />
      <span className="font-mono text-sm">Loading forecast data...</span>
    </div>
  );
}
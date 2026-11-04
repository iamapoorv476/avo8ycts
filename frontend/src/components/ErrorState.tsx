import { AlertTriangle } from "lucide-react";

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-slate-950 px-6">
      <div className="max-w-md rounded-lg border border-rose-900 bg-rose-950/40 p-6 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-rose-500" />
        <p className="font-mono text-sm text-rose-300">{message}</p>
        <p className="mt-2 text-xs text-slate-500">
          Likely outside the ingested January 2026 scope, or the backend isn't running.
        </p>
      </div>
    </div>
  );
}
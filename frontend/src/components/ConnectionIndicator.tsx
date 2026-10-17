import type { ConnectionStatus } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";

const statusConfig: Record<ConnectionStatus, { label: string; dotClass: string }> = {
  disconnected: { label: "Disconnected", dotClass: "bg-muted-foreground" },
  connecting: { label: "Connecting…", dotClass: "bg-amber-400 animate-pulse" },
  connected: { label: "Connected", dotClass: "bg-emerald-400" },
  error: { label: "Connection failed", dotClass: "bg-destructive" },
};

/** Shows whether the voice connection is up. The connection itself is made automatically. */
export function ConnectionIndicator({ status }: { status: ConnectionStatus }) {
  const { label, dotClass } = statusConfig[status];
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status" aria-live="polite">
      <span className={cn("h-2 w-2 rounded-full", dotClass)} />
      {label}
    </div>
  );
}

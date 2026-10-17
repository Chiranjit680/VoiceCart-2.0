import { useState } from "react";
import { Plug, Unplug, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ConnectionStatus } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";

const statusConfig: Record<ConnectionStatus, { label: string; dotClass: string }> = {
  disconnected: { label: "Disconnected", dotClass: "bg-muted-foreground" },
  connecting: { label: "Connecting…", dotClass: "bg-amber-400 animate-pulse" },
  connected: { label: "Connected", dotClass: "bg-emerald-400" },
  error: { label: "Error", dotClass: "bg-destructive" },
};

interface ConnectionPanelProps {
  status: ConnectionStatus;
  onConnect: (url: string) => void;
  onDisconnect: () => void;
}

export function ConnectionPanel({ status, onConnect, onDisconnect }: ConnectionPanelProps) {
  const [url, setUrl] = useState("ws://localhost:8003/ws");
  const isConnected = status === "connected";
  const { label, dotClass } = statusConfig[status];

  return (
    <div className="flex flex-col gap-3 w-full max-w-md">
      <div className="flex items-center gap-2">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="ws://your-server/ws"
          disabled={isConnected}
          className="font-mono text-sm bg-card border-border"
        />
        <Button
          size="icon"
          variant={isConnected ? "destructive" : "default"}
          onClick={() => (isConnected ? onDisconnect() : onConnect(url))}
          disabled={status === "connecting"}
        >
          {status === "connecting" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : isConnected ? (
            <Unplug className="h-4 w-4" />
          ) : (
            <Plug className="h-4 w-4" />
          )}
        </Button>
      </div>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className={cn("h-2 w-2 rounded-full", dotClass)} />
        {label}
      </div>
    </div>
  );
}

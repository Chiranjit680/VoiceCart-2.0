import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface LogEntry {
  id: number;
  time: string;
  message: string;
}

export function ActivityLog({ entries }: { entries: LogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  return (
    <ScrollArea className="h-48 w-full max-w-md rounded-lg border border-border bg-card p-3">
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-6">No activity yet</p>
      ) : (
        <div className="space-y-1 font-mono text-xs">
          {entries.map((e) => (
            <div key={e.id} className="flex gap-2">
              <span className="text-muted-foreground shrink-0">{e.time}</span>
              <span className="text-foreground">{e.message}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </ScrollArea>
  );
}

import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageSquare } from "lucide-react";

export interface Message {
  id: number;
  time: string;
  text: string;
}

export function MessageBox({ messages }: { messages: Message[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div className="w-full max-w-md">
      <div className="flex items-center gap-2 mb-2 text-sm text-muted-foreground">
        <MessageSquare className="h-4 w-4" />
        <span>Backend Messages</span>
      </div>
      <ScrollArea className="h-48 w-full rounded-lg border border-border bg-card p-3">
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">No messages yet</p>
        ) : (
          <div className="space-y-2 text-sm">
            {messages.map((m) => (
              <div key={m.id} className="flex gap-2">
                <span className="text-muted-foreground shrink-0 font-mono text-xs">{m.time}</span>
                <span className="text-foreground">{m.text}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

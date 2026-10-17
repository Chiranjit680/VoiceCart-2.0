import { useEffect, useRef } from "react";
import { Mic } from "lucide-react";
import type { ProductCardData } from "@/lib/api";
import { ProductCardRow } from "@/components/ProductCard";
import { cn } from "@/lib/utils";

export type ConversationItem =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; products: ProductCardData[] }
  | { id: number; role: "notice"; text: string };

/** An item before it gets its id (Omit would collapse the union, so distribute it over each member). */
export type NewConversationItem = ConversationItem extends infer T ? (T extends { id: number } ? Omit<T, "id"> : never) : never;

interface ConversationProps {
  items: ConversationItem[];
  /** The assistant is working on the latest request. */
  pending?: boolean;
}

function Bubble({ item }: { item: ConversationItem }) {
  if (item.role === "notice") {
    return <p className="mx-auto max-w-md text-center text-xs text-muted-foreground">{item.text}</p>;
  }

  const fromUser = item.role === "user";
  return (
    <div className={cn("flex flex-col gap-2", fromUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          fromUser
            ? "rounded-br-md bg-primary text-primary-foreground"
            : "rounded-bl-md border border-border bg-card text-foreground"
        )}
      >
        {item.text}
      </div>
      {item.role === "assistant" && item.products.length > 0 ? (
        <div className="w-full max-w-full">
          <ProductCardRow products={item.products} />
        </div>
      ) : null}
    </div>
  );
}

function Typing() {
  return (
    <div className="flex items-start" role="status" aria-label="The assistant is thinking">
      <div className="flex gap-1 rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export function Conversation({ items, pending = false }: ConversationProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [items.length, pending]);

  if (items.length === 0 && !pending) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center text-muted-foreground">
        <Mic className="h-10 w-10" aria-hidden />
        <p className="text-lg font-medium text-foreground">What would you like to buy?</p>
        <p className="max-w-sm text-sm">
          Switch on hands-free or press the microphone, then say something like “do you have Amul butter?” or
          “add two to my cart”.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6" aria-live="polite" aria-label="Conversation">
      {items.map((item) => (
        <Bubble key={item.id} item={item} />
      ))}
      {pending ? <Typing /> : null}
      <div ref={bottomRef} />
    </div>
  );
}

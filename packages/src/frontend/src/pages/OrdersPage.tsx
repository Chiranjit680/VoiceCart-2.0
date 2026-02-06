import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ClipboardList } from "lucide-react";

export default function OrdersPage() {
  const { data: orders, isLoading } = useQuery({ queryKey: ["orders"], queryFn: api.getOrders });

  return (
    <div className="p-6 lg:p-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-foreground mb-2">Orders</h1>
      <p className="text-muted-foreground mb-8">Your order history</p>

      {isLoading ? (
        <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-lg bg-card" />)}</div>
      ) : !orders?.length ? (
        <div className="flex flex-col items-center py-20 text-muted-foreground">
          <ClipboardList className="h-12 w-12 mb-3" />
          <p>No orders yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {orders.map((o: any) => (
            <div key={o._id || o.id} className="rounded-lg border border-border bg-card p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-foreground">Order #{(o._id || o.id)?.slice(-8)}</span>
                <span className={`rounded-full px-3 py-0.5 text-xs font-medium ${
                  o.status === "completed" ? "bg-primary/10 text-primary"
                  : o.status === "cancelled" ? "bg-destructive/10 text-destructive"
                  : "bg-accent text-accent-foreground"
                }`}>
                  {o.status || "pending"}
                </span>
              </div>
              {o.total && <p className="text-lg font-bold text-primary">${o.total}</p>}
              {o.created_at && <p className="text-xs text-muted-foreground">{new Date(o.created_at).toLocaleDateString()}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

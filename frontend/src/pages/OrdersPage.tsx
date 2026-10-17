import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { api, ApiError, type Order } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate, formatPrice } from "@/lib/format";
import { ProductImage } from "@/components/ProductImage";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function statusClass(status: string): string {
  switch (status.toLowerCase()) {
    case "delivered":
    case "completed":
      return "bg-primary/10 text-primary";
    case "cancelled":
    case "canceled":
      return "bg-destructive/10 text-destructive";
    case "shipped":
      return "bg-accent text-accent-foreground";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function OrderCard({ order }: { order: Order }) {
  return (
    <article className="overflow-hidden rounded-xl border border-border bg-card" aria-label={`Order ${order.id}`}>
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Order #{order.id}</h2>
          <p className="text-xs text-muted-foreground">{formatDate(order.created_at)}</p>
        </div>
        <span className={cn("rounded-full px-3 py-0.5 text-xs font-medium capitalize", statusClass(order.status))}>
          {order.status}
        </span>
      </header>

      <ul className="divide-y divide-border">
        {order.items.map((item) => {
          const name = item.product?.name ?? `Product #${item.product_id}`;
          return (
            <li key={item.product_id} className="flex items-center gap-3 px-4 py-3">
              <ProductImage
                productId={item.product_id}
                name={name}
                hasImage={item.product?.has_image ?? false}
                className="h-14 w-14 shrink-0 rounded-lg"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{name}</p>
                <p className="text-xs text-muted-foreground">
                  {item.quantity} × {formatPrice(item.price)}
                </p>
              </div>
              <span className="text-sm font-medium text-foreground">{formatPrice(item.quantity * item.price)}</span>
            </li>
          );
        })}
      </ul>

      <footer className="flex items-end justify-between gap-4 border-t border-border bg-muted/30 px-4 py-3">
        <p className="min-w-0 truncate text-xs text-muted-foreground">Deliver to {order.address}</p>
        <p className="shrink-0 text-base font-bold text-primary">{formatPrice(order.total_amount)}</p>
      </footer>
    </article>
  );
}

export default function OrdersPage() {
  const { logout } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["orders"],
    queryFn: api.getOrders,
    retry: (failures, err) => !(err instanceof ApiError && err.status === 401) && failures < 2,
  });

  // An expired login: sign out, which sends the user to the sign-in page.
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) logout();
  }, [error, logout]);

  const orders = [...(data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <div className="mx-auto max-w-3xl p-6 lg:p-8">
      <h1 className="mb-1 text-3xl font-bold text-foreground">Orders</h1>
      <p className="mb-8 text-muted-foreground">Your order history</p>

      {isLoading ? (
        <div className="space-y-3" aria-busy="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-xl bg-card" />
          ))}
        </div>
      ) : error ? (
        <div role="alert" className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
          <p>We couldn’t load your orders.</p>
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : orders.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-center text-muted-foreground">
          <ClipboardList className="mb-3 h-12 w-12" aria-hidden />
          <p className="font-medium text-foreground">No orders yet</p>
          <p className="mt-1 text-sm">
            Ask the assistant to check out your cart on the{" "}
            <Link to="/" className="underline underline-offset-2 hover:text-foreground">
              Voice page
            </Link>
            .
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <OrderCard key={order.id} order={order} />
          ))}
        </div>
      )}
    </div>
  );
}

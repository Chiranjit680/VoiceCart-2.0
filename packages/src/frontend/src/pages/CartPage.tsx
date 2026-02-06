import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Trash2, ShoppingCart, Minus, Plus } from "lucide-react";
import { toast } from "sonner";

export default function CartPage() {
  const qc = useQueryClient();
  const { data: cart, isLoading } = useQuery({ queryKey: ["cart"], queryFn: api.getCart });
  const { data: cost } = useQuery({ queryKey: ["cart-cost"], queryFn: api.getCartCost });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cart"] });
    qc.invalidateQueries({ queryKey: ["cart-cost"] });
  };

  const remove = async (pid: string) => {
    try {
      await api.removeFromCart(pid);
      toast.success("Removed");
      refresh();
    } catch (err: any) { toast.error(err.message); }
  };

  const update = async (pid: string, qty: number) => {
    if (qty < 1) return remove(pid);
    try {
      await api.updateCartItem(pid, { quantity: qty });
      refresh();
    } catch (err: any) { toast.error(err.message); }
  };

  const checkout = async () => {
    try {
      await api.checkout();
      toast.success("Checkout successful!");
      refresh();
    } catch (err: any) { toast.error(err.message); }
  };

  const clear = async () => {
    try {
      await api.clearCart();
      toast.success("Cart cleared");
      refresh();
    } catch (err: any) { toast.error(err.message); }
  };

  const items: any[] = Array.isArray(cart) ? cart : cart?.items ?? [];

  return (
    <div className="p-6 lg:p-8 max-w-2xl">
      <h1 className="text-3xl font-bold text-foreground mb-2">Cart</h1>
      <p className="text-muted-foreground mb-8">Review your items</p>

      {isLoading ? (
        <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-lg bg-card" />)}</div>
      ) : !items.length ? (
        <div className="flex flex-col items-center py-20 text-muted-foreground">
          <ShoppingCart className="h-12 w-12 mb-3" />
          <p>Your cart is empty</p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {items.map((item: any) => (
              <div key={item.product_id || item.id} className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
                <div className="flex-1">
                  <h3 className="font-medium text-foreground">{item.name || item.product_name || `Product`}</h3>
                  <p className="text-sm text-muted-foreground">
                    ${item.price ?? "—"} × {item.quantity}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="icon" variant="ghost" onClick={() => update(item.product_id || item.id, (item.quantity || 1) - 1)}>
                    <Minus className="h-4 w-4" />
                  </Button>
                  <span className="w-8 text-center text-sm font-medium text-foreground">{item.quantity}</span>
                  <Button size="icon" variant="ghost" onClick={() => update(item.product_id || item.id, (item.quantity || 1) + 1)}>
                    <Plus className="h-4 w-4" />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => remove(item.product_id || item.id)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-lg border border-border bg-card p-4 space-y-4">
            {cost && (
              <div className="flex justify-between text-lg font-bold text-foreground">
                <span>Total</span>
                <span className="text-primary">${cost.total ?? cost.cost ?? "—"}</span>
              </div>
            )}
            <div className="flex gap-3">
              <Button onClick={checkout} className="flex-1">Checkout</Button>
              <Button variant="destructive" onClick={clear}>Clear Cart</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";
import { Package, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function ProductsPage() {
  const { data: products, isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: api.getProducts,
  });
  const { isAuthenticated } = useAuth();

  const handleAddToCart = async (productId: string) => {
    if (!isAuthenticated) {
      toast.error("Please log in to add items to cart");
      return;
    }
    try {
      await api.addToCart({ product_id: productId, quantity: 1 });
      toast.success("Added to cart!");
    } catch (err: any) {
      toast.error(err.message);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground">Products</h1>
        <p className="mt-1 text-muted-foreground">Browse our collection</p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-xl bg-card border border-border" />
          ))}
        </div>
      ) : !products?.length ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Package className="h-12 w-12 mb-3" />
          <p>No products found</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {products.map((p: any) => (
            <div
              key={p._id || p.id}
              className="group relative rounded-xl border border-border bg-card overflow-hidden transition-all hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5"
            >
              <Link to={`/product/${p._id || p.id}`} className="block p-5">
                <div className="mb-3 flex h-32 items-center justify-center rounded-lg bg-muted">
                  {p.image ? (
                    <img src={p.image} alt={p.name} className="h-full w-full object-cover rounded-lg" />
                  ) : (
                    <Package className="h-10 w-10 text-muted-foreground" />
                  )}
                </div>
                <h3 className="font-semibold text-foreground truncate">{p.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{p.description}</p>
                <p className="mt-2 text-lg font-bold text-primary">
                  ${typeof p.price === "number" ? p.price.toFixed(2) : p.price}
                </p>
              </Link>
              <div className="px-5 pb-4">
                <Button
                  size="sm"
                  className="w-full gap-2"
                  onClick={() => handleAddToCart(p._id || p.id)}
                >
                  <Plus className="h-4 w-4" /> Add to Cart
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

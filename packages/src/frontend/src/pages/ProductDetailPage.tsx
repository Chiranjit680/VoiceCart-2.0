import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Package, Plus, Star } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { isAuthenticated } = useAuth();
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  const { data: product, isLoading } = useQuery({
    queryKey: ["product", id],
    queryFn: () => api.getProduct(id!),
    enabled: !!id,
  });

  const { data: reviews, refetch: refetchReviews } = useQuery({
    queryKey: ["reviews", id],
    queryFn: () => api.getProductReviews(id!),
    enabled: !!id,
  });

  const handleAddToCart = async () => {
    if (!isAuthenticated) return toast.error("Please log in first");
    try {
      await api.addToCart({ product_id: id!, quantity: 1 });
      toast.success("Added to cart!");
    } catch (err: any) {
      toast.error(err.message);
    }
  };

  const handleReview = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createReview({ product_id: id!, rating, comment });
      toast.success("Review submitted!");
      setComment("");
      refetchReviews();
    } catch (err: any) {
      toast.error(err.message);
    }
  };

  if (isLoading) return <div className="p-8"><div className="h-64 animate-pulse rounded-xl bg-card" /></div>;

  if (!product) return <div className="p-8 text-center text-muted-foreground">Product not found</div>;

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      <div className="grid gap-8 md:grid-cols-2">
        <div className="flex items-center justify-center rounded-xl bg-card border border-border p-8">
          {product.image ? (
            <img src={product.image} alt={product.name} className="max-h-72 object-contain rounded-lg" />
          ) : (
            <Package className="h-24 w-24 text-muted-foreground" />
          )}
        </div>
        <div className="space-y-4">
          <h1 className="text-3xl font-bold text-foreground">{product.name}</h1>
          <p className="text-muted-foreground">{product.description}</p>
          <p className="text-3xl font-bold text-primary">
            ${typeof product.price === "number" ? product.price.toFixed(2) : product.price}
          </p>
          {product.category && (
            <span className="inline-block rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground">
              {product.category}
            </span>
          )}
          <Button onClick={handleAddToCart} className="w-full gap-2" size="lg">
            <Plus className="h-5 w-5" /> Add to Cart
          </Button>
        </div>
      </div>

      {/* Reviews */}
      <div className="mt-12 space-y-6">
        <h2 className="text-xl font-bold text-foreground">Reviews</h2>
        {reviews?.length ? (
          <div className="space-y-3">
            {reviews.map((r: any, i: number) => (
              <div key={i} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-2">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <Star key={j} className={`h-4 w-4 ${j < r.rating ? "text-primary fill-primary" : "text-muted-foreground"}`} />
                  ))}
                </div>
                <p className="text-sm text-foreground">{r.comment}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">No reviews yet</p>
        )}

        {isAuthenticated && (
          <form onSubmit={handleReview} className="space-y-3 rounded-lg border border-border bg-card p-4">
            <h3 className="text-sm font-medium text-foreground">Write a Review</h3>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Rating:</span>
              <Input type="number" min={1} max={5} value={rating} onChange={(e) => setRating(Number(e.target.value))} className="w-20 bg-muted border-border" />
            </div>
            <Textarea placeholder="Your review…" value={comment} onChange={(e) => setComment(e.target.value)} className="bg-muted border-border" />
            <Button type="submit" size="sm">Submit Review</Button>
          </form>
        )}
      </div>
    </div>
  );
}

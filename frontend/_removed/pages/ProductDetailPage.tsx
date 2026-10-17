import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Package, Plus, Star, ShoppingCart, Leaf, Flame, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

/* ── Static featured / suggested products ── */
const STATIC_PRODUCTS = [
  {
    id: "s1",
    name: "Organic Avocados (3 pk)",
    description: "Ripe Hass avocados, ready to eat. Sourced from sustainable farms.",
    price: 4.99,
    image: "https://images.unsplash.com/photo-1523049673857-eb18f1d7b578?w=300&h=300&fit=crop",
    category: "Fruits",
    badge: "Organic",
    badgeIcon: <Leaf className="h-3 w-3" />,
    rating: 4.5,
    reviews: 128,
  },
  {
    id: "s2",
    name: "Sourdough Bread Loaf",
    description: "Artisan slow-fermented sourdough with a crispy crust and soft interior.",
    price: 6.49,
    image: "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=300&h=300&fit=crop",
    category: "Bakery",
    badge: "Fresh Daily",
    badgeIcon: <Sparkles className="h-3 w-3" />,
    rating: 4.8,
    reviews: 256,
  },
  {
    id: "s3",
    name: "Free-Range Eggs (12 ct)",
    description: "Farm-fresh free-range eggs. High protein, rich golden yolks.",
    price: 5.29,
    image: "https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=300&h=300&fit=crop",
    category: "Dairy & Eggs",
    badge: "Best Seller",
    badgeIcon: <Flame className="h-3 w-3" />,
    rating: 4.7,
    reviews: 342,
  },
  {
    id: "s4",
    name: "Greek Yogurt – Vanilla",
    description: "Thick, creamy Greek yogurt with real vanilla bean. High protein, low sugar.",
    price: 3.79,
    image: "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=300&h=300&fit=crop",
    category: "Dairy & Eggs",
    badge: "Popular",
    badgeIcon: <Sparkles className="h-3 w-3" />,
    rating: 4.4,
    reviews: 189,
  },
  {
    id: "s5",
    name: "Atlantic Salmon Fillet",
    description: "Wild-caught Atlantic salmon, rich in Omega-3. Skin-on, boneless.",
    price: 12.99,
    image: "https://images.unsplash.com/photo-1599084993091-1cb5c0721cc6?w=300&h=300&fit=crop",
    category: "Seafood",
    badge: "Premium",
    badgeIcon: <Star className="h-3 w-3" />,
    rating: 4.9,
    reviews: 97,
  },
  {
    id: "s6",
    name: "Mixed Nuts – Roasted & Salted",
    description: "Almonds, cashews, pecans & walnuts. Lightly roasted with sea salt.",
    price: 8.49,
    image: "https://images.unsplash.com/photo-1599599810769-bcde5a160d32?w=300&h=300&fit=crop",
    category: "Snacks",
    badge: "Vegan",
    badgeIcon: <Leaf className="h-3 w-3" />,
    rating: 4.6,
    reviews: 214,
  },
];

function MiniStars({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={`h-3.5 w-3.5 ${i < Math.round(rating) ? "text-amber-400 fill-amber-400" : "text-muted-foreground/40"}`}
        />
      ))}
    </div>
  );
}

function StaticProductCard({ item }: { item: (typeof STATIC_PRODUCTS)[number] }) {
  const handleAdd = async () => {
    toast.success(`${item.name} added to cart!`);
  };

  return (
    <Card className="group relative flex flex-col overflow-hidden transition-all hover:shadow-md hover:border-primary/30">
      {/* Badge */}
      <div className="absolute top-3 left-3 z-10">
        <Badge variant="secondary" className="gap-1 bg-background/80 backdrop-blur-sm shadow-sm text-xs">
          {item.badgeIcon}
          {item.badge}
        </Badge>
      </div>

      {/* Image */}
      <div className="relative aspect-square overflow-hidden bg-muted">
        <img
          src={item.image}
          alt={item.name}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      </div>

      {/* Content */}
      <CardContent className="flex flex-1 flex-col gap-2 p-4">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {item.category}
        </span>
        <h3 className="text-sm font-semibold leading-snug text-foreground line-clamp-2">
          {item.name}
        </h3>
        <p className="text-xs text-muted-foreground line-clamp-2">{item.description}</p>
        <div className="mt-auto flex items-center gap-2 pt-1">
          <MiniStars rating={item.rating} />
          <span className="text-xs text-muted-foreground">({item.reviews})</span>
        </div>
      </CardContent>

      {/* Footer */}
      <CardFooter className="flex items-center justify-between border-t border-border px-4 py-3">
        <span className="text-lg font-bold text-primary">${item.price.toFixed(2)}</span>
        <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={handleAdd}>
          <ShoppingCart className="h-3.5 w-3.5" /> Add
        </Button>
      </CardFooter>
    </Card>
  );
}

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

      {/* ── You May Also Like ── */}
      <div className="mt-16 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-foreground">You May Also Like</h2>
          <span className="text-xs text-muted-foreground">Hand-picked for you</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {STATIC_PRODUCTS.map((item) => (
            <StaticProductCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";
import { Package, Plus, Star, ShoppingCart, Cpu, Smartphone, Laptop, Headphones, Watch, Tv, Gamepad2, Camera, Speaker, Tablet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

/* ── Static product catalog ── */
const STATIC_PRODUCTS = [
  {
    id: "st-1",
    name: 'MacBook Pro 16" M3 Max',
    description: "Apple M3 Max chip, 36GB RAM, 1TB SSD. Liquid Retina XDR display.",
    price: 2499.0,
    image: "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop",
    category: "Laptops",
    icon: <Laptop className="h-3.5 w-3.5" />,
    badge: "Best Seller",
    rating: 4.9,
    reviews: 1247,
    stock: 15,
  },
  {
    id: "st-2",
    name: "iPhone 16 Pro Max",
    description: "A18 Pro chip, 256GB, Titanium. 48MP camera system with 5× optical zoom.",
    price: 1199.0,
    image: "https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=400&h=400&fit=crop",
    category: "Smartphones",
    icon: <Smartphone className="h-3.5 w-3.5" />,
    badge: "New Arrival",
    rating: 4.8,
    reviews: 2341,
    stock: 42,
  },
  {
    id: "st-3",
    name: "Samsung Galaxy S25 Ultra",
    description: "Snapdragon 8 Elite, 12GB RAM, 512GB. S Pen included, 200MP camera.",
    price: 1299.99,
    image: "https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?w=400&h=400&fit=crop",
    category: "Smartphones",
    icon: <Smartphone className="h-3.5 w-3.5" />,
    badge: "Popular",
    rating: 4.7,
    reviews: 1893,
    stock: 38,
  },
  {
    id: "st-4",
    name: "Sony WH-1000XM5",
    description: "Industry-leading noise cancellation. 30-hour battery, Hi-Res Audio.",
    price: 349.99,
    image: "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400&h=400&fit=crop",
    category: "Audio",
    icon: <Headphones className="h-3.5 w-3.5" />,
    badge: "Top Rated",
    rating: 4.8,
    reviews: 3456,
    stock: 67,
  },
  {
    id: "st-5",
    name: "Dell XPS 15 (2025)",
    description: "Intel Core Ultra 9, 32GB RAM, 1TB SSD. 15.6\" 3.5K OLED touch display.",
    price: 1899.0,
    image: "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop",
    category: "Laptops",
    icon: <Laptop className="h-3.5 w-3.5" />,
    badge: "Editor's Pick",
    rating: 4.6,
    reviews: 876,
    stock: 22,
  },
  {
    id: "st-6",
    name: "Apple Watch Ultra 3",
    description: "49mm titanium case, precision GPS, 72-hour battery life. Dive-ready to 100m.",
    price: 799.0,
    image: "https://images.unsplash.com/photo-1434493789847-2f02dc6ca35d?w=400&h=400&fit=crop",
    category: "Wearables",
    icon: <Watch className="h-3.5 w-3.5" />,
    badge: "Premium",
    rating: 4.7,
    reviews: 654,
    stock: 19,
  },
  {
    id: "st-7",
    name: 'LG C4 65" OLED TV',
    description: "4K 120Hz OLED evo, Dolby Vision & Atmos, webOS 24. Perfect for gaming.",
    price: 1796.99,
    image: "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=400&h=400&fit=crop",
    category: "TVs",
    icon: <Tv className="h-3.5 w-3.5" />,
    badge: "Deal",
    rating: 4.8,
    reviews: 1102,
    stock: 11,
  },
  {
    id: "st-8",
    name: "PlayStation 5 Pro",
    description: "Enhanced GPU, 2TB SSD, ray-tracing. 8K output support, DualSense controller.",
    price: 699.99,
    image: "https://images.unsplash.com/photo-1606144042614-b2417e99c4e3?w=400&h=400&fit=crop",
    category: "Gaming",
    icon: <Gamepad2 className="h-3.5 w-3.5" />,
    badge: "Hot",
    rating: 4.9,
    reviews: 4521,
    stock: 8,
  },
  {
    id: "st-9",
    name: "Sony Alpha A7 IV",
    description: "33MP full-frame mirrorless, 4K 60fps, real-time Eye AF. Kit with 28-70mm lens.",
    price: 2498.0,
    image: "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=400&h=400&fit=crop",
    category: "Cameras",
    icon: <Camera className="h-3.5 w-3.5" />,
    badge: "Pro",
    rating: 4.8,
    reviews: 723,
    stock: 14,
  },
  {
    id: "st-10",
    name: "iPad Pro 13\" M4",
    description: "M4 chip, Ultra Retina XDR OLED, 256GB. Thinnest Apple product ever.",
    price: 1299.0,
    image: "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop",
    category: "Tablets",
    icon: <Tablet className="h-3.5 w-3.5" />,
    badge: "New",
    rating: 4.7,
    reviews: 1567,
    stock: 31,
  },
  {
    id: "st-11",
    name: "Sonos Era 300",
    description: "Spatial audio speaker with Dolby Atmos. WiFi 6, Bluetooth 5.0, AirPlay 2.",
    price: 449.0,
    image: "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop",
    category: "Audio",
    icon: <Speaker className="h-3.5 w-3.5" />,
    badge: "Trending",
    rating: 4.5,
    reviews: 398,
    stock: 45,
  },
  {
    id: "st-12",
    name: "ASUS ROG Strix G16",
    description: "RTX 4070, Intel i9-14900HX, 16GB DDR5, 1TB SSD. 16\" 240Hz display.",
    price: 1649.99,
    image: "https://images.unsplash.com/photo-1625842268584-8f3296236761?w=400&h=400&fit=crop",
    category: "Gaming",
    icon: <Gamepad2 className="h-3.5 w-3.5" />,
    badge: "Gaming Pick",
    rating: 4.6,
    reviews: 542,
    stock: 17,
  },
];

function MiniStars({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={`h-3 w-3 ${i < Math.round(rating) ? "text-amber-400 fill-amber-400" : "text-muted-foreground/30"}`}
        />
      ))}
    </div>
  );
}

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

      {/* ── Static Product Cards ── */}
      <div className="mt-14">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Featured Electronics</h2>
            <p className="mt-1 text-sm text-muted-foreground">Top picks across laptops, phones, audio & more</p>
          </div>
          <Badge variant="outline" className="gap-1.5 text-xs">
            <Cpu className="h-3 w-3" /> {STATIC_PRODUCTS.length} items
          </Badge>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {STATIC_PRODUCTS.map((item) => (
            <Card
              key={item.id}
              className="group relative flex flex-col overflow-hidden transition-all hover:shadow-lg hover:shadow-primary/5 hover:border-primary/30"
            >
              {/* Badge */}
              <div className="absolute top-3 left-3 z-10">
                <Badge variant="secondary" className="gap-1 bg-background/80 backdrop-blur-sm shadow-sm text-[11px]">
                  {item.icon}
                  {item.badge}
                </Badge>
              </div>

              {/* Stock indicator */}
              {item.stock <= 15 && (
                <div className="absolute top-3 right-3 z-10">
                  <Badge variant="destructive" className="text-[10px]">
                    Only {item.stock} left
                  </Badge>
                </div>
              )}

              {/* Image */}
              <div className="relative aspect-square overflow-hidden bg-muted">
                <img
                  src={item.image}
                  alt={item.name}
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                />
              </div>

              {/* Content */}
              <CardContent className="flex flex-1 flex-col gap-1.5 p-4">
                <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {item.category}
                </span>
                <h3 className="text-sm font-semibold leading-snug text-foreground line-clamp-1">
                  {item.name}
                </h3>
                <p className="text-xs text-muted-foreground line-clamp-2">{item.description}</p>
                <div className="mt-auto flex items-center gap-2 pt-2">
                  <MiniStars rating={item.rating} />
                  <span className="text-[11px] text-muted-foreground">
                    {item.rating} ({item.reviews.toLocaleString()})
                  </span>
                </div>
              </CardContent>

              {/* Footer */}
              <CardFooter className="flex items-center justify-between border-t border-border px-4 py-3">
                <span className="text-lg font-bold text-primary">${item.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs"
                  onClick={() => toast.success(`${item.name} added to cart!`)}
                >
                  <ShoppingCart className="h-3.5 w-3.5" /> Add
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

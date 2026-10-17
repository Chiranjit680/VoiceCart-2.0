import { Star } from "lucide-react";
import type { ProductCardData } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { ProductImage } from "@/components/ProductImage";
import { cn } from "@/lib/utils";

function stockLabel(stock: number): { text: string; className: string } | null {
  if (stock <= 0) return { text: "Out of stock", className: "text-destructive" };
  if (stock <= 5) return { text: `Only ${stock} left`, className: "text-amber-600 dark:text-amber-400" };
  return null;
}

/** A product with its photo, as shown in the conversation. */
export function ProductCard({ product, className }: { product: ProductCardData; className?: string }) {
  const stock = stockLabel(product.stock);

  return (
    <article
      aria-label={product.name}
      className={cn(
        "group flex w-44 shrink-0 snap-start flex-col overflow-hidden rounded-xl border border-border/80 bg-card shadow-sm ring-1 ring-transparent transition-all hover:-translate-y-0.5 hover:border-primary/50 hover:ring-primary/10 hover:shadow-md",
        className
      )}
    >
      <div className="relative">
        <ProductImage
          productId={product.id}
          name={product.name}
          hasImage={product.has_image}
          className="aspect-square w-full"
        />
        {product.quantity ? (
          <span className="absolute right-2 top-2 rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-primary-foreground shadow">
            ×{product.quantity}
          </span>
        ) : null}
      </div>

      <div className="flex flex-1 flex-col gap-1 p-3">
        <h3 className="line-clamp-2 text-sm font-medium leading-snug text-foreground">{product.name}</h3>
        {product.brand_name ? <p className="truncate text-xs text-muted-foreground">{product.brand_name}</p> : null}

        <div className="mt-auto flex items-end justify-between pt-2">
          <span className="text-base font-bold text-primary">{formatPrice(product.price)}</span>
          {product.num_reviews > 0 ? (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" title={`${product.num_reviews} reviews`}>
              <Star className="h-3 w-3 fill-amber-400 text-amber-400" aria-hidden />
              {product.avg_rating.toFixed(1)}
            </span>
          ) : null}
        </div>
        {stock ? <p className={cn("text-xs font-medium", stock.className)}>{stock.text}</p> : null}
      </div>
    </article>
  );
}

/** Cards side by side; scrolls sideways when they do not fit. */
export function ProductCardRow({ products }: { products: ProductCardData[] }) {
  if (products.length === 0) return null;
  return (
    <div className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2" role="list" aria-label="Products">
      {products.map((product) => (
        <div role="listitem" key={product.id} className="contents">
          <ProductCard product={product} />
        </div>
      ))}
    </div>
  );
}

import { useState } from "react";
import { ImageOff } from "lucide-react";
import { imageUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ProductImageProps {
  productId: number;
  name: string;
  hasImage: boolean;
  className?: string;
}

/** A product's photo, or a neutral placeholder when it has none or the photo fails to load. */
export function ProductImage({ productId, name, hasImage, className }: ProductImageProps) {
  const [failed, setFailed] = useState(false);

  if (!hasImage || failed) {
    return (
      <div
        role="img"
        aria-label={`${name} (no photo)`}
        className={cn("flex items-center justify-center bg-muted text-muted-foreground", className)}
      >
        <ImageOff className="h-1/4 w-1/4 max-h-8 max-w-8" aria-hidden />
      </div>
    );
  }

  return (
    <img
      src={imageUrl(productId)}
      alt={name}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={cn("bg-muted object-cover", className)}
    />
  );
}

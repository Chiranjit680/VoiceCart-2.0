import { Star } from "lucide-react";

export default function ReviewsPage() {
  return (
    <div className="p-6 lg:p-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-foreground mb-2">My Reviews</h1>
      <p className="text-muted-foreground mb-8">Reviews you've written</p>
      <div className="flex flex-col items-center py-20 text-muted-foreground">
        <Star className="h-12 w-12 mb-3" />
        <p>Your reviews will appear on individual product pages</p>
        <p className="text-sm mt-1">Browse products to leave reviews</p>
      </div>
    </div>
  );
}

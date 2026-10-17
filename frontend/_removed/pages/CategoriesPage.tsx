import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Grid3X3 } from "lucide-react";

export default function CategoriesPage() {
  const { data: categories, isLoading } = useQuery({ queryKey: ["categories"], queryFn: api.getCategories });

  return (
    <div className="p-6 lg:p-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-foreground mb-2">Categories</h1>
      <p className="text-muted-foreground mb-8">Browse by category</p>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-card" />)}</div>
      ) : !categories?.length ? (
        <div className="flex flex-col items-center py-20 text-muted-foreground">
          <Grid3X3 className="h-12 w-12 mb-3" />
          <p>No categories yet</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {categories.map((c: any) => (
            <div key={c._id || c.id || c.name} className="flex items-center justify-center rounded-xl border border-border bg-card p-6 text-center transition-colors hover:border-primary/30 hover:bg-accent">
              <span className="font-medium text-foreground">{c.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

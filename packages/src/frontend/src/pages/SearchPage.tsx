import { useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Package, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);
  const { isAuthenticated } = useAuth();

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await api.searchProducts(query);
      setResults(Array.isArray(res) ? res : []);
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const addToCart = async (pid: string) => {
    if (!isAuthenticated) return toast.error("Please log in first");
    try {
      await api.addToCart({ product_id: pid, quantity: 1 });
      toast.success("Added to cart!");
    } catch (err: any) { toast.error(err.message); }
  };

  return (
    <div className="p-6 lg:p-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-foreground mb-2">Search</h1>
      <p className="text-muted-foreground mb-6">Find products by name or description</p>

      <form onSubmit={handleSearch} className="flex gap-2 mb-8">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search products…"
          className="bg-card border-border"
        />
        <Button type="submit" disabled={loading} className="gap-2">
          <Search className="h-4 w-4" /> Search
        </Button>
      </form>

      {results === null ? null : !results.length ? (
        <p className="text-center text-muted-foreground py-12">No results found</p>
      ) : (
        <div className="space-y-3">
          {results.map((p: any) => (
            <div key={p._id || p.id} className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
              <Link to={`/product/${p._id || p.id}`} className="flex-1">
                <h3 className="font-medium text-foreground">{p.name}</h3>
                <p className="text-sm text-muted-foreground line-clamp-1">{p.description}</p>
              </Link>
              <div className="flex items-center gap-3 ml-4">
                <span className="font-bold text-primary">${p.price}</span>
                <Button size="icon" variant="ghost" onClick={() => addToCart(p._id || p.id)}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PackageSearch, Search } from "lucide-react";
import { api } from "@/lib/api";
import { SORT_LABELS, categoriesOf, filterAndSort, forSale, type SortKey } from "@/lib/catalogue";
import { ProductCard } from "@/components/ProductCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const selectClass =
  "h-10 rounded-md border border-border bg-card px-3 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Everything the store sells, as photo cards. Buying happens by voice; this is for looking around. */
export default function CataloguePage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["catalogue"],
    queryFn: api.getProducts,
    staleTime: 5 * 60 * 1000, // the catalogue rarely changes while someone browses it
  });
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<SortKey>("featured");

  const available = useMemo(() => forSale(data ?? []), [data]);
  const categories = useMemo(() => categoriesOf(available), [available]);
  const shown = useMemo(() => filterAndSort(available, { search, category, sort }), [available, search, category, sort]);

  const filtering = search.trim() !== "" || category !== "";

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">
      <h1 className="mb-1 text-3xl font-bold text-foreground">Catalogue</h1>
      <p className="mb-6 text-muted-foreground">
        Everything in store. To buy something, ask for it on the{" "}
        <Link to="/" className="underline underline-offset-2 hover:text-foreground">
          Voice page
        </Link>
        .
      </p>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or brand"
            aria-label="Search the catalogue"
            className="bg-card pl-9"
          />
        </div>
        {categories.length > 0 ? (
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category" className={selectClass}>
            <option value="">All categories</option>
            {categories.map(({ name, count }) => (
              <option key={name} value={name}>
                {name} ({count})
              </option>
            ))}
          </select>
        ) : null}
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort by" className={selectClass}>
          {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
            <option key={key} value={key}>
              {SORT_LABELS[key]}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" aria-busy="true">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="aspect-[3/4] animate-pulse rounded-xl bg-card" />
          ))}
        </div>
      ) : error ? (
        <div role="alert" className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
          <p>We couldn’t load the catalogue.</p>
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : shown.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-center text-muted-foreground">
          <PackageSearch className="mb-3 h-12 w-12" aria-hidden />
          <p className="font-medium text-foreground">{filtering ? "Nothing matches that" : "The catalogue is empty"}</p>
          {filtering ? (
            <Button
              variant="link"
              onClick={() => {
                setSearch("");
                setCategory("");
              }}
            >
              Clear the search and category
            </Button>
          ) : null}
        </div>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted-foreground" aria-live="polite">
            {filtering ? `${shown.length} of ${available.length} products` : `${available.length} products`}
          </p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {shown.map((product) => (
              <ProductCard key={product.id} product={product} className="w-full" />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

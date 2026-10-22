import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CataloguePage from "./CataloguePage";
import { api, ApiError, type ProductCardData } from "@/lib/api";

const product = (id: number, name: string, extra: Partial<ProductCardData> = {}): ProductCardData => ({
  id, name, brand_name: null, price: 100, avg_rating: 0, num_reviews: 0, stock: 10, has_image: false, for_sale: true, categories: [], ...extra,
});

const PRODUCTS = [
  product(101, "Amul Taaza Toned Milk 1L", { brand_name: "Amul", price: 68, has_image: true, categories: [{ id: 1, name: "Dairy" }] }),
  product(102, "Amul Butter 500g", { brand_name: "Amul", price: 285, has_image: true, categories: [{ id: 1, name: "Dairy" }] }),
  product(103, "India Gate Basmati Rice 5kg", { brand_name: "India Gate", price: 720, has_image: true, categories: [{ id: 2, name: "Staples" }] }),
  product(7, "Plain Notebook", { price: 40 }),
  product(8, "Discontinued Pen", { for_sale: false }),
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CataloguePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const cardNames = () => screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"));

describe("CataloguePage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows every product that is for sale as a card, with its photo where it has one", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue(PRODUCTS);
    renderPage();
    await screen.findAllByRole("article");

    expect(cardNames()).toEqual(["Amul Butter 500g", "Amul Taaza Toned Milk 1L", "India Gate Basmati Rice 5kg", "Plain Notebook"]);
    expect(screen.queryByRole("article", { name: "Discontinued Pen" })).toBeNull(); // not for sale
    expect(screen.getByText("4 products")).toBeInTheDocument();

    const butter = screen.getByRole("article", { name: "Amul Butter 500g" });
    expect((within(butter).getByRole("img", { name: "Amul Butter 500g" }) as HTMLImageElement).src).toMatch(/\/product\/102\/image$/);
    const notebook = screen.getByRole("article", { name: "Plain Notebook" });
    expect(within(notebook).getByRole("img", { name: "Plain Notebook (no photo)" })).toBeInTheDocument();
  });

  it("filters as the shopper types, counts the matches, and can be cleared", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue(PRODUCTS);
    renderPage();
    await screen.findAllByRole("article");

    fireEvent.change(screen.getByLabelText("Search the catalogue"), { target: { value: "amul" } });
    expect(cardNames()).toEqual(["Amul Butter 500g", "Amul Taaza Toned Milk 1L"]);
    expect(screen.getByText("2 of 4 products")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search the catalogue"), { target: { value: "zzz" } });
    expect(screen.getByText("Nothing matches that")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear the search and category" }));
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("offers the categories that exist and filters by the chosen one", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue(PRODUCTS);
    renderPage();
    await screen.findAllByRole("article");

    const category = screen.getByLabelText("Category");
    expect(within(category).getAllByRole("option").map((o) => o.textContent)).toEqual(["All categories", "Dairy (2)", "Staples (1)"]);
    fireEvent.change(category, { target: { value: "Staples" } });
    expect(cardNames()).toEqual(["India Gate Basmati Rice 5kg"]);
  });

  it("hides the category choice when no product has a category", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue([product(7, "Plain Notebook")]);
    renderPage();
    await screen.findAllByRole("article");
    expect(screen.queryByLabelText("Category")).toBeNull();
  });

  it("sorts by price", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue(PRODUCTS);
    renderPage();
    await screen.findAllByRole("article");
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "price-asc" } });
    expect(cardNames()).toEqual(["Plain Notebook", "Amul Taaza Toned Milk 1L", "Amul Butter 500g", "India Gate Basmati Rice 5kg"]);
  });

  it("says so when the store has nothing", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("The catalogue is empty")).toBeInTheDocument();
  });

  it("offers a retry when loading fails", async () => {
    const getProducts = vi.spyOn(api, "getProducts").mockRejectedValue(new ApiError(500, "boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("couldn’t load the catalogue");

    getProducts.mockResolvedValue(PRODUCTS);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByRole("article")).toHaveLength(4);
  });

  it("points shoppers to the Voice page to buy", async () => {
    vi.spyOn(api, "getProducts").mockResolvedValue(PRODUCTS);
    renderPage();
    expect(screen.getByRole("link", { name: "Voice page" })).toHaveAttribute("href", "/");
  });
});

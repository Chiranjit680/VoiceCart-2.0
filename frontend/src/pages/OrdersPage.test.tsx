import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OrdersPage from "./OrdersPage";
import { api, ApiError, type Order } from "@/lib/api";

const logout = vi.fn();
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ logout }) }));

const butter = { id: 102, name: "Amul Butter 500g", brand_name: "Amul", price: 285, avg_rating: 4.5, num_reviews: 12, stock: 60, has_image: true };
const rice = { id: 103, name: "India Gate Basmati Rice 5kg", brand_name: "India Gate", price: 720, avg_rating: 4.7, num_reviews: 30, stock: 40, has_image: false };

const order = (id: number, created: string, overrides: Partial<Order> = {}): Order => ({
  id, user_id: 2, address: "221B Baker Street, London", total_amount: 1290, status: "pending", created_at: created,
  items: [
    { product_id: 102, quantity: 2, price: 285, product: butter },
    { product_id: 103, quantity: 1, price: 720, product: rice },
  ],
  ...overrides,
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <OrdersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("OrdersPage", () => {
  beforeEach(() => logout.mockClear());
  afterEach(() => vi.restoreAllMocks());

  it("lists orders with each item's photo, quantity and price", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([order(7, "2026-10-16T10:00:00+05:30")]);
    renderPage();

    const card = await screen.findByRole("article", { name: "Order 7" });
    expect(within(card).getByText("Order #7")).toBeInTheDocument();
    expect(within(card).getByText("pending")).toBeInTheDocument();
    expect(within(card).getByText("2 × ₹285")).toBeInTheDocument();
    expect(within(card).getByText("₹570")).toBeInTheDocument(); // line total
    expect(within(card).getByText("₹1,290")).toBeInTheDocument(); // order total
    expect(within(card).getByText(/221B Baker Street/)).toBeInTheDocument();

    const withPhoto = within(card).getByRole("img", { name: "Amul Butter 500g" }) as HTMLImageElement;
    expect(withPhoto.src).toMatch(/\/product\/102\/image$/);
    expect(within(card).getByRole("img", { name: "India Gate Basmati Rice 5kg (no photo)" })).toBeInTheDocument();
  });

  it("shows the newest order first", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([
      order(1, "2026-09-01T10:00:00+05:30"),
      order(3, "2026-10-16T10:00:00+05:30"),
      order(2, "2026-10-01T10:00:00+05:30"),
    ]);
    renderPage();
    await screen.findByRole("article", { name: "Order 3" });
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Order 3", "Order 2", "Order 1"]);
  });

  it("copes with an item whose product is missing", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([
      order(5, "2026-10-16T10:00:00+05:30", { items: [{ product_id: 999, quantity: 1, price: 50, product: null }] }),
    ]);
    renderPage();
    expect(await screen.findByText("Product #999")).toBeInTheDocument();
  });

  it("styles a cancelled order differently from a pending one", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([order(8, "2026-10-16T10:00:00+05:30", { status: "Cancelled" })]);
    renderPage();
    expect(await screen.findByText("Cancelled")).toHaveClass("text-destructive");
  });

  it("explains an empty history and points to the Voice page", async () => {
    vi.spyOn(api, "getOrders").mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("No orders yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voice page" })).toHaveAttribute("href", "/");
  });

  it("offers a retry when loading fails", async () => {
    // The page retries a failed load twice (about 3 seconds) before giving up, so wait for that.
    const getOrders = vi.spyOn(api, "getOrders").mockRejectedValue(new ApiError(500, "boom"));
    renderPage();
    expect(await screen.findByRole("alert", {}, { timeout: 8000 })).toHaveTextContent("couldn’t load your orders");
    expect(getOrders).toHaveBeenCalledTimes(3);

    getOrders.mockResolvedValue([order(9, "2026-10-16T10:00:00+05:30")]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Order 9" })).toBeInTheDocument();
  }, 15000);

  it("signs the user out when their login has expired", async () => {
    vi.spyOn(api, "getOrders").mockRejectedValue(new ApiError(401, "Could not validate credentials"));
    renderPage();
    await waitFor(() => expect(logout).toHaveBeenCalled());
  });
});

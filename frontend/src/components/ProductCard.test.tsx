import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ProductCard, ProductCardRow } from "./ProductCard";
import type { ProductCardData } from "@/lib/api";

const butter: ProductCardData = {
  id: 102, name: "Amul Butter 500g", brand_name: "Amul", price: 285, avg_rating: 4.5, num_reviews: 12, stock: 60, has_image: true,
};

describe("ProductCard", () => {
  it("shows the product's photo, name, brand and price", () => {
    render(<ProductCard product={butter} />);
    const photo = screen.getByRole("img", { name: "Amul Butter 500g" }) as HTMLImageElement;
    expect(photo.src).toMatch(/\/product\/102\/image$/);
    expect(photo).toHaveAttribute("loading", "lazy");
    expect(screen.getByRole("heading", { name: "Amul Butter 500g" })).toBeInTheDocument();
    expect(screen.getByText("Amul")).toBeInTheDocument();
    expect(screen.getByText("₹285")).toBeInTheDocument();
  });

  it("shows a placeholder, not a broken image, when the product has no photo", () => {
    render(<ProductCard product={{ ...butter, has_image: false }} />);
    expect(screen.getByRole("img", { name: "Amul Butter 500g (no photo)" })).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("falls back to the placeholder when the photo fails to load", () => {
    render(<ProductCard product={butter} />);
    fireEvent.error(document.querySelector("img")!);
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByRole("img", { name: /no photo/ })).toBeInTheDocument();
  });

  it("shows the quantity for a cart line", () => {
    render(<ProductCard product={{ ...butter, quantity: 3 }} />);
    expect(screen.getByText("×3")).toBeInTheDocument();
  });

  it("warns about low and zero stock, and says nothing when stock is healthy", () => {
    const { rerender } = render(<ProductCard product={{ ...butter, stock: 3 }} />);
    expect(screen.getByText("Only 3 left")).toBeInTheDocument();
    rerender(<ProductCard product={{ ...butter, stock: 0 }} />);
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    rerender(<ProductCard product={butter} />);
    expect(screen.queryByText(/left|Out of stock/)).toBeNull();
  });

  it("shows the rating only when there are reviews", () => {
    const { rerender } = render(<ProductCard product={butter} />);
    expect(screen.getByText("4.5")).toBeInTheDocument();
    rerender(<ProductCard product={{ ...butter, num_reviews: 0, avg_rating: 0 }} />);
    expect(screen.queryByText("0.0")).toBeNull();
  });

  it("leaves out the brand line when there is no brand", () => {
    render(<ProductCard product={{ ...butter, brand_name: null }} />);
    expect(screen.queryByText("Amul")).toBeNull();
  });
});

describe("ProductCardRow", () => {
  it("renders one card per product", () => {
    render(<ProductCardRow products={[butter, { ...butter, id: 103, name: "India Gate Basmati Rice 5kg", has_image: false }]} />);
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("renders nothing for an empty list", () => {
    const { container } = render(<ProductCardRow products={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

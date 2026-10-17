import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Conversation, type ConversationItem } from "./Conversation";

const butter = { id: 102, name: "Amul Butter 500g", brand_name: "Amul", price: 285, avg_rating: 4.5, num_reviews: 12, stock: 60, has_image: true };

describe("Conversation", () => {
  it("invites the user to speak when it is empty", () => {
    render(<Conversation items={[]} />);
    expect(screen.getByText("What would you like to buy?")).toBeInTheDocument();
  });

  it("shows what the user said and the assistant's reply", () => {
    const items: ConversationItem[] = [
      { id: 1, role: "user", text: "do you have amul butter" },
      { id: 2, role: "assistant", text: "Yes, 285 rupees.", products: [] },
    ];
    render(<Conversation items={items} />);
    expect(screen.getByText("do you have amul butter")).toBeInTheDocument();
    expect(screen.getByText("Yes, 285 rupees.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Products" })).toBeNull();
  });

  it("shows the product cards with the reply that carries them", () => {
    const items: ConversationItem[] = [
      { id: 1, role: "user", text: "amul butter" },
      { id: 2, role: "assistant", text: "Here it is.", products: [butter] },
      { id: 3, role: "user", text: "and rice" },
      { id: 4, role: "assistant", text: "No rice.", products: [] },
    ];
    render(<Conversation items={items} />);
    const row = screen.getByRole("list", { name: "Products" });
    expect(within(row).getByRole("heading", { name: "Amul Butter 500g" })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(1); // only the reply that had products
  });

  it("shows notices as plain centred text, not as a chat bubble", () => {
    render(<Conversation items={[{ id: 1, role: "notice", text: "(no speech detected)" }]} />);
    expect(screen.getByText("(no speech detected)")).toHaveClass("text-center");
  });

  it("shows thinking dots while waiting, even before any message", () => {
    render(<Conversation items={[]} pending />);
    expect(screen.getByRole("status", { name: "The assistant is thinking" })).toBeInTheDocument();
    expect(screen.queryByText("What would you like to buy?")).toBeNull();
  });

  it("announces new messages to screen readers", () => {
    render(<Conversation items={[{ id: 1, role: "user", text: "hello" }]} />);
    expect(screen.getByLabelText("Conversation")).toHaveAttribute("aria-live", "polite");
  });
});

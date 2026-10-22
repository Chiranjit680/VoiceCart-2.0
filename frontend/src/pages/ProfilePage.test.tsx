import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ProfilePage from "./ProfilePage";
import { addEntry } from "@/lib/profile";
import { api, ApiError, type Profile } from "@/lib/api";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ logout: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const SAVED: Profile = { age: 34, preferences: ["vegetarian"], medical_conditions: ["diabetes"] };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProfilePage />
    </QueryClientProvider>
  );
}

describe("addEntry", () => {
  it("tidies spaces, ignores blanks and repeats (any case), and keeps order", () => {
    expect(addEntry([], "  low   salt ")).toEqual(["low salt"]);
    expect(addEntry(["vegan"], "Vegan")).toEqual(["vegan"]);
    expect(addEntry(["vegan"], "   ")).toEqual(["vegan"]);
    expect(addEntry(["vegan"], "keto")).toEqual(["vegan", "keto"]);
  });

  it("stops at the server's limits", () => {
    expect(addEntry([], "x".repeat(200))[0]).toHaveLength(80);
    const full = Array.from({ length: 30 }, (_, i) => `item ${i}`);
    expect(addEntry(full, "one more")).toBe(full);
  });
});

const openEditor = async () => fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

describe("ProfilePage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows what is saved as read-only text, with an Edit button and no form", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue(SAVED);
    renderPage();
    const view = await screen.findByRole("region", { name: "Your profile" });
    expect(within(view).getByText("34 years")).toBeInTheDocument();
    expect(within(view).getByText("vegetarian")).toBeInTheDocument();
    expect(within(view).getByText("diabetes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Age")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save profile" })).toBeNull();
  });

  it("says 'Not added' for anything the shopper has not filled in", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue({ age: null, preferences: [], medical_conditions: [] });
    renderPage();
    await screen.findByRole("button", { name: "Edit" });
    expect(screen.getAllByText("Not added")).toHaveLength(3);
  });

  it("Edit opens the form filled with what is saved", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue(SAVED);
    renderPage();
    await openEditor();
    expect(screen.getByDisplayValue("34")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Preferences added" })).getByText("vegetarian")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Medical conditions added" })).getByText("diabetes")).toBeInTheDocument();
  });

  it("Cancel throws away changes and goes back to the saved profile", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue(SAVED);
    const saveProfile = vi.spyOn(api, "saveProfile");
    renderPage();
    await openEditor();
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "99" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(saveProfile).not.toHaveBeenCalled();
    expect(screen.getByText("34 years")).toBeInTheDocument();
    await openEditor(); // reopening shows the saved value again, not the abandoned 99
    expect(screen.getByLabelText("Age")).toHaveValue("34");
  });

  it("saving returns to the read-only view showing the new values", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue(SAVED);
    vi.spyOn(api, "saveProfile").mockImplementation(async (p) => p);
    renderPage();
    await openEditor();
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "35" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("35 years")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("starts empty for a new shopper and cannot save until something changes", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue({ age: null, preferences: [], medical_conditions: [] });
    renderPage();
    await openEditor();
    const save = screen.getByRole("button", { name: "Save profile" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "40" } });
    expect(save).toBeEnabled();
  });

  it("adds entries with Enter (without submitting) and the Add button, removes with the x, then saves the lot", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue({ age: null, preferences: [], medical_conditions: [] });
    const saveProfile = vi.spyOn(api, "saveProfile").mockImplementation(async (p) => p);
    renderPage();
    await openEditor();

    const preferences = screen.getByLabelText("Preferences");
    fireEvent.change(preferences, { target: { value: "vegan" } });
    fireEvent.keyDown(preferences, { key: "Enter" });
    expect(saveProfile).not.toHaveBeenCalled(); // Enter only added the chip
    fireEvent.change(preferences, { target: { value: "only Amul" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Add" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Remove only Amul" }));

    fireEvent.change(screen.getByLabelText("Medical conditions"), { target: { value: "peanut allergy" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Add" })[1]);
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "29" } });

    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
    expect(saveProfile.mock.calls[0][0]).toEqual({ age: 29, preferences: ["vegan"], medical_conditions: ["peanut allergy"] });
  });

  it("will not save an age that is not a whole number from 0 to 120", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue(SAVED);
    const saveProfile = vi.spyOn(api, "saveProfile");
    renderPage();
    await openEditor();
    const age = screen.getByLabelText("Age");
    for (const bad of ["abc", "-3", "200", "3.5"]) {
      fireEvent.change(age, { target: { value: bad } });
      expect(screen.getByRole("alert")).toHaveTextContent("whole number from 0 to 120");
      expect(screen.getByRole("button", { name: "Save profile" })).toBeDisabled();
    }
    expect(saveProfile).not.toHaveBeenCalled();
  });

  it("clears the age when the box is emptied", async () => {
    vi.spyOn(api, "getProfile").mockResolvedValue(SAVED);
    const saveProfile = vi.spyOn(api, "saveProfile").mockImplementation(async (p) => p);
    renderPage();
    await openEditor();
    fireEvent.change(screen.getByLabelText("Age"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(saveProfile).toHaveBeenCalled());
    expect(saveProfile.mock.calls[0][0].age).toBeNull();
  });

  it("offers a retry when loading fails", async () => {
    const getProfile = vi.spyOn(api, "getProfile").mockRejectedValue(new ApiError(500, "boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("couldn’t load your profile");
    getProfile.mockResolvedValue(SAVED);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("34 years")).toBeInTheDocument();
  });
});

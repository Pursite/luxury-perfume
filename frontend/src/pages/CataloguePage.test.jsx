import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

import { productsPage } from "../test/fixtures";
import CataloguePage from "./CataloguePage";

const api = vi.hoisted(() => ({ listProducts: vi.fn() }));

vi.mock("../api/products", () => api);

function renderCatalogue(initialEntry = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <CataloguePage />
    </MemoryRouter>,
  );
}

function HistoryBackButton() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate(-1)}>Back</button>;
}

beforeEach(() => {
  api.listProducts.mockReset();
});

test("renders discounted, regular-price, and out-of-stock API products", async () => {
  api.listProducts.mockResolvedValue(productsPage);
  renderCatalogue();

  expect(await screen.findByRole("heading", { name: "Sauvage Elixir" })).toBeInTheDocument();
  const featured = screen.getByText("Featured");
  expect(featured).toBeInTheDocument();
  expect(featured.closest(".product-card-media")).toBeNull();
  expect(featured.closest(".product-card-brandline")).not.toBeNull();
  expect(screen.getByText("6,250,000 toman")).toBeInTheDocument();
  expect(screen.getByText("7,500,000 toman")).toHaveClass("price-original");
  expect(screen.getByRole("heading", { name: "Naxos" })).toBeInTheDocument();
  expect(screen.getByText("8,900,000 toman")).toBeInTheDocument();
  expect(screen.getByLabelText("No image available for Naxos")).toHaveTextContent("Luxury Perfume");
  expect(screen.getByRole("heading", { name: "Aventus" })).toBeInTheDocument();
  expect(screen.getByText("Out of stock")).toBeInTheDocument();
});

test("shows a stable loading catalogue", () => {
  api.listProducts.mockReturnValue(new Promise(() => {}));
  renderCatalogue();

  expect(screen.getByRole("status", { name: "Loading fragrances" })).toBeInTheDocument();
});

test("clears active search and filters from the no-results state", async () => {
  const user = userEvent.setup();
  api.listProducts.mockImplementation((parameters) => (
    Object.keys(parameters).length
      ? Promise.resolve({ ...productsPage, count: 0, results: [] })
      : Promise.resolve(productsPage)
  ));
  renderCatalogue("/?search=rose&target_audience=unisex");

  expect(await screen.findByRole("heading", { name: "No fragrances found" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Clear search and filters" }));

  expect(screen.getByRole("searchbox", { name: "Search fragrances" })).toHaveValue("");
  expect(screen.getByRole("combobox", { name: "Audience" })).toHaveValue("");
  expect(await screen.findByRole("heading", { name: "Sauvage Elixir" })).toBeInTheDocument();
});

test("shows a recoverable catalogue API error", async () => {
  const user = userEvent.setup();
  api.listProducts
    .mockRejectedValueOnce(new Error("network unavailable"))
    .mockResolvedValueOnce(productsPage);
  renderCatalogue();

  expect(await screen.findByRole("heading", { name: "The collection could not be loaded" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("heading", { name: "Sauvage Elixir" })).toBeInTheDocument();
});

test("sends committed URL filters to the server", async () => {
  api.listProducts.mockResolvedValue(productsPage);
  renderCatalogue("/?search=rose&target_audience=unisex&page=2");

  await screen.findByRole("heading", { name: "Sauvage Elixir" });
  expect(api.listProducts).toHaveBeenCalledWith(
    expect.objectContaining({ search: "rose", target_audience: "unisex", page: "2" }),
    expect.any(AbortSignal),
  );
});

test("offers only fragrance-family values accepted by the Product API", async () => {
  api.listProducts.mockResolvedValue(productsPage);
  renderCatalogue();

  const family = await screen.findByRole("combobox", { name: "Family" });
  expect(family).toHaveTextContent("Amber");
  expect(family).toHaveTextContent("Citrus");
  expect(family).not.toHaveTextContent("Oriental");
  expect(family).not.toHaveTextContent("Fresh");
});

test("clears search immediately and returns focus", async () => {
  api.listProducts.mockResolvedValue(productsPage);
  renderCatalogue("/?search=rose");
  const search = await screen.findByRole("searchbox", { name: "Search fragrances" });

  fireEvent.click(screen.getByRole("button", { name: "Clear search" }));

  expect(search).toHaveValue("");
  expect(search).toHaveFocus();
});

test("keeps the search draft synchronized with browser history", async () => {
  api.listProducts.mockResolvedValue(productsPage);
  render(
    <MemoryRouter
      initialEntries={["/?search=rose", "/?search=amber"]}
      initialIndex={1}
    >
      <HistoryBackButton />
      <CataloguePage />
    </MemoryRouter>,
  );
  const search = await screen.findByRole("searchbox", { name: "Search fragrances" });
  expect(search).toHaveValue("amber");

  fireEvent.click(screen.getByRole("button", { name: "Back" }));

  await waitFor(() => expect(search).toHaveValue("rose"));
  await new Promise((resolve) => window.setTimeout(resolve, 350));
  expect(search).toHaveValue("rose");
});

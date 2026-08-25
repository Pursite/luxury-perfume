import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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

beforeEach(() => {
  api.listProducts.mockReset();
});

test("renders discounted, regular-price, and out-of-stock API products", async () => {
  api.listProducts.mockResolvedValue(productsPage);
  renderCatalogue();

  expect(await screen.findByRole("heading", { name: "Sauvage Elixir" })).toBeInTheDocument();
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

test("guides users when no products match", async () => {
  api.listProducts.mockResolvedValue({ ...productsPage, count: 0, results: [] });
  renderCatalogue();

  expect(await screen.findByRole("heading", { name: "No fragrances found" })).toBeInTheDocument();
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

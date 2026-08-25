import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { productDetail } from "../test/fixtures";
import ProductDetailPage from "./ProductDetailPage";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/products/sauvage-elixir"]}>
      <Routes>
        <Route path="/products/:slug" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => vi.unstubAllGlobals());

test("renders Product Detail fields and the real fragrance pyramid", async () => {
  fetch.mockResolvedValue(jsonResponse(productDetail));
  renderDetail();

  expect(await screen.findByRole("heading", { name: "Sauvage Elixir" })).toBeInTheDocument();
  expect(screen.getByText("An intense trail of spices, lavender, and polished woods.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Top notes" })).toBeInTheDocument();
  expect(screen.getByText("Grapefruit")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Heart notes" })).toBeInTheDocument();
  expect(screen.getByText("Lavender")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Base notes" })).toBeInTheDocument();
  expect(screen.getByText("Sandalwood")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/products/sauvage-elixir/",
    expect.objectContaining({ method: "GET", signal: expect.any(AbortSignal) }),
  );
});

test("selects another Product image through an accessible thumbnail", async () => {
  const user = userEvent.setup();
  fetch.mockResolvedValue(jsonResponse(productDetail));
  renderDetail();

  const mainImage = await screen.findByRole("img", { name: "Sauvage Elixir by Dior — image 1" });
  await user.click(screen.getByRole("button", { name: "View Sauvage Elixir image 2" }));
  expect(mainImage).toHaveAttribute("src", expect.stringContaining("sauvage-side.jpg"));
});

test("shows a stable detail loading state", async () => {
  let finishLoading;
  fetch.mockReturnValue(new Promise((resolve) => { finishLoading = resolve; }));
  renderDetail();
  expect(screen.getByRole("status", { name: "Loading product" })).toBeInTheDocument();
  finishLoading(jsonResponse(productDetail));
  await screen.findByRole("heading", { name: "Sauvage Elixir" });
});

test("renders a product-specific not-found state", async () => {
  fetch.mockResolvedValue(jsonResponse({ detail: "Not found." }, 404));
  renderDetail();
  expect(await screen.findByRole("heading", { name: "Fragrance not found" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Return to the collection" })).toHaveAttribute("href", "/");
});

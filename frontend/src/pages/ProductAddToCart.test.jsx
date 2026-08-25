import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { clearTokens, setTokens } from "../api/tokenStore";
import Header from "../components/Header";
import { AuthProvider } from "../context/AuthContext";
import { CartProvider } from "../context/CartContext";
import { cartResponse, productDetail } from "../test/fixtures";
import ProductDetailPage from "./ProductDetailPage";

const emptyCart = { items: [], total_quantity: 0, total_price: "0.00", has_unavailable_items: false };

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderProduct() {
  return render(
    <MemoryRouter initialEntries={["/products/sauvage-elixir"]}>
      <AuthProvider>
        <CartProvider>
          <Header />
          <Routes>
            <Route path="/products/:slug" element={<ProductDetailPage />} />
            <Route path="/login" element={<h1>Sign in to continue</h1>} />
          </Routes>
        </CartProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

test("adds a Product through the real authenticated Cart contract", async () => {
  const user = userEvent.setup();
  setTokens({ access: "old-access", refresh: "old-refresh" });
  fetch.mockImplementation((url, options = {}) => {
    if (url.endsWith("/token/refresh/")) {
      return Promise.resolve(jsonResponse({ access: "new-access", refresh: "new-refresh" }));
    }
    if (url === "/api/v1/products/sauvage-elixir/") return Promise.resolve(jsonResponse(productDetail));
    if (url === "/api/v1/cart/" && options.method === "GET") return Promise.resolve(jsonResponse(emptyCart));
    if (url === "/api/v1/cart/items/" && options.method === "POST") return Promise.resolve(jsonResponse(cartResponse, 201));
    throw new Error(`Unexpected request: ${options.method || "GET"} ${url}`);
  });
  renderProduct();

  await user.click(await screen.findByRole("button", { name: "Add to cart" }));
  expect(await screen.findByRole("status", { name: "Cart update" })).toHaveTextContent("Added to your cart.");
  const addRequest = fetch.mock.calls.find(([url, options]) => url === "/api/v1/cart/items/" && options.method === "POST");
  expect(JSON.parse(addRequest[1].body)).toEqual({ product_slug: "sauvage-elixir", quantity: 1 });
  expect(addRequest[1].headers.Authorization).toBe("Bearer new-access");
  expect(screen.getByLabelText("2 items in cart")).toBeInTheDocument();
});

test("routes an anonymous add interaction to Login without calling Cart", async () => {
  const user = userEvent.setup();
  fetch.mockImplementation((url) => {
    if (url === "/api/v1/products/sauvage-elixir/") return Promise.resolve(jsonResponse(productDetail));
    throw new Error(`Anonymous flow must not request ${url}`);
  });
  renderProduct();

  await user.click(await screen.findByRole("button", { name: "Sign in to add to cart" }));
  expect(screen.getByRole("heading", { name: "Sign in to continue" })).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([url]) => url.startsWith("/api/v1/cart"))).toHaveLength(0);
});

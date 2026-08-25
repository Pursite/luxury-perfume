import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import App from "./App";
import { productsPage } from "./test/fixtures";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
    count: 0,
    total_pages: 1,
    current_page: 1,
    page_size: 20,
    links: { next: null, previous: null },
    results: [],
  })));
});
afterEach(() => vi.unstubAllGlobals());

test("keeps the development notice visible in the storefront shell", () => {
  renderApp();

  expect(
    screen.getByText(
      "این وب‌سایت در حال توسعه است. خدمات پیامکی و پرداخت آنلاین در حال حاضر در دسترس نیستند.",
    ),
  ).toHaveAttribute("lang", "fa");
  expect(screen.getByText(/این وب‌سایت/)).toHaveAttribute("dir", "rtl");
});

test("renders real paginated Product API results through the storefront client", async () => {
  fetch.mockResolvedValueOnce(jsonResponse(productsPage));
  renderApp();

  expect(await screen.findByRole("heading", { name: "Sauvage Elixir" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Naxos" })).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/products/",
    expect.objectContaining({ method: "GET" }),
  );
});

test("keeps Product API errors visible instead of rendering an empty catalogue", async () => {
  fetch.mockResolvedValueOnce(jsonResponse({ detail: "try again later" }, 429));
  renderApp();

  expect(await screen.findByRole("heading", { name: "The collection could not be loaded" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Sauvage Elixir" })).not.toBeInTheDocument();
});

test("routes an anonymous Cart visit to Login", async () => {
  renderApp("/cart");
  expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([url]) => url.startsWith("/api/v1/cart"))).toHaveLength(0);
});

test("routes an anonymous Account visit to Login", async () => {
  renderApp("/account");

  expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([url]) => url.startsWith("/api/v1/users/profile"))).toHaveLength(0);
});

test("renders a useful 404 page inside the storefront shell", () => {
  renderApp("/a-fragrance-that-does-not-exist");
  expect(screen.getByRole("heading", { name: "This trail ends here." })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Return to the collection" })).toHaveAttribute("href", "/");
  expect(screen.getByText(/خدمات پیامکی و پرداخت آنلاین/)).toBeInTheDocument();
});

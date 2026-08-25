import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

import Header from "../components/Header";
import { CartProvider } from "../context/CartContext";
import { cartResponse, productsPage } from "../test/fixtures";
import CartPage from "./CartPage";

const cartApi = vi.hoisted(() => ({
  getCart: vi.fn(),
  addCartItem: vi.fn(),
  updateCartItem: vi.fn(),
  removeCartItem: vi.fn(),
  clearCart: vi.fn(),
}));
const auth = vi.hoisted(() => ({
  status: "authenticated",
  isAuthenticated: true,
  logout: vi.fn(),
}));

vi.mock("../api/cart", () => cartApi);
vi.mock("../hooks/useAuth", () => ({ default: () => auth }));

const emptyCart = {
  items: [],
  total_quantity: 0,
  total_price: "0.00",
  has_unavailable_items: false,
};

function renderCart() {
  return render(
    <MemoryRouter>
      <CartProvider>
        <Header />
        <CartPage />
      </CartProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Object.values(cartApi).forEach((mock) => mock.mockReset());
  auth.logout.mockReset();
});

test("shows a stable Cart loading state", async () => {
  let finishLoading;
  cartApi.getCart.mockReturnValue(new Promise((resolve) => { finishLoading = resolve; }));
  renderCart();
  expect(screen.getByRole("status", { name: "Loading cart" })).toBeInTheDocument();
  finishLoading(emptyCart);
  expect(await screen.findByRole("heading", { name: "Your cart is empty" })).toBeInTheDocument();
});

test("keeps unavailable Cart lines visible with current stock", async () => {
  const unavailableCart = {
    items: [{
      product: {
        uuid: productsPage.results[2].uuid,
        slug: productsPage.results[2].slug,
        name: productsPage.results[2].name,
        primary_image: null,
      },
      quantity: 2,
      unit_price: "12000000.00",
      line_total: "24000000.00",
      available_stock: 0,
      available: false,
    }],
    total_quantity: 2,
    total_price: "24000000.00",
    has_unavailable_items: true,
  };
  cartApi.getCart.mockResolvedValue(unavailableCart);
  renderCart();

  const line = (await screen.findByRole("heading", { name: "Aventus" })).closest("article");
  expect(within(line).getByText("Currently unavailable")).toBeInTheDocument();
  expect(within(line).getByText("Current stock: 0")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remove Aventus" })).toBeEnabled();
});

test("sets an absolute quantity and synchronizes the Header badge", async () => {
  const user = userEvent.setup();
  const updated = {
    ...cartResponse,
    items: [{ ...cartResponse.items[0], quantity: 3, line_total: "18750000.00" }],
    total_quantity: 3,
    total_price: "18750000.00",
  };
  cartApi.getCart.mockResolvedValue(cartResponse);
  cartApi.updateCartItem.mockResolvedValue(updated);
  renderCart();

  const quantity = await screen.findByLabelText("Quantity for Sauvage Elixir");
  await user.clear(quantity);
  await user.type(quantity, "3");
  await user.click(screen.getByRole("button", { name: "Update Sauvage Elixir quantity" }));

  expect(cartApi.updateCartItem).toHaveBeenCalledWith("sauvage-elixir", 3);
  expect(await screen.findByRole("link", { name: "Cart, 3 items" })).toBeInTheDocument();
});

test("removes an item and refreshes authoritative Cart state", async () => {
  const user = userEvent.setup();
  cartApi.getCart.mockResolvedValueOnce(cartResponse).mockResolvedValueOnce(emptyCart);
  cartApi.removeCartItem.mockResolvedValue(null);
  renderCart();

  await user.click(await screen.findByRole("button", { name: "Remove Sauvage Elixir" }));
  expect(cartApi.removeCartItem).toHaveBeenCalledWith("sauvage-elixir");
  expect(await screen.findByRole("heading", { name: "Your cart is empty" })).toBeInTheDocument();
});

test("clears the Cart only after accessible confirmation", async () => {
  const user = userEvent.setup();
  cartApi.getCart.mockResolvedValueOnce(cartResponse).mockResolvedValueOnce(emptyCart);
  cartApi.clearCart.mockResolvedValue(null);
  renderCart();

  await user.click(await screen.findByRole("button", { name: "Clear cart" }));
  const dialog = screen.getByRole("alertdialog", { name: "Clear your cart?" });
  expect(dialog).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Keep items" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Clear cart permanently" }));
  expect(cartApi.clearCart).toHaveBeenCalledOnce();
  expect(await screen.findByRole("heading", { name: "Your cart is empty" })).toBeInTheDocument();
});

test("keeps the clear confirmation open and exposes a mutation failure", async () => {
  const user = userEvent.setup();
  cartApi.getCart.mockResolvedValue(cartResponse);
  cartApi.clearCart.mockRejectedValue(new Error("Cart service unavailable"));
  renderCart();

  await user.click(await screen.findByRole("button", { name: "Clear cart" }));
  await user.click(screen.getByRole("button", { name: "Clear cart permanently" }));

  const dialog = screen.getByRole("alertdialog", { name: "Clear your cart?" });
  expect(within(dialog).getByRole("alert")).toHaveTextContent("Cart service unavailable");
  expect(dialog).toBeInTheDocument();
});

test("keeps payment disabled and explains it without issuing a request", async () => {
  cartApi.getCart.mockResolvedValue(cartResponse);
  renderCart();

  const payment = await screen.findByRole("button", { name: "Proceed to Payment" });
  const wrapper = screen.getByRole("group", { name: "Proceed to Payment, unavailable" });
  expect(payment).toBeDisabled();
  wrapper.focus();
  await waitFor(() => {
    expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  });
  expect(cartApi.addCartItem).not.toHaveBeenCalled();
  expect(cartApi.updateCartItem).not.toHaveBeenCalled();
});

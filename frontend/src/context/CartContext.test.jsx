import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { AuthContext } from "./authContext";
import { CartProvider } from "./CartContext";
import useCart from "../hooks/useCart";

const cartApi = vi.hoisted(() => ({
  getCart: vi.fn(),
  addCartItem: vi.fn(),
  updateCartItem: vi.fn(),
  removeCartItem: vi.fn(),
  clearCart: vi.fn(),
}));

vi.mock("../api/cart", () => cartApi);

const emptyCart = {
  items: [],
  total_quantity: 0,
  total_price: "0.00",
  has_unavailable_items: false,
};

function MutationProbe() {
  const cart = useCart();
  return (
    <button
      type="button"
      disabled={cart.loading}
      onClick={() => {
        cart.addItem("noir-rose", 1).catch(() => {});
        cart.addItem("noir-rose", 1).catch(() => {});
      }}
    >
      Add twice
    </button>
  );
}

beforeEach(() => {
  Object.values(cartApi).forEach((mock) => mock.mockReset());
  cartApi.getCart.mockResolvedValue(emptyCart);
});

test("allows only one cart mutation to begin while another mutation is in flight", async () => {
  let finishMutation;
  cartApi.addCartItem.mockImplementation(() => new Promise((resolve) => { finishMutation = resolve; }));

  render(
    <AuthContext.Provider value={{ status: "authenticated", isAuthenticated: true }}>
      <CartProvider><MutationProbe /></CartProvider>
    </AuthContext.Provider>,
  );

  const button = screen.getByRole("button", { name: "Add twice" });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);

  expect(cartApi.addCartItem).toHaveBeenCalledTimes(1);
  finishMutation(emptyCart);
});

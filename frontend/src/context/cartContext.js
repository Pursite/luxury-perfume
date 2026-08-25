import { createContext } from "react";

export const EMPTY_CART = {
  items: [],
  total_quantity: 0,
  total_price: "0.00",
  has_unavailable_items: false,
};

export const emptyCartContext = {
  cart: EMPTY_CART,
  loading: false,
  mutating: false,
  error: "",
  reload: async () => {},
  addItem: async () => {},
  updateItem: async () => {},
  removeItem: async () => {},
  clear: async () => {},
};

export const CartContext = createContext(emptyCartContext);

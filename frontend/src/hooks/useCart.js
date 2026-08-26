import { useContext } from "react";

import { CartContext } from "../context/cartContext";

export default function useCart() {
  return useContext(CartContext);
}

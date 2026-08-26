import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import * as cartApi from "../api/cart";
import useAuth from "../hooks/useAuth";
import { CartContext, EMPTY_CART, emptyCartContext } from "./cartContext";

function cartMessage(error) {
  const data = error?.data;
  const fieldMessage = data && Object.values(data).flat().find((value) => typeof value === "string");
  return fieldMessage || error?.message || "The cart could not be updated. Try again.";
}

function AuthenticatedCartProvider({ children }) {
  const [cart, setCart] = useState(EMPTY_CART);
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState("");
  const mutationInFlight = useRef(false);

  const reload = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setLoading(true);
    setError("");
    try {
      const nextCart = await cartApi.getCart();
      setCart(nextCart);
      return nextCart;
    } catch (caught) {
      setError(cartMessage(caught));
      throw caught;
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    cartApi.getCart()
      .then((nextCart) => {
        if (active) {
          setCart(nextCart);
          setLoading(false);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(cartMessage(caught));
          setLoading(false);
        }
      });
    return () => { active = false; };
  }, []);

  const mutate = useCallback(async (operation, { refresh = false } = {}) => {
    if (mutationInFlight.current) return null;
    mutationInFlight.current = true;
    setMutating(true);
    setError("");
    try {
      const response = await operation();
      if (refresh) return await reload({ quiet: true });
      if (response) setCart(response);
      return response;
    } catch (caught) {
      setError(cartMessage(caught));
      throw caught;
    } finally {
      mutationInFlight.current = false;
      setMutating(false);
    }
  }, [reload]);

  const value = useMemo(() => ({
    cart,
    loading,
    mutating,
    error,
    reload,
    addItem: (slug, quantity) => mutate(() => cartApi.addCartItem(slug, quantity)),
    updateItem: (slug, quantity) => mutate(() => cartApi.updateCartItem(slug, quantity)),
    removeItem: (slug) => mutate(() => cartApi.removeCartItem(slug), { refresh: true }),
    clear: () => mutate(() => cartApi.clearCart(), { refresh: true }),
  }), [cart, error, loading, mutate, mutating, reload]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function CartProvider({ children }) {
  const auth = useAuth();
  if (auth.status !== "authenticated") {
    return <CartContext.Provider value={emptyCartContext}>{children}</CartContext.Provider>;
  }
  return <AuthenticatedCartProvider>{children}</AuthenticatedCartProvider>;
}

import { request } from "./client";

export function getCart() {
  return request("/api/v1/cart/", { auth: true });
}

export function addCartItem(productSlug, quantity) {
  return request("/api/v1/cart/items/", {
    method: "POST",
    body: { product_slug: productSlug, quantity },
    auth: true,
  });
}

export function updateCartItem(productSlug, quantity) {
  return request(`/api/v1/cart/items/${encodeURIComponent(productSlug)}/`, {
    method: "PATCH",
    body: { quantity },
    auth: true,
  });
}

export function removeCartItem(productSlug) {
  return request(`/api/v1/cart/items/${encodeURIComponent(productSlug)}/`, {
    method: "DELETE",
    auth: true,
  });
}

export function clearCart() {
  return request("/api/v1/cart/", { method: "DELETE", auth: true });
}

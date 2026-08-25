import { request } from "./client";

function productQuery(parameters) {
  const query = new URLSearchParams();
  Object.entries(parameters).forEach(([key, value]) => {
    if (value !== "" && value != null) query.set(key, value);
  });
  return query.toString();
}

export function listProducts(parameters = {}, signal) {
  const query = productQuery(parameters);
  return request(`/api/v1/products/${query ? `?${query}` : ""}`, { signal });
}

export function getProduct(slug, signal) {
  return request(`/api/v1/products/${encodeURIComponent(slug)}/`, { signal });
}

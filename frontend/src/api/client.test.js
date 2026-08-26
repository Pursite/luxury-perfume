import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { backendUrl, refreshSession, request } from "./client";
import { clearTokens, setTokens } from "./tokenStore";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => vi.unstubAllGlobals());

test("keeps development API requests on the relative Vite path", () => {
  expect(backendUrl("/api/v1/products/")).toBe("/api/v1/products/");
});

test("refreshes an expired access token once and retries the protected request", async () => {
  setTokens({ access: "expired-access", refresh: "old-refresh" });
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "Token is invalid or expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ access: "new-access", refresh: "new-refresh" }))
    .mockResolvedValueOnce(jsonResponse({ total_quantity: 0, items: [] }));

  await expect(request("/api/v1/cart/", { auth: true })).resolves.toEqual({
    total_quantity: 0,
    items: [],
  });

  expect(fetch).toHaveBeenCalledTimes(3);
  expect(fetch.mock.calls[1][0]).toBe("/api/v1/users/token/refresh/");
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ refresh: "old-refresh" });
  expect(fetch.mock.calls[2][1].headers.Authorization).toBe("Bearer new-access");
  expect(sessionStorage.getItem("exon.refreshToken")).toBe("new-refresh");
});

test("clears the session when refresh fails", async () => {
  setTokens({ access: "expired-access", refresh: "old-refresh" });
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ detail: "refresh invalid" }, 401));

  await expect(request("/api/v1/cart/", { auth: true })).rejects.toMatchObject({ status: 401 });
  expect(sessionStorage.getItem("exon.refreshToken")).toBeNull();
});

test("preserves the refresh token when restoration is throttled", async () => {
  setTokens({ access: null, refresh: "old-refresh" });
  fetch.mockResolvedValueOnce(jsonResponse({ detail: "try again later" }, 429));

  await expect(refreshSession()).rejects.toMatchObject({ status: 429 });
  expect(sessionStorage.getItem("exon.refreshToken")).toBe("old-refresh");
});

test("shares one refresh across concurrent protected requests", async () => {
  setTokens({ access: "expired-access", refresh: "old-refresh" });
  let refreshCalls = 0;
  fetch.mockImplementation((url, options) => {
    if (url === "/api/v1/users/token/refresh/") {
      refreshCalls += 1;
      return Promise.resolve(jsonResponse({ access: "new-access", refresh: "new-refresh" }));
    }
    if (options.headers.Authorization === "Bearer expired-access") {
      return Promise.resolve(jsonResponse({ detail: "expired" }, 401));
    }
    return Promise.resolve(jsonResponse({ total_quantity: 0, items: [] }));
  });

  await expect(Promise.all([
    request("/api/v1/cart/", { auth: true }),
    request("/api/v1/cart/", { auth: true }),
  ])).resolves.toHaveLength(2);

  expect(refreshCalls).toBe(1);
});

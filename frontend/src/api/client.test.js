import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { backendUrl, refreshSession, request } from "./client";
import { clearTokens, getAccessToken, setAccessToken } from "./tokenStore";

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
  setAccessToken("expired-access");
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "Token is invalid or expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ access: "new-access" }))
    .mockResolvedValueOnce(jsonResponse({ total_quantity: 0, items: [] }));

  await expect(request("/api/v1/cart/", { auth: true })).resolves.toEqual({
    total_quantity: 0,
    items: [],
  });

  expect(fetch).toHaveBeenCalledTimes(3);
  expect(fetch.mock.calls[1][0]).toBe("/api/v1/users/token/refresh/");
  expect(fetch.mock.calls[1][1].body).toBeUndefined();
  expect(fetch.mock.calls[1][1].credentials).toBe("include");
  expect(fetch.mock.calls[2][1].headers.Authorization).toBe("Bearer new-access");
  expect(sessionStorage.getItem("exon.refreshToken")).toBeNull();
});

test("clears the session when refresh fails", async () => {
  setAccessToken("expired-access");
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ detail: "refresh invalid" }, 401));

  await expect(request("/api/v1/cart/", { auth: true })).rejects.toMatchObject({ status: 401 });
  expect(getAccessToken()).toBeNull();
});

test("preserves the refresh token when restoration is throttled", async () => {
  setAccessToken(null);
  fetch.mockResolvedValueOnce(jsonResponse({ detail: "try again later" }, 429));

  await expect(refreshSession()).rejects.toMatchObject({ status: 429 });
  expect(getAccessToken()).toBeNull();
});

test("shares one refresh across concurrent protected requests", async () => {
  setAccessToken("expired-access");
  let refreshCalls = 0;
  fetch.mockImplementation((url, options) => {
    if (url === "/api/v1/users/token/refresh/") {
      refreshCalls += 1;
      return Promise.resolve(jsonResponse({ access: "new-access" }));
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

test("does not retry a protected request when refresh fails", async () => {
  setAccessToken("expired-access");
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ detail: "temporarily unavailable" }, 503));

  await expect(request("/api/v1/cart/", { auth: true })).rejects.toMatchObject({ status: 503 });
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("does not retry a protected request after a malformed refresh success", async () => {
  setAccessToken("expired-access");
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({}));

  await expect(request("/api/v1/cart/", { auth: true })).rejects.toMatchObject({ status: 0 });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(getAccessToken()).toBe("expired-access");
});

test("refresh remains functional when Web Locks are unavailable", async () => {
  setAccessToken(null);
  fetch.mockResolvedValueOnce(jsonResponse({ access: "restored-access" }));

  await expect(refreshSession()).resolves.toBe("restored-access");
  expect(getAccessToken()).toBe("restored-access");
});

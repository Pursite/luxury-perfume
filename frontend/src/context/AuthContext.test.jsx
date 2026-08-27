import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, expect, test, vi } from "vitest";

import { request } from "../api/client";
import { clearTokens, getAccessToken, setAccessToken } from "../api/tokenStore";
import useAuth from "../hooks/useAuth";
import useCart from "../hooks/useCart";
import { AuthProvider } from "./AuthContext";
import { CartProvider } from "./CartContext";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function SessionProbe() {
  const auth = useAuth();
  return (
    <div>
      <span>{auth.status}</span>
      <button type="button" onClick={() => request("/api/v1/cart/", { auth: true }).catch(() => {})}>
        Load protected data
      </button>
    </div>
  );
}

function RestorationProbe() {
  const auth = useAuth();
  const cart = useCart();
  return (
    <div>
      <span>{auth.status}</span>
      <span>{cart.cart.total_quantity}</span>
      <button type="button" onClick={auth.retrySession}>Retry session</button>
    </div>
  );
}

function LogoutProbe() {
  const auth = useAuth();
  return (
    <div>
      <span>{auth.status}</span>
      <button type="button" onClick={() => auth.logout().catch(() => {})}>Sign out</button>
    </div>
  );
}

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("fetch", vi.fn());
});

test("returns the application to anonymous state when an active session cannot refresh", async () => {
  setAccessToken("expired-access");
  fetch
    .mockResolvedValueOnce(jsonResponse({ access: "active-access" }))
    .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ detail: "refresh invalid" }, 401));

  render(<AuthProvider><SessionProbe /></AuthProvider>);
  await screen.findByText("authenticated");

  await userEvent.click(screen.getByRole("button", { name: "Load protected data" }));

  await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
});

test("starts anonymously when the persistent refresh cookie is absent", async () => {
  fetch.mockResolvedValueOnce(jsonResponse({ detail: "Token is invalid or expired" }, 401));

  render(<AuthProvider><SessionProbe /></AuthProvider>);

  await screen.findByText("anonymous");
  expect(screen.queryByText("restoration_error")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/users/token/refresh/",
    expect.objectContaining({ method: "POST", credentials: "include" }),
  );
});

test("clears memory only after the cookie-backed logout succeeds", async () => {
  setAccessToken(null);
  fetch.mockImplementation((url) => {
    if (url === "/api/v1/users/token/refresh/") return Promise.resolve(jsonResponse({ access: "restored-access" }));
    if (url === "/api/v1/users/logout/") return Promise.resolve(jsonResponse({ message: "successfully logged out." }));
    throw new Error(`Unexpected request: ${url}`);
  });

  render(<AuthProvider><LogoutProbe /></AuthProvider>);
  await screen.findByText("authenticated");
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

  await screen.findByText("anonymous");
  const logoutCall = fetch.mock.calls.find(([url]) => url === "/api/v1/users/logout/");
  expect(logoutCall[1].credentials).toBe("include");
  expect(logoutCall[1].headers.Authorization).toBeUndefined();
  expect(getAccessToken()).toBeNull();
});

test("restores a valid rotated session before initializing the protected Cart", async () => {
  setAccessToken(null);
  const refreshCalls = [];
  const cartCalls = [];
  fetch.mockImplementation((url, options) => {
    if (url === "/api/v1/users/token/refresh/") {
      refreshCalls.push(options);
      return Promise.resolve(jsonResponse({ access: "restored-access" }));
    }
    if (url === "/api/v1/cart/") {
      cartCalls.push(options);
      return Promise.resolve(jsonResponse({ total_quantity: 1, items: [] }));
    }
    throw new Error(`Unexpected request: ${url}`);
  });

  render(
    <StrictMode>
      <AuthProvider>
        <CartProvider>
          <RestorationProbe />
        </CartProvider>
      </AuthProvider>
    </StrictMode>,
  );

  await screen.findByText("authenticated");
  await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  expect(sessionStorage.getItem("exon.refreshToken")).toBeNull();
  expect(getAccessToken()).toBe("restored-access");
  expect(refreshCalls).toHaveLength(1);
  expect(cartCalls.length).toBeGreaterThan(0);
  expect(cartCalls[0].headers.Authorization).toBe("Bearer restored-access");
});

test("recovers a transient reload failure without classifying the session as anonymous", async () => {
  setAccessToken(null);
  const refreshCalls = [];
  const cartCalls = [];
  fetch.mockImplementation((url, options) => {
    if (url === "/api/v1/users/token/refresh/") {
      refreshCalls.push(options);
      if (refreshCalls.length === 1) {
        return Promise.resolve(jsonResponse({ detail: "try again later" }, 429));
      }
      return Promise.resolve(jsonResponse({ access: "restored-access" }));
    }
    if (url === "/api/v1/cart/") {
      cartCalls.push(options);
      return Promise.resolve(jsonResponse({ total_quantity: 2, items: [] }));
    }
    throw new Error(`Unexpected request: ${url}`);
  });

  render(
    <StrictMode>
      <AuthProvider>
        <CartProvider>
          <RestorationProbe />
        </CartProvider>
      </AuthProvider>
    </StrictMode>,
  );

  await screen.findByText("restoration_error");
  expect(screen.queryByText("anonymous")).not.toBeInTheDocument();
  expect(sessionStorage.getItem("exon.refreshToken")).toBeNull();
  expect(cartCalls).toHaveLength(0);

  await userEvent.click(screen.getByRole("button", { name: "Retry session" }));

  await screen.findByText("authenticated");
  await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
  expect(sessionStorage.getItem("exon.refreshToken")).toBeNull();
  expect(refreshCalls).toHaveLength(2);
  expect(cartCalls.length).toBeGreaterThan(0);
  expect(cartCalls[0].headers.Authorization).toBe("Bearer restored-access");
});

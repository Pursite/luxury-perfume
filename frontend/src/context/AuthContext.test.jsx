import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { request } from "../api/client";
import { clearTokens, setTokens } from "../api/tokenStore";
import useAuth from "../hooks/useAuth";
import { AuthProvider } from "./AuthContext";

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

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("fetch", vi.fn());
});

test("returns the application to anonymous state when an active session cannot refresh", async () => {
  setTokens({ access: "expired-access", refresh: "initial-refresh" });
  fetch
    .mockResolvedValueOnce(jsonResponse({ access: "active-access", refresh: "active-refresh" }))
    .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
    .mockResolvedValueOnce(jsonResponse({ detail: "refresh invalid" }, 401));

  render(<AuthProvider><SessionProbe /></AuthProvider>);
  await screen.findByText("authenticated");

  await userEvent.click(screen.getByRole("button", { name: "Load protected data" }));

  await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
});

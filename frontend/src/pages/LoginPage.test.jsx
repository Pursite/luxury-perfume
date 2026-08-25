import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AuthProvider } from "../context/AuthContext";
import { clearTokens } from "../api/tokenStore";
import LoginPage from "./LoginPage";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function SignupDestination() {
  const location = useLocation();
  return (
    <div>
      <h1>Create your account</h1>
      <span data-testid="signup-return-to">{location.state?.returnTo}</span>
    </div>
  );
}

function renderLogin() {
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: "/login", state: { returnTo: "/cart" } }]}
    >
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupDestination />} />
          <Route path="/cart" element={<h1>Your cart</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

test("logs in with username and password and returns to the intended page", async () => {
  const user = userEvent.setup();
  fetch.mockResolvedValue(jsonResponse({
    message: "Login successful.",
    tokens: { access: "access-token", refresh: "refresh-token" },
  }));
  renderLogin();

  await user.type(screen.getByLabelText("Username"), "customer");
  await user.type(screen.getByLabelText("Password"), "correct horse battery staple");
  await user.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByRole("heading", { name: "Your cart" })).toBeInTheDocument();
  expect(sessionStorage.getItem("exon.refreshToken")).toBe("refresh-token");
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/users/login/userpass/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ username: "customer", password: "correct horse battery staple" }),
    }),
  );
});

test("shows a generic accessible authentication error and preserves the username", async () => {
  const user = userEvent.setup();
  fetch.mockResolvedValue(jsonResponse({ detail: "No active account found." }, 401));
  renderLogin();

  await user.type(screen.getByLabelText("Username"), "customer");
  await user.type(screen.getByLabelText("Password"), "wrong-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The username or password is incorrect.");
  expect(screen.getByLabelText("Username")).toHaveValue("customer");
  expect(screen.getByLabelText("Password")).toHaveValue("");
});

test("reveals and remasks the password accessibly", async () => {
  const user = userEvent.setup();
  renderLogin();
  const password = screen.getByLabelText("Password");
  expect(password).toHaveAttribute("type", "password");
  await user.click(screen.getByRole("button", { name: "Show password" }));
  expect(password).toHaveAttribute("type", "text");
  expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();
});

test("links to Signup and preserves the intended return destination", async () => {
  const user = userEvent.setup();
  renderLogin();

  const signupLink = screen.getByRole("link", { name: "Create one" });
  expect(signupLink).toHaveAttribute("href", "/signup");
  await user.click(signupLink);

  expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
  expect(screen.getByTestId("signup-return-to")).toHaveTextContent("/cart");
});

test("keeps SMS sign-in disabled with pointer and keyboard-accessible explanation", async () => {
  const user = userEvent.setup();
  renderLogin();

  const smsButton = screen.getByRole("button", { name: "Sign in with SMS" });
  const wrapper = screen.getByRole("group", { name: "Sign in with SMS, unavailable" });
  expect(smsButton).toBeDisabled();
  expect(screen.getByText("SMS sign-in is not available yet.")).toBeInTheDocument();

  await user.hover(wrapper);
  expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  await user.unhover(wrapper);

  while (document.activeElement !== wrapper) await user.tab();
  expect(wrapper).toHaveFocus();
  expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  await user.click(smsButton);

  expect(fetch).not.toHaveBeenCalled();
});

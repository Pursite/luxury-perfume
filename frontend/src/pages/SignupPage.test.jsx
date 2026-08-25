import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import App from "../App";
import { clearTokens } from "../api/tokenStore";
import { AuthProvider } from "../context/AuthContext";
import { CartProvider } from "../context/CartContext";

const emptyCart = {
  items: [],
  total_quantity: 0,
  total_price: "0.00",
  has_unavailable_items: false,
};

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderSignup(returnTo) {
  const entry = returnTo
    ? { pathname: "/signup", state: { returnTo } }
    : "/signup";
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <CartProvider>
          <App />
        </CartProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => vi.unstubAllGlobals());

test("signs up with the direct username/password contract and synchronizes Cart", async () => {
  const user = userEvent.setup();
  fetch.mockImplementation((url, options = {}) => {
    if (url === "/api/v1/users/signup/") {
      return Promise.resolve(jsonResponse({
        user: { username: "secure_customer" },
        tokens: { access: "signup-access", refresh: "signup-refresh" },
      }, 201));
    }
    if (url === "/api/v1/cart/" && options.method === "GET") {
      return Promise.resolve(jsonResponse(emptyCart));
    }
    throw new Error(`Unexpected request: ${options.method || "GET"} ${url}`);
  });
  renderSignup("/cart");

  await user.type(screen.getByLabelText("Username"), "secure_customer");
  await user.type(screen.getByLabelText("Password"), "CorrectHorseBatteryStaple42!");
  await user.click(screen.getByRole("button", { name: "Create account" }));

  expect(await screen.findByRole("heading", { name: "Your cart is empty" })).toBeInTheDocument();
  const signupRequest = fetch.mock.calls.find(([url]) => url === "/api/v1/users/signup/");
  expect(JSON.parse(signupRequest[1].body)).toEqual({
    username: "secure_customer",
    password: "CorrectHorseBatteryStaple42!",
  });
  expect(sessionStorage.getItem("exon.refreshToken")).toBe("signup-refresh");
  const cartRequest = fetch.mock.calls.find(([url]) => url === "/api/v1/cart/");
  expect(cartRequest[1].headers.Authorization).toBe("Bearer signup-access");
});

test("rejects an unsafe return destination after successful Signup", async () => {
  const user = userEvent.setup();
  fetch.mockImplementation((url) => {
    if (url === "/api/v1/users/signup/") {
      return Promise.resolve(jsonResponse({
        user: { username: "secure_customer" },
        tokens: { access: "signup-access", refresh: "signup-refresh" },
      }, 201));
    }
    if (url === "/api/v1/products/") {
      return Promise.resolve(jsonResponse({
        count: 0,
        total_pages: 1,
        current_page: 1,
        page_size: 12,
        links: { next: null, previous: null },
        results: [],
      }));
    }
    if (url === "/api/v1/cart/") return Promise.resolve(jsonResponse(emptyCart));
    throw new Error(`Unexpected request: ${url}`);
  });
  renderSignup("https://attacker.example/collect");

  await user.type(screen.getByLabelText("Username"), "secure_customer");
  await user.type(screen.getByLabelText("Password"), "CorrectHorseBatteryStaple42!");
  await user.click(screen.getByRole("button", { name: "Create account" }));

  expect(await screen.findByRole("heading", { name: "No fragrances found" })).toBeInTheDocument();
});

test("shows client validation without issuing a Signup request", async () => {
  const user = userEvent.setup();
  renderSignup();

  await user.click(screen.getByRole("button", { name: "Create account" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Enter a username and password.");
  expect(screen.getByLabelText("Username")).toHaveFocus();
  expect(fetch).not.toHaveBeenCalled();
});

test("renders backend Signup field errors and preserves entered values", async () => {
  const user = userEvent.setup();
  fetch.mockResolvedValue(jsonResponse({
    password: ["This password is too common."],
  }, 400));
  renderSignup();

  await user.type(screen.getByLabelText("Username"), "secure_customer");
  await user.type(screen.getByLabelText("Password"), "common-password");
  await user.click(screen.getByRole("button", { name: "Create account" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This password is too common.");
  expect(screen.getByLabelText("Username")).toHaveValue("secure_customer");
  expect(screen.getByLabelText("Password")).toHaveValue("common-password");
});

test("renders the backend's generic nested account-conflict error", async () => {
  const user = userEvent.setup();
  fetch.mockResolvedValue(jsonResponse({
    non_field_errors: {
      non_field_errors: ["Unable to create an account with the provided information."],
    },
  }, 400));
  renderSignup();

  await user.type(screen.getByLabelText("Username"), "secure_customer");
  await user.type(screen.getByLabelText("Password"), "CorrectHorseBatteryStaple42!");
  await user.click(screen.getByRole("button", { name: "Create account" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to create an account with the provided information.",
  );
});

test("links back to Sign In while preserving the return destination", async () => {
  const user = userEvent.setup();
  renderSignup("/cart");

  const loginLink = screen.getByRole("link", { name: "Sign in" });
  expect(loginLink).toHaveAttribute("href", "/login");
  await user.click(loginLink);

  expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
});

test("keeps SMS Signup disabled and never calls an OTP endpoint", async () => {
  const user = userEvent.setup();
  renderSignup();

  const smsButton = screen.getByRole("button", { name: "Sign up with SMS" });
  const wrapper = screen.getByRole("group", { name: "Sign up with SMS, unavailable" });
  expect(smsButton).toBeDisabled();
  expect(screen.getByText("SMS sign-up is not available yet.")).toBeInTheDocument();

  await user.hover(wrapper);
  expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  await user.unhover(wrapper);
  while (document.activeElement !== wrapper) await user.tab();
  expect(wrapper).toHaveFocus();
  expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  await user.click(smsButton);

  expect(fetch).not.toHaveBeenCalled();
  expect(fetch.mock.calls.some(([url]) => /(?:signup|login)\/(?:send|verify)-otp/.test(url))).toBe(false);
});

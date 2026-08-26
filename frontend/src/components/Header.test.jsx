import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";

import Header from "./Header";

const auth = vi.hoisted(() => ({
  status: "anonymous",
  isAuthenticated: false,
  retrySession: vi.fn(),
  logout: vi.fn(),
}));
const cart = vi.hoisted(() => ({
  cart: { items: [], total_quantity: 0, total_price: "0.00", has_unavailable_items: false },
}));

vi.mock("../hooks/useAuth", () => ({ default: () => auth }));
vi.mock("../hooks/useCart", () => ({ default: () => cart }));

function renderHeader(initialEntry = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Header />
      <button type="button" onClick={() => {}}>Outside target</button>
      <Routes>
        <Route path="/" element={<h1>Products destination</h1>} />
        <Route path="/cart" element={<h1>Cart destination</h1>} />
        <Route path="/login" element={<h1>Sign in destination</h1>} />
        <Route path="/account" element={<h1>Account destination</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  auth.status = "anonymous";
  auth.isAuthenticated = false;
  auth.retrySession.mockReset();
  auth.logout.mockReset();
  cart.cart = { items: [], total_quantity: 0, total_price: "0.00", has_unavailable_items: false };
});

test("renders compact direct storefront navigation for anonymous customers", () => {
  renderHeader();

  expect(screen.getByRole("link", { name: "Luxury Perfume home" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Products" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Cart" })).toHaveAttribute("href", "/cart");
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  expect(screen.queryByRole("button", { name: "Menu" })).not.toBeInTheDocument();
});

test("exposes a retry action during transient session restoration failure", async () => {
  auth.status = "restoration_error";
  const user = userEvent.setup();
  renderHeader();

  await user.click(screen.getByRole("button", { name: "Retry session" }));
  expect(auth.retrySession).toHaveBeenCalledOnce();
  expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
});

test("replaces textual authenticated state with the account icon and stable Cart badge", () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  cart.cart = { ...cart.cart, total_quantity: 100 };
  renderHeader();

  expect(screen.getByRole("button", { name: "Account menu" })).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("link", { name: "Cart, 100 items" })).toHaveTextContent("99+");
  expect(screen.getByText("99+")).toHaveAttribute("aria-hidden", "true");
  expect(screen.queryByText("Signed in")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Sign Out" })).not.toBeInTheDocument();
});

test("opens the exact account menu by click and keeps future destinations inert", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();

  await user.click(screen.getByRole("button", { name: "Account menu" }));
  const menu = screen.getByRole("menu", { name: "Account menu" });
  expect(within(menu).getAllByRole("menuitem").map((item) => item.getAttribute("aria-label"))).toEqual([
    "Account Details",
    "Orders",
    "Tickets",
    "Sign Out",
  ]);
  const orders = within(menu).getByRole("menuitem", { name: "Orders" });
  const tickets = within(menu).getByRole("menuitem", { name: "Tickets" });
  expect(orders).toHaveAttribute("aria-disabled", "true");
  expect(tickets).toHaveAttribute("aria-disabled", "true");
  expect(orders.querySelector("button")).toBeDisabled();

  await user.hover(orders);
  expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  await user.click(orders.querySelector("button"));
  expect(screen.getByRole("heading", { name: "Products destination" })).toBeInTheDocument();
  expect(auth.logout).not.toHaveBeenCalled();
});

test("supports roving menu focus and restores the trigger on Escape", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });

  trigger.focus();
  await user.keyboard("{ArrowDown}");
  const accountDetails = screen.getByRole("menuitem", { name: "Account Details" });
  await waitFor(() => expect(accountDetails).toHaveFocus());
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("menuitem", { name: "Orders" })).toHaveFocus();
  await user.keyboard("{End}");
  expect(screen.getByRole("menuitem", { name: "Sign Out" })).toHaveFocus();
  await user.keyboard("{Home}");
  expect(accountDetails).toHaveFocus();
  await user.keyboard("{Escape}");

  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("toggles on repeated taps", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });

  await user.click(trigger);
  expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument();
  await user.click(trigger);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("handles Escape while focus remains on the trigger", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });

  trigger.focus();
  await waitFor(() => expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument());
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test("resets roving focus on a fresh open", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });

  trigger.focus();
  await user.keyboard("{ArrowDown}{End}{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
  await user.click(trigger);
  expect(screen.getByRole("menuitem", { name: "Account Details" })).toHaveAttribute("tabindex", "0");
});

test("closes after the pointer moves outside the account menu", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });
  const outside = screen.getByRole("button", { name: "Outside target" });

  outside.focus();
  await user.hover(trigger);
  expect(screen.getByRole("menu", { name: "Account menu" })).toBeInTheDocument();
  fireEvent.pointerOver(outside);
  await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
});

test("keeps pointer travel open so Account Details remains clickable", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });

  await user.hover(trigger);
  const menu = screen.getByRole("menu", { name: "Account menu" });
  const popup = menu.parentElement;
  expect(popup).toHaveClass("account-menu-popup");
  fireEvent.pointerOver(popup);
  await user.hover(menu);
  expect(menu).toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Account Details" }));
  expect(screen.getByRole("heading", { name: "Account destination" })).toBeInTheDocument();
});

test("lets Tab leave the menu through normal document focus order", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  const user = userEvent.setup();
  renderHeader();
  const trigger = screen.getByRole("button", { name: "Account menu" });

  trigger.focus();
  await user.keyboard("{ArrowDown}");
  await waitFor(() => expect(screen.getByRole("menuitem", { name: "Account Details" })).toHaveFocus());
  await user.tab();

  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Outside target" })).toHaveFocus();
});

test("navigates to Account Details and signs out only once", async () => {
  auth.status = "authenticated";
  auth.isAuthenticated = true;
  auth.logout.mockReturnValue(new Promise(() => {}));
  const user = userEvent.setup();
  const { rerender } = renderHeader();

  await user.click(screen.getByRole("button", { name: "Account menu" }));
  await user.click(screen.getByRole("menuitem", { name: "Account Details" }));
  expect(screen.getByRole("heading", { name: "Account destination" })).toBeInTheDocument();

  rerender(
    <MemoryRouter>
      <Header />
    </MemoryRouter>,
  );
  await user.click(screen.getByRole("button", { name: "Account menu" }));
  const signOut = screen.getByRole("menuitem", { name: "Sign Out" });
  await user.dblClick(signOut);

  expect(auth.logout).toHaveBeenCalledOnce();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

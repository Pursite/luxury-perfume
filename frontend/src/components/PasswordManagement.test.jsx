import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import PasswordManagement from "./PasswordManagement";
import { getAccessToken, setAccessToken, clearTokens } from "../api/tokenStore";
import { AuthContext, anonymousAuth } from "../context/authContext";

const profile = { username: "customer_name", has_usable_password: true, sms_available: false, phone_number: "09123456789" };
function Destination() {
  const location = useLocation();
  return <p>{location.state?.message || "Account restored"}</p>;
}
function renderForm(overrides = {}, recovery = false, recover = vi.fn()) {
  return render(<MemoryRouter initialEntries={["/form"]}>
    <AuthContext.Provider value={{ ...anonymousAuth, recover }}>
      <Routes>
        <Route path="/form" element={<PasswordManagement profile={{ ...profile, ...overrides }} recovery={recovery} />} />
        <Route path="/login" element={<Destination />} />
        <Route path="/account" element={<Destination />} />
      </Routes>
    </AuthContext.Provider>
  </MemoryRouter>);
}
function response(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}
async function fillPassword(user) {
  await user.type(screen.getByLabelText("New password"), "NewStrongPass123!");
  await user.type(screen.getByLabelText("Confirm new password"), "NewStrongPass123!");
}
beforeEach(() => {
  setAccessToken("old-access");
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => { clearTokens(); vi.unstubAllGlobals(); });

test("password accounts can change passwords without SMS and cannot use disabled recovery", () => {
  renderForm();
  expect(screen.getByLabelText("Current password")).toBeInTheDocument();
  expect(screen.queryByText("Forgot password?")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Set Password" })).not.toBeInTheDocument();
});

test("OTP-only accounts show distinct setup and no change or recovery actions", () => {
  renderForm({ has_usable_password: false, sms_available: true });
  expect(screen.getByRole("form", { name: "Set Password" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
  expect(screen.queryByText("Forgot password?")).not.toBeInTheDocument();
});

test("OTP-only setup is unavailable without SMS", () => {
  renderForm({ has_usable_password: false });
  expect(screen.getByRole("button", { name: "Set Password" })).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
});

test("validates current password and confirmation before sending requests", async () => {
  const user = userEvent.setup();
  renderForm();
  await user.type(screen.getByLabelText("New password"), "NewStrongPass123!");
  await user.click(screen.getByRole("button", { name: "Change Password" }));
  expect(screen.getByText("Enter your current password.")).toBeInTheDocument();
  expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

test("displays API field errors and clears sensitive inputs", async () => {
  fetch.mockResolvedValue(response({ current_password: ["Current password is incorrect."] }, 400));
  const user = userEvent.setup();
  renderForm();
  await user.type(screen.getByLabelText("Current password"), "wrong");
  await fillPassword(user);
  await user.click(screen.getByRole("button", { name: "Change Password" }));
  expect(await screen.findByText("Current password is incorrect.")).toBeInTheDocument();
  expect(screen.getByLabelText("Current password")).toHaveValue("");
  expect(screen.getByLabelText("New password")).toHaveValue("");
});

test("changes password once, includes credentials, and clears the old session", async () => {
  let finish;
  fetch.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const user = userEvent.setup();
  renderForm();
  await user.type(screen.getByLabelText("Current password"), "OldStrongPass123!");
  await fillPassword(user);
  const button = screen.getByRole("button", { name: "Change Password" });
  await user.click(button);
  await user.click(button);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith("/api/v1/users/password/change/", expect.objectContaining({
    credentials: "include", method: "POST",
    body: JSON.stringify({ password: "NewStrongPass123!", current_password: "OldStrongPass123!" }),
  }));
  finish(response({ message: "Password changed." }));
  expect(await screen.findByText("Password saved. Sign in with your new password.")).toBeInTheDocument();
  expect(getAccessToken()).toBeNull();
});

test("setup requires sending and entering a fresh code without current password", async () => {
  fetch.mockImplementation(() => Promise.resolve(response({ message: "success" })));
  const user = userEvent.setup();
  renderForm({ has_usable_password: false, sms_available: true });
  await user.click(screen.getByRole("button", { name: "Send verification code" }));
  await user.type(await screen.findByLabelText("Verification code"), "123456");
  await fillPassword(user);
  await user.click(screen.getByRole("button", { name: "Set Password" }));
  expect(await screen.findByText("Password saved. Sign in with your new password.")).toBeInTheDocument();
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/users/password/set/verify/", expect.objectContaining({
    body: JSON.stringify({ password: "NewStrongPass123!", otp: "123456" }),
  }));
});

test("recovery never asks for current password and adopts the recovered session", async () => {
  fetch.mockResolvedValue(response({ message: "requested" }));
  const recover = vi.fn().mockResolvedValue({ tokens: { access: "recovered" } });
  const user = userEvent.setup();
  renderForm({}, true, recover);
  await user.type(screen.getByLabelText("Phone number"), "09123456789");
  await user.click(screen.getByRole("button", { name: "Send verification code" }));
  expect(await screen.findByText("If this account supports recovery, a verification code has been requested.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Verification code"), "123456");
  await fillPassword(user);
  await user.click(screen.getByRole("button", { name: "Reset Password" }));
  await waitFor(() => expect(recover).toHaveBeenCalledWith({ phone_number: "09123456789", otp: "123456", password: "NewStrongPass123!" }));
  expect(await screen.findByText("Account restored")).toBeInTheDocument();
});

test("phone-only accounts must save a username before enabling password sign-in", () => {
  renderForm({ has_usable_password: false, username: null, sms_available: true });
  expect(screen.getByText(/Save a username in Personal Information/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send verification code" })).not.toBeInTheDocument();
});

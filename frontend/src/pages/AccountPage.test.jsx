import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { clearTokens, setAccessToken } from "../api/tokenStore";
import { profileResponse } from "../test/fixtures";
import AccountPage from "./AccountPage";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAccount() {
  return render(
    <MemoryRouter>
      <AccountPage />
    </MemoryRouter>,
  );
}

function deferred() {
  let resolve;
  const promise = new Promise((next) => { resolve = next; });
  return { promise, resolve };
}

beforeEach(() => {
  clearTokens();
  setAccessToken("access-token");
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  clearTokens();
  vi.unstubAllGlobals();
});

test("loads the current profile into the account ledger with backend-owned completion", async () => {
  fetch.mockResolvedValue(jsonResponse({ data: profileResponse }));

  renderAccount();

  expect(screen.getByRole("status", { name: "Loading account details" })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Account Details" })).toBeInTheDocument();
  expect(document.title).toBe("Account Details — Luxury Perfume");
  expect(screen.getByText("Profile incomplete")).toBeInTheDocument();
  expect(screen.getByLabelText("Username")).toHaveValue("customer_name");
  expect(screen.getByLabelText("Email")).toHaveValue("customer@example.com");
  expect(screen.getByLabelText("First name")).toHaveValue("Customer");
  expect(screen.getByLabelText("Last name")).toHaveValue("Name");
  expect(screen.getByText("No verified phone number")).toBeInTheDocument();
  expect(screen.getByLabelText("Address title")).toHaveValue("Home");
  expect(screen.getByLabelText("Full address")).toHaveValue("12 Saffron Street");
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/users/profile/",
    expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({ Authorization: "Bearer access-token" }),
    }),
  );
});

test("shows a retryable profile-read error", async () => {
  fetch
    .mockResolvedValueOnce(jsonResponse({ detail: "Unavailable" }, 503))
    .mockResolvedValueOnce(jsonResponse({ data: profileResponse }));
  const user = userEvent.setup();

  renderAccount();

  expect(await screen.findByRole("heading", { name: "Account details are unavailable." })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByLabelText("Username")).toHaveValue("customer_name");
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("sends only changed personal fields and replaces them with confirmed server data", async () => {
  const confirmed = { ...profileResponse, first_name: "Alexandra" };
  fetch
    .mockResolvedValueOnce(jsonResponse({ data: profileResponse }))
    .mockResolvedValueOnce(jsonResponse({ message: "updated", data: confirmed }));
  const user = userEvent.setup();

  renderAccount();
  const firstName = await screen.findByLabelText("First name");
  await user.clear(firstName);
  await user.type(firstName, "Alex");
  await user.click(screen.getByRole("button", { name: "Save personal information" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Changes saved.");
  expect(firstName).toHaveValue("Alexandra");
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    "/api/v1/users/profile/update/",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({ first_name: "Alex" }),
    }),
  );
});

test("validates personal fields, keeps drafts, and focuses the first invalid field", async () => {
  fetch.mockResolvedValue(jsonResponse({ data: profileResponse }));
  const user = userEvent.setup();

  renderAccount();
  const username = await screen.findByLabelText("Username");
  await user.clear(username);
  await user.type(username, "bad name");
  await user.click(screen.getByRole("button", { name: "Save personal information" }));

  expect(username).toHaveFocus();
  expect(username).toHaveValue("bad name");
  expect(screen.getByText("Use 5–150 ASCII letters, numbers, or underscores.")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("maps server field errors inline and prevents duplicate personal submissions", async () => {
  const update = deferred();
  fetch
    .mockResolvedValueOnce(jsonResponse({ data: profileResponse }))
    .mockImplementationOnce(() => update.promise);
  const user = userEvent.setup();

  renderAccount();
  const email = await screen.findByLabelText("Email");
  await user.clear(email);
  await user.type(email, "next@example.com");
  const save = screen.getByRole("button", { name: "Save personal information" });
  await user.click(save);
  await user.click(save);

  expect(save).toBeDisabled();
  expect(fetch).toHaveBeenCalledTimes(2);
  update.resolve(jsonResponse({ email: ["This email is already taken."] }, 400));
  expect(await screen.findByText("This email is already taken.")).toBeInTheDocument();
  expect(email).toHaveFocus();
  expect(email).toHaveValue("next@example.com");
});

test("creates the first address without an ID", async () => {
  const emptyProfile = { ...profileResponse, addresses: [] };
  const createdAddress = {
    id: "66666666-6666-4666-8666-666666666666",
    title: "Office",
    full_address: "88 Cedar Avenue",
    postal_code: "",
  };
  fetch
    .mockResolvedValueOnce(jsonResponse({ data: emptyProfile }))
    .mockResolvedValueOnce(jsonResponse({ data: { ...emptyProfile, addresses: [createdAddress] } }));
  const user = userEvent.setup();

  renderAccount();
  expect(await screen.findByRole("heading", { name: "Add your first address" })).toBeInTheDocument();
  await user.type(screen.getByLabelText("Address title"), "Office");
  await user.type(screen.getByLabelText("Full address"), "88 Cedar Avenue");
  await user.click(screen.getByRole("button", { name: "Save address" }));

  expect(fetch).toHaveBeenNthCalledWith(
    2,
    "/api/v1/users/profile/update/",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({
        address: { title: "Office", full_address: "88 Cedar Avenue" },
      }),
    }),
  );
  expect(await screen.findByRole("heading", { name: "Office" })).toBeInTheDocument();
});

test("updates addresses by explicit ID without discarding other drafts", async () => {
  const secondAddress = {
    id: "77777777-7777-4777-8777-777777777777",
    title: "Studio",
    full_address: "Old studio",
    postal_code: null,
  };
  const profile = { ...profileResponse, addresses: [...profileResponse.addresses, secondAddress] };
  const confirmed = {
    ...profile,
    addresses: [profileResponse.addresses[0], { ...secondAddress, full_address: "New studio" }],
  };
  fetch
    .mockResolvedValueOnce(jsonResponse({ data: profile }))
    .mockResolvedValueOnce(jsonResponse({ data: confirmed }));
  const user = userEvent.setup();

  renderAccount();
  const firstName = await screen.findByLabelText("First name");
  await user.clear(firstName);
  await user.type(firstName, "Unsaved personal draft");
  const studio = screen.getByRole("group", { name: "Edit Studio address" });
  const fullAddress = within(studio).getByLabelText("Full address");
  await user.clear(fullAddress);
  await user.type(fullAddress, "New studio");
  await user.click(within(studio).getByRole("button", { name: "Save address" }));

  expect(fetch).toHaveBeenNthCalledWith(
    2,
    "/api/v1/users/profile/update/",
    expect.objectContaining({
      body: JSON.stringify({
        address: { id: secondAddress.id, full_address: "New studio" },
      }),
    }),
  );
  expect(firstName).toHaveValue("Unsaved personal draft");
  expect(screen.queryByRole("button", { name: /add another/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
});

test("serializes saves from independent forms so older responses cannot replace newer state", async () => {
  const personalUpdate = deferred();
  const addressUpdate = deferred();
  const confirmedPersonal = { ...profileResponse, first_name: "Alexandra" };
  const confirmedAddress = {
    ...confirmedPersonal,
    addresses: [{ ...profileResponse.addresses[0], full_address: "88 Cedar Avenue" }],
  };
  fetch
    .mockResolvedValueOnce(jsonResponse({ data: profileResponse }))
    .mockImplementationOnce(() => personalUpdate.promise)
    .mockImplementationOnce(() => addressUpdate.promise);
  const user = userEvent.setup();

  renderAccount();
  const firstName = await screen.findByLabelText("First name");
  await user.clear(firstName);
  await user.type(firstName, "Alex");
  await user.click(screen.getByRole("button", { name: "Save personal information" }));

  const fullAddress = screen.getByLabelText("Full address");
  await user.clear(fullAddress);
  await user.type(fullAddress, "88 Cedar Avenue");
  await user.click(screen.getByRole("button", { name: "Save address" }));

  expect(fetch).toHaveBeenCalledTimes(2);
  personalUpdate.resolve(jsonResponse({ data: confirmedPersonal }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  addressUpdate.resolve(jsonResponse({ data: confirmedAddress }));

  await waitFor(() => expect(firstName).toHaveValue("Alexandra"));
  await waitFor(() => expect(fullAddress).toHaveValue("88 Cedar Avenue"));
});

test("keeps phone and password actions genuinely unavailable without making requests", async () => {
  fetch.mockResolvedValue(jsonResponse({ data: profileResponse }));
  const user = userEvent.setup();

  renderAccount();
  const addPhone = await screen.findByRole("button", { name: "Add phone number" });
  const phoneWrapper = screen.getByRole("group", { name: "Add phone number, unavailable" });
  const resetPassword = screen.getByRole("button", { name: "Reset Password" });
  expect(addPhone).toBeDisabled();
  expect(resetPassword).toBeDisabled();

  await user.hover(phoneWrapper);
  expect(screen.getByRole("tooltip")).toHaveTextContent("This feature will be available later.");
  await user.unhover(phoneWrapper);
  await user.click(addPhone);
  await user.click(resetPassword);

  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls.some(([url]) => /otp|password-reset/.test(url))).toBe(false);
});

import { beforeEach, expect, test } from "vitest";

import { clearTokens, getAccessToken, setAccessToken } from "./tokenStore";

beforeEach(() => {
  clearTokens();
  sessionStorage.clear();
  localStorage.clear();
});

test("keeps access tokens in memory without persisting refresh credentials", () => {
  setAccessToken("access-token");

  expect(getAccessToken()).toBe("access-token");
  expect(sessionStorage.length).toBe(0);
  expect(localStorage.length).toBe(0);
});

test("purges the legacy session refresh key", () => {
  sessionStorage.setItem("exon.refreshToken", "legacy-refresh");
  clearTokens();

  expect(sessionStorage.getItem("exon.refreshToken")).toBeNull();
});

import { endSession, request } from "./client";

export function loginWithPassword(credentials) {
  return request("/api/v1/users/login/userpass/", {
    method: "POST",
    body: credentials,
    credentials: "include",
  });
}

export function signupWithPassword(credentials) {
  return request("/api/v1/users/signup/", {
    method: "POST",
    body: credentials,
    credentials: "include",
  });
}

export function logoutSession() {
  return endSession(() => request("/api/v1/users/logout/", {
    method: "POST",
    credentials: "include",
    retryAuth: false,
  }));
}


export function resetPassword(payload) {
  return request("/api/v1/users/password-reset/verify-and-reset/", {
    method: "POST", body: payload, credentials: "include",
  });
}

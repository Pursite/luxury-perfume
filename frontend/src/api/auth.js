import { request } from "./client";

export function loginWithPassword(credentials) {
  return request("/api/v1/users/login/userpass/", {
    method: "POST",
    body: credentials,
  });
}

export function logoutSession(refresh) {
  return request("/api/v1/users/logout/", {
    method: "POST",
    body: { refresh },
    auth: true,
    retryAuth: false,
  });
}

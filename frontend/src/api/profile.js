import { request } from "./client";

export function getCurrentProfile(signal) {
  return request("/api/v1/users/profile/", { auth: true, signal });
}

export function updateProfile(payload) {
  return request("/api/v1/users/profile/update/", {
    method: "PATCH",
    body: payload,
    auth: true,
  });
}

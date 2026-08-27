import {
  clearTokens,
  getAccessToken,
  notifyRestorationError,
  setAccessToken,
} from "./tokenStore";

const configuredBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
let refreshPromise = null;
let logoutInProgress = false;

export class ApiError extends Error {
  constructor(message, { status = 0, data = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export function backendUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${configuredBase}${normalizedPath}`;
}

function errorMessage(data, fallback) {
  if (typeof data?.detail === "string") return data.detail;
  if (typeof data?.message === "string") return data.message;
  if (typeof data?.non_field_errors?.[0] === "string") return data.non_field_errors[0];
  return fallback;
}

async function parseResponse(response) {
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : null;
}

async function fetchResponse(
  path,
  { method = "GET", body, signal, headers = {}, credentials = "same-origin" } = {},
) {
  let response;
  try {
    response = await fetch(backendUrl(path), {
      method,
      signal,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      credentials,
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("The server could not be reached. Check your connection and try again.");
  }

  return response;
}

function responseError(response, data) {
  return new ApiError(errorMessage(data, "The request could not be completed."), {
    status: response.status,
    data,
  });
}

export function withSessionCookieLock(operation) {
  const locks = globalThis.navigator?.locks;
  if (locks?.request) {
    return locks.request("exon-auth-session", { mode: "exclusive" }, operation);
  }
  return operation();
}

export async function refreshSession() {
  if (logoutInProgress) {
    throw new ApiError("Sign out is in progress.");
  }

  if (!refreshPromise) {
    refreshPromise = withSessionCookieLock(async () => {
      const response = await fetchResponse("/api/v1/users/token/refresh/", {
        method: "POST",
        credentials: "include",
      });
      const data = await parseResponse(response);
      if (!response.ok) {
        if (response.status === 401) clearTokens();
        else notifyRestorationError();
        throw responseError(response, data);
      }
      if (typeof data?.access !== "string" || !data.access) {
        notifyRestorationError();
        throw new ApiError("The session could not be restored.");
      }
      setAccessToken(data.access);
      return data.access;
    })
      .catch((error) => {
        if (error.status === 0) notifyRestorationError();
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function endSession(operation) {
  logoutInProgress = true;
  try {
    return await withSessionCookieLock(operation);
  } finally {
    logoutInProgress = false;
  }
}

export async function request(
  path,
  {
    method = "GET",
    body,
    signal,
    headers = {},
    credentials = "same-origin",
    auth = false,
    retryAuth = true,
  } = {},
) {
  const access = auth ? getAccessToken() : null;
  const response = await fetchResponse(path, {
    method,
    body,
    signal,
    headers: {
      ...headers,
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
    },
    credentials,
  });

  const data = await parseResponse(response);
  if (response.status === 401 && auth && retryAuth) {
    const refreshedAccess = await refreshSession();
    if (!refreshedAccess) {
      throw new ApiError("The session could not be restored.");
    }
    return request(path, {
      method,
      body,
      signal,
      headers,
      credentials,
      auth,
      retryAuth: false,
    });
  }
  if (!response.ok) {
    throw responseError(response, data);
  }
  return data;
}

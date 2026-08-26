const REFRESH_TOKEN_KEY = "exon.refreshToken";
let accessToken = null;
const sessionListeners = new Set();

export function getAccessToken() {
  return accessToken;
}

export function getRefreshToken() {
  try {
    return sessionStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setTokens({ access, refresh }) {
  accessToken = access || null;
  try {
    if (refresh) sessionStorage.setItem(REFRESH_TOKEN_KEY, refresh);
    else sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    accessToken = null;
    throw new Error("Browser session storage is unavailable.");
  }
}

export function clearTokens() {
  accessToken = null;
  try {
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // In-memory authentication is still cleared when storage is inaccessible.
  }
  sessionListeners.forEach((listener) => listener());
}

export function subscribeToSessionClear(listener) {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

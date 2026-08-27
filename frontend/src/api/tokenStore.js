const LEGACY_REFRESH_TOKEN_KEY = "exon.refreshToken";
let accessToken = null;
const sessionListeners = new Set();
const restorationErrorListeners = new Set();

try {
  sessionStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
} catch {
  // Storage cleanup is best effort; refresh credentials are never written here.
}

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(access) {
  accessToken = access || null;
}

export function clearTokens() {
  accessToken = null;
  try {
    sessionStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
  } catch {
    // In-memory authentication is still cleared when storage is inaccessible.
  }
  sessionListeners.forEach((listener) => listener());
}

export function subscribeToSessionClear(listener) {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

export function notifyRestorationError() {
  restorationErrorListeners.forEach((listener) => listener());
}

export function subscribeToRestorationError(listener) {
  restorationErrorListeners.add(listener);
  return () => restorationErrorListeners.delete(listener);
}

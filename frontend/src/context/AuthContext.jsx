import { useEffect, useMemo, useState } from "react";

import { loginWithPassword, logoutSession } from "../api/auth";
import { refreshSession } from "../api/client";
import { clearTokens, getRefreshToken, setTokens, subscribeToSessionClear } from "../api/tokenStore";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(getRefreshToken() ? "initializing" : "anonymous");

  useEffect(() => subscribeToSessionClear(() => setStatus("anonymous")), []);

  useEffect(() => {
    if (!getRefreshToken()) return undefined;
    let active = true;
    refreshSession()
      .then(() => { if (active) setStatus("authenticated"); })
      .catch(() => { if (active) setStatus("anonymous"); });
    return () => { active = false; };
  }, []);

  async function login(credentials) {
    const response = await loginWithPassword(credentials);
    setTokens(response.tokens);
    setStatus("authenticated");
    return response;
  }

  async function logout() {
    const refresh = getRefreshToken();
    try {
      if (refresh) await logoutSession(refresh);
    } finally {
      clearTokens();
      setStatus("anonymous");
    }
  }

  const value = useMemo(() => ({
    status,
    isAuthenticated: status === "authenticated",
    login,
    logout,
  }), [status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

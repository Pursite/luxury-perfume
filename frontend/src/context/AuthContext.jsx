import { useCallback, useEffect, useMemo, useState } from "react";

import { loginWithPassword, logoutSession, signupWithPassword } from "../api/auth";
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

  const establishSession = useCallback((response) => {
    setTokens(response.tokens);
    setStatus("authenticated");
    return response;
  }, []);

  const login = useCallback(async (credentials) => {
    return establishSession(await loginWithPassword(credentials));
  }, [establishSession]);

  const signup = useCallback(async (credentials) => {
    return establishSession(await signupWithPassword(credentials));
  }, [establishSession]);

  const logout = useCallback(async () => {
    const refresh = getRefreshToken();
    try {
      if (refresh) await logoutSession(refresh);
    } finally {
      clearTokens();
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo(() => ({
    status,
    isAuthenticated: status === "authenticated",
    login,
    signup,
    logout,
  }), [login, logout, signup, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { loginWithPassword, logoutSession, signupWithPassword } from "../api/auth";
import { refreshSession } from "../api/client";
import { clearTokens, getRefreshToken, setTokens, subscribeToSessionClear } from "../api/tokenStore";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(getRefreshToken() ? "initializing" : "anonymous");
  const [sessionError, setSessionError] = useState("");
  const restoreAttempt = useRef(null);

  useEffect(() => subscribeToSessionClear(() => {
    setSessionError("");
    setStatus("anonymous");
  }), []);

  const restoreSession = useCallback(() => {
    if (restoreAttempt.current) return restoreAttempt.current;
    if (!getRefreshToken()) {
      setSessionError("");
      setStatus("anonymous");
      return Promise.resolve(false);
    }

    setSessionError("");
    setStatus("initializing");
    restoreAttempt.current = refreshSession()
      .then((access) => {
        if (!access) {
          setStatus("anonymous");
          return false;
        }
        setStatus("authenticated");
        return true;
      })
      .catch((error) => {
        if (error.status === 401 || !getRefreshToken()) {
          setSessionError("");
          setStatus("anonymous");
        } else {
          setSessionError("Your session could not be restored. Check your connection and try again.");
          setStatus("restoration_error");
        }
        return false;
      })
      .finally(() => {
        restoreAttempt.current = null;
      });
    return restoreAttempt.current;
  }, []);

  useEffect(() => {
    if (getRefreshToken()) Promise.resolve().then(restoreSession);
  }, [restoreSession]);

  const establishSession = useCallback((response) => {
    setTokens(response.tokens);
    setSessionError("");
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
      setSessionError("");
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo(() => ({
    status,
    isAuthenticated: status === "authenticated",
    sessionError,
    login,
    signup,
    logout,
    retrySession: restoreSession,
  }), [login, logout, restoreSession, sessionError, signup, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

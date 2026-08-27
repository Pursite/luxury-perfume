import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { loginWithPassword, logoutSession, signupWithPassword } from "../api/auth";
import { refreshSession } from "../api/client";
import {
  clearTokens,
  setAccessToken,
  subscribeToRestorationError,
  subscribeToSessionClear,
} from "../api/tokenStore";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }) {
  const [status, setStatus] = useState("initializing");
  const [sessionError, setSessionError] = useState("");
  const restoreAttempt = useRef(null);

  useEffect(() => {
    const unsubscribeClear = subscribeToSessionClear(() => {
      setSessionError("");
      setStatus("anonymous");
    });
    const unsubscribeError = subscribeToRestorationError(() => {
      setSessionError("Your session could not be restored. Check your connection and try again.");
      setStatus("restoration_error");
    });
    return () => {
      unsubscribeClear();
      unsubscribeError();
    };
  }, []);

  const restoreSession = useCallback(() => {
    if (restoreAttempt.current) return restoreAttempt.current;
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
        if (error.status === 401) {
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
    Promise.resolve().then(restoreSession);
  }, [restoreSession]);

  const establishSession = useCallback((response) => {
    setAccessToken(response.tokens?.access);
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
    try {
      await logoutSession();
      clearTokens();
      setSessionError("");
      setStatus("anonymous");
    } catch (error) {
      setSessionError("Sign out could not be completed. Check your connection and try again.");
      throw error;
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

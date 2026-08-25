import { createContext } from "react";

export const anonymousAuth = {
  status: "anonymous",
  isAuthenticated: false,
  sessionError: "",
  login: async () => {},
  signup: async () => {},
  logout: async () => {},
  retrySession: async () => false,
};

export const AuthContext = createContext(anonymousAuth);

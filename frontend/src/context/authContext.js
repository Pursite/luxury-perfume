import { createContext } from "react";

export const anonymousAuth = {
  status: "anonymous",
  isAuthenticated: false,
  login: async () => {},
  signup: async () => {},
  logout: async () => {},
};

export const AuthContext = createContext(anonymousAuth);

import { Navigate, useLocation } from "react-router-dom";

import useAuth from "../hooks/useAuth";

export default function ProtectedRoute({ children }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "initializing") {
    return <div className="route-loading" role="status" aria-label="Restoring your session" />;
  }
  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace state={{ returnTo: `${location.pathname}${location.search}` }} />;
  }
  return children;
}

import { useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import DisabledSmsOption from "../components/DisabledSmsOption";
import AuthLayout from "../components/AuthLayout";
import ErrorState from "../components/ErrorState";
import PasswordField from "../components/PasswordField";
import useAuth from "../hooks/useAuth";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { safeInternalPath } from "../utils/navigation";

export default function LoginPage() {
  useDocumentTitle("Sign in");
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const usernameRef = useRef(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (auth.status === "initializing") {
    return <div className="route-loading" role="status" aria-label="Restoring your session" />;
  }
  if (auth.status === "restoration_error") {
    return (
      <ErrorState
        title="Your session could not be restored"
        message={auth.sessionError}
        onRetry={auth.retrySession}
      />
    );
  }

  if (auth.isAuthenticated) {
    return <Navigate to={safeInternalPath(location.state?.returnTo)} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter both your username and password.");
      usernameRef.current?.focus();
      return;
    }

    setSubmitting(true);
    try {
      await auth.login({ username: username.trim(), password });
      navigate(safeInternalPath(location.state?.returnTo), { replace: true });
    } catch (caught) {
      setPassword("");
      setError(
        caught.status === 401
          ? "The username or password is incorrect."
          : "Sign in could not be completed. Check your connection and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      titleId="login-title"
      eyebrow="Private collection"
      title="Welcome back."
      description="Sign in to keep your selected fragrances together."
    >
      <form className="login-form" noValidate onSubmit={handleSubmit}>
          {error ? <div id="login-error" className="form-error" role="alert">{error}</div> : null}
          <label htmlFor="username">Username</label>
          <input
            ref={usernameRef}
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "login-error login-help" : "login-help"}
            onChange={(event) => { setUsername(event.target.value); setError(""); }}
          />
          <label htmlFor="password">Password</label>
          <PasswordField
            id="password"
            autoComplete="current-password"
            value={password}
            invalid={Boolean(error)}
            describedBy={error ? "login-error login-help" : "login-help"}
            onChange={(event) => { setPassword(event.target.value); setError(""); }}
          />
          <p id="login-help" className="form-help">Use the username and password registered with Luxury Perfume.</p>
          <button type="submit" className="button login-submit" disabled={submitting} aria-busy={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
          <DisabledSmsOption label="Sign in with SMS" note="SMS sign-in is not available yet." />
          <p className="auth-account-switch">
            Don&apos;t have an account?{" "}
            <Link
              to="/signup"
              state={{ returnTo: safeInternalPath(location.state?.returnTo) }}
            >
              Create one
            </Link>
          </p>
      </form>
    </AuthLayout>
  );
}

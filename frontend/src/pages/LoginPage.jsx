import { useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

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
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
    <div className="login-page page-frame">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-introduction">
          <p className="eyebrow">Private collection</p>
          <h1 id="login-title">Welcome back.</h1>
          <p>Sign in to keep your selected fragrances together.</p>
        </div>
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
          <div className="password-control">
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "login-error login-help" : "login-help"}
              onChange={(event) => { setPassword(event.target.value); setError(""); }}
            />
            <button
              type="button"
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((value) => !value)}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          <p id="login-help" className="form-help">Use the username and password registered with EXON+.</p>
          <button type="submit" className="button login-submit" disabled={submitting} aria-busy={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}

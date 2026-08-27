import { useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import DisabledSmsOption from "../components/DisabledSmsOption";
import AuthLayout from "../components/AuthLayout";
import ErrorState from "../components/ErrorState";
import PasswordField from "../components/PasswordField";
import useAuth from "../hooks/useAuth";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { safeInternalPath } from "../utils/navigation";

const USERNAME_PATTERN = /^[A-Za-z0-9_]+$/;

function firstMessage(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map(firstMessage).find(Boolean) || "";
  }
  if (value && typeof value === "object") {
    return Object.values(value).map(firstMessage).find(Boolean) || "";
  }
  return "";
}

function responseError(error) {
  const data = error?.data || {};
  for (const field of ["username", "password", "non_field_errors", "detail"]) {
    const message = firstMessage(data[field]);
    if (message) {
      return {
        field: field === "username" || field === "password" ? field : "form",
        message,
      };
    }
  }
  return {
    field: "form",
    message: "Your account could not be created. Check your connection and try again.",
  };
}

export default function SignupPage() {
  useDocumentTitle("Create account");
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const usernameRef = useRef(null);
  const passwordRef = useRef(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const returnTo = safeInternalPath(location.state?.returnTo);

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

  if (auth.isAuthenticated) return <Navigate to={returnTo} replace />;

  function setValidationError(field, message) {
    setError({ field, message });
    (field === "password" ? passwordRef : usernameRef).current?.focus();
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    const normalizedUsername = username.trim();
    if (!normalizedUsername || !password) {
      setValidationError("username", "Enter a username and password.");
      return;
    }
    if (normalizedUsername.length < 5 || normalizedUsername.length > 150 || !USERNAME_PATTERN.test(normalizedUsername)) {
      setValidationError("username", "Use 5 to 150 letters, numbers, or underscores for your username.");
      return;
    }
    if (password.length < 12 || password.length > 128) {
      setValidationError("password", "Use a password between 12 and 128 characters.");
      return;
    }

    setSubmitting(true);
    try {
      await auth.signup({ username: normalizedUsername, password });
      navigate(returnTo, { replace: true });
    } catch (caught) {
      const nextError = responseError(caught);
      setError(nextError);
      if (nextError.field === "username") usernameRef.current?.focus();
      if (nextError.field === "password") passwordRef.current?.focus();
    } finally {
      setSubmitting(false);
    }
  }

  const usernameInvalid = error?.field === "username" || error?.field === "form";
  const passwordInvalid = error?.field === "password" || error?.field === "form";

  return (
    <AuthLayout
      titleId="signup-title"
      eyebrow="Begin your collection"
      title="Create your account."
      description="Save your selected fragrances in one private, personal collection."
    >
      <form className="login-form" noValidate onSubmit={handleSubmit}>
          {error ? <div id="signup-error" className="form-error" role="alert">{error.message}</div> : null}
          <label htmlFor="signup-username">Username</label>
          <input
            ref={usernameRef}
            id="signup-username"
            name="username"
            autoComplete="username"
            minLength="5"
            maxLength="150"
            pattern="[A-Za-z0-9_]+"
            value={username}
            aria-invalid={usernameInvalid}
            aria-describedby={error ? "signup-error signup-username-help" : "signup-username-help"}
            onChange={(event) => { setUsername(event.target.value); setError(null); }}
          />
          <p id="signup-username-help" className="field-help">Use 5–150 letters, numbers, or underscores.</p>
          <label htmlFor="signup-password">Password</label>
          <PasswordField
            ref={passwordRef}
            id="signup-password"
            autoComplete="new-password"
            value={password}
            minLength="12"
            maxLength="128"
            invalid={passwordInvalid}
            describedBy={error ? "signup-error signup-password-help" : "signup-password-help"}
            onChange={(event) => { setPassword(event.target.value); setError(null); }}
          />
          <p id="signup-password-help" className="form-help">
            Use at least 12 characters and avoid common or entirely numeric passwords.
          </p>
          <button type="submit" className="button login-submit" disabled={submitting} aria-busy={submitting}>
            {submitting ? "Creating account…" : "Create account"}
          </button>
          <DisabledSmsOption label="Sign up with SMS" note="SMS sign-up is not available yet." />
          <p className="auth-account-switch">
            Already have an account?{" "}
            <Link to="/login" state={{ returnTo }}>Sign in</Link>
          </p>
      </form>
    </AuthLayout>
  );
}

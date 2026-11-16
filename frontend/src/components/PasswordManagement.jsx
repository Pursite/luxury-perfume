import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { request } from "../api/client";
import { clearTokens } from "../api/tokenStore";
import useAuth from "../hooks/useAuth";
import PasswordField from "./PasswordField";
import UnavailableControl from "./UnavailableControl";

function message(value) {
  return Array.isArray(value) ? value.join(" ") : typeof value === "string" ? value : "";
}

export default function PasswordManagement({ profile, recovery = false }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const mode = recovery ? "recovery" : profile.has_usable_password ? "change" : "setup";
  const [values, setValues] = useState({ current_password: "", password: "", confirmation: "", phone_number: "", otp: "" });
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState("");
  const inFlight = useRef(false);
  const title = mode === "change" ? "Change Password" : mode === "setup" ? "Set Password" : "Reset Password";

  function change(name, value) {
    setValues((current) => ({ ...current, [name]: value }));
    setErrors({});
    setStatus("");
  }

  async function submit(event) {
    event.preventDefault();
    if (inFlight.current) return;
    const sending = mode !== "change" && !sent;
    const next = {};
    if (recovery && !/^09[0-9]{9}$/.test(values.phone_number.trim())) next.phone_number = "Enter an 11-digit phone number beginning with 09.";
    if (!sending) {
      if (mode === "change" && !values.current_password) next.current_password = "Enter your current password.";
      if (!values.password) next.password = "Enter a new password.";
      if (values.password !== values.confirmation) next.confirmation = "Passwords do not match.";
      if (mode !== "change" && !/^[0-9]{6}$/.test(values.otp)) next.otp = "Enter the six-digit verification code.";
    }
    if (Object.keys(next).length) { setErrors(next); return; }
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    try {
      if (sending) {
        await request(recovery ? "/api/v1/users/password-reset/send-otp/" : "/api/v1/users/password/set/send-otp/", {
          method: "POST", auth: !recovery,
          body: recovery ? { phone_number: values.phone_number.trim() } : {},
        });
        setSent(true);
        setStatus(recovery ? "If this account supports recovery, a verification code has been requested." : "Verification code requested.");
      } else {
        const body = { password: values.password };
        if (mode === "change") body.current_password = values.current_password;
        else body.otp = values.otp;
        if (recovery) {
          body.phone_number = values.phone_number.trim();
          await auth.recover(body);
          navigate("/account", { replace: true });
        } else {
          await request(mode === "change" ? "/api/v1/users/password/change/" : "/api/v1/users/password/set/verify/", {
            method: "POST", body, auth: true, credentials: "include", retryAuth: false,
          });
          clearTokens();
          navigate("/login", { replace: true, state: { message: "Password saved. Sign in with your new password." } });
        }
      }
    } catch (caught) {
      const fields = Object.fromEntries(Object.entries(caught.data || {}).map(([key, value]) => [key, message(value)]));
      setErrors({ ...fields, form: fields.detail || fields.non_field_errors || (Object.keys(fields).some((key) => key in values) ? "" : caught.message || "The request could not be completed.") });
    } finally {
      if (!sending) setValues((current) => ({ ...current, current_password: "", password: "", confirmation: "", otp: "" }));
      inFlight.current = false;
      setBusy(false);
    }
  }

  function field(name, label, secret = false) {
    const id = `security-${name}`;
    const errorId = `${id}-error`;
    const props = {
      id, name, value: values[name], disabled: busy,
      maxLength: secret ? 128 : name === "otp" ? 6 : 11,
      autoComplete: secret ? name === "current_password" ? "current-password" : "new-password" : name === "otp" ? "one-time-code" : "tel",
      onChange: (event) => change(name, event.target.value),
    };
    return (
      <div className="account-field">
        <label htmlFor={id}>{label}</label>
        {secret ? <PasswordField {...props} invalid={Boolean(errors[name])} describedBy={errors[name] ? errorId : undefined} /> :
          <input {...props} aria-invalid={Boolean(errors[name])} aria-describedby={errors[name] ? errorId : undefined} />}
        {errors[name] ? <p id={errorId} className="field-error" role="alert">{errors[name]}</p> : null}
      </div>
    );
  }

  if (mode === "setup" && !profile.username) {
    return <p>Save a username in Personal Information before setting a password so you can sign in afterward.</p>;
  }
  if (mode === "setup" && (!profile.sms_available || !profile.phone_number)) {
    return <div><p>Setting a password requires fresh SMS verification, which is not available for this account.</p><UnavailableControl label="Set Password" /></div>;
  }
  return (
    <div>
      <form className="account-personal-form" noValidate onSubmit={submit} aria-label={title}>
        <h3>{title}</h3>
        {recovery ? field("phone_number", "Phone number") : null}
        {mode === "change" ? field("current_password", "Current password", true) : null}
        {mode === "change" || sent ? <>
          {mode !== "change" ? field("otp", "Verification code") : null}
          {field("password", "New password", true)}
          {field("confirmation", "Confirm new password", true)}
        </> : null}
        {errors.form ? <p className="form-error" role="alert">{errors.form}</p> : null}
        {status ? <p role="status">{status}</p> : null}
        <button className="button" type="submit" disabled={busy} aria-busy={busy}>{mode !== "change" && !sent ? "Send verification code" : title}</button>
      </form>
      {mode === "change" && profile.sms_available && profile.phone_number ? <Link to="/forgot-password">Forgot password?</Link> : null}
    </div>
  );
}

import { useRef, useState } from "react";

import { updateProfile } from "../api/profile";
import UnavailableControl from "./UnavailableControl";

const FIELD_ORDER = ["username", "email", "first_name", "last_name"];

function personalValues(profile) {
  return {
    username: profile.username || "",
    email: profile.email || "",
    first_name: profile.first_name || "",
    last_name: profile.last_name || "",
  };
}

function firstMessage(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.find((item) => typeof item === "string") || "";
  return "";
}

export default function AccountDetailsForm({ profile, onProfileChange }) {
  const [baseline, setBaseline] = useState(() => personalValues(profile));
  const [draft, setDraft] = useState(() => personalValues(profile));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);
  const usernameRef = useRef(null);
  const emailRef = useRef(null);
  const firstNameRef = useRef(null);
  const lastNameRef = useRef(null);
  const refs = {
    username: usernameRef,
    email: emailRef,
    first_name: firstNameRef,
    last_name: lastNameRef,
  };

  function change(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: "" }));
    setFormError("");
    setStatus("");
  }

  function validate() {
    const next = {};
    const username = draft.username.trim();
    const email = draft.email.trim();
    if (baseline.username && !username) next.username = "Username cannot be empty.";
    else if (username && !/^[A-Za-z0-9_]{5,150}$/.test(username)) {
      next.username = "Use 5–150 ASCII letters, numbers, or underscores.";
    }
    if (baseline.email && !email) next.email = "Email cannot be empty.";
    if (draft.first_name.length > 50) next.first_name = "First name cannot exceed 50 characters.";
    if (draft.last_name.length > 50) next.last_name = "Last name cannot exceed 50 characters.";
    return next;
  }

  function focusFirst(nextErrors) {
    const field = FIELD_ORDER.find((name) => nextErrors[name]);
    refs[field]?.current?.focus();
  }

  async function submit(event) {
    event.preventDefault();
    if (inFlight.current) return;
    const nextErrors = validate();
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      focusFirst(nextErrors);
      return;
    }

    const normalized = {
      ...draft,
      username: draft.username.trim(),
      email: draft.email.trim(),
    };
    const payload = Object.fromEntries(
      FIELD_ORDER
        .filter((field) => normalized[field] !== baseline[field])
        .map((field) => [field, normalized[field]]),
    );
    if (!Object.keys(payload).length) return;

    inFlight.current = true;
    setSubmitting(true);
    setErrors({});
    setFormError("");
    setStatus("");
    try {
      const response = await updateProfile(payload);
      const confirmed = personalValues(response.data);
      setBaseline(confirmed);
      setDraft(confirmed);
      onProfileChange(response.data);
      setStatus("Changes saved.");
    } catch (caught) {
      const serverErrors = Object.fromEntries(
        FIELD_ORDER
          .map((field) => [field, firstMessage(caught.data?.[field])])
          .filter(([, errorMessage]) => errorMessage),
      );
      setErrors(serverErrors);
      if (Object.keys(serverErrors).length) focusFirst(serverErrors);
      else setFormError(caught.message || "Changes could not be saved. Try again.");
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  function field({ name, label, type = "text", autoComplete }) {
    const errorId = `${name}-error`;
    return (
      <div className="account-field">
        <label htmlFor={name}>{label}</label>
        <input
          ref={refs[name]}
          id={name}
          name={name}
          type={type}
          autoComplete={autoComplete}
          maxLength={name === "username" ? 150 : name.includes("name") ? 50 : undefined}
          value={draft[name]}
          aria-invalid={Boolean(errors[name])}
          aria-describedby={errors[name] ? errorId : undefined}
          onChange={(event) => change(name, event.target.value)}
        />
        {errors[name] ? <p id={errorId} className="field-error">{errors[name]}</p> : null}
      </div>
    );
  }

  return (
    <form className="account-personal-form" noValidate onSubmit={submit}>
      <section className="account-ledger-section" aria-labelledby="personal-heading">
        <div className="account-section-heading">
          <p className="eyebrow">Identity</p>
          <h2 id="personal-heading">Personal Information</h2>
        </div>
        <div className="account-field-grid">
          {field({ name: "username", label: "Username", autoComplete: "username" })}
          {field({ name: "first_name", label: "First name", autoComplete: "given-name" })}
          {field({ name: "last_name", label: "Last name", autoComplete: "family-name" })}
        </div>
      </section>
      <section className="account-ledger-section" aria-labelledby="contact-heading">
        <div className="account-section-heading">
          <p className="eyebrow">Reachability</p>
          <h2 id="contact-heading">Contact</h2>
        </div>
        <div className="account-field-grid account-contact-fields">
          {field({ name: "email", label: "Email", type: "email", autoComplete: "email" })}
          {profile.phone_number ? (
            <div className="account-field">
              <label htmlFor="verified-phone">Verified phone number</label>
              <input id="verified-phone" value={profile.phone_number} readOnly />
            </div>
          ) : (
            <div className="account-phone-missing">
              <p>No verified phone number</p>
              <p>Phone verification is not available yet, but you can save your other details.</p>
              <UnavailableControl label="Add phone number" />
            </div>
          )}
        </div>
      </section>
      {formError ? <p className="form-error" role="alert">{formError}</p> : null}
      <div className="account-form-actions">
        <button type="submit" className="button" disabled={submitting} aria-busy={submitting}>
          Save personal information
        </button>
        {status ? <p className="save-status" role="status">{status}</p> : null}
      </div>
    </form>
  );
}

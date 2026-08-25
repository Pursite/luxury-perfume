import { useId, useRef, useState } from "react";

function values(address) {
  return {
    title: address?.title || "",
    full_address: address?.full_address || "",
    postal_code: address?.postal_code || "",
  };
}

function message(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.find((item) => typeof item === "string") || "";
  return "";
}

export default function AddressEditor({ address, onProfileChange, saveProfile }) {
  const prefix = useId();
  const creating = !address?.id;
  const [baseline, setBaseline] = useState(() => values(address));
  const [draft, setDraft] = useState(() => values(address));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);
  const titleRef = useRef(null);
  const fullAddressRef = useRef(null);
  const postalCodeRef = useRef(null);
  const refs = {
    title: titleRef,
    full_address: fullAddressRef,
    postal_code: postalCodeRef,
  };

  function change(field, nextValue) {
    setDraft((current) => ({ ...current, [field]: nextValue }));
    setErrors((current) => ({ ...current, [field]: "" }));
    setFormError("");
    setStatus("");
  }

  function validate() {
    const next = {};
    if (!draft.title.trim()) next.title = "Title is required.";
    else if (draft.title.trim().length > 50) next.title = "Title cannot exceed 50 characters.";
    if (!draft.full_address.trim()) next.full_address = "Full address is required.";
    if (draft.postal_code.length > 10) next.postal_code = "Postal code cannot exceed 10 characters.";
    return next;
  }

  function focusFirst(nextErrors) {
    const field = ["title", "full_address", "postal_code"].find((name) => nextErrors[name]);
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
      title: draft.title.trim(),
      full_address: draft.full_address.trim(),
      postal_code: draft.postal_code.trim(),
    };
    const changed = creating
      ? Object.fromEntries(Object.entries(normalized).filter(([, value]) => value !== ""))
      : Object.fromEntries(
        Object.entries(normalized).filter(([field, value]) => value !== baseline[field]),
      );
    if (!creating && !Object.keys(changed).length) return;
    const addressPayload = creating ? changed : { id: address.id, ...changed };

    inFlight.current = true;
    setSubmitting(true);
    setErrors({});
    setFormError("");
    setStatus("");
    try {
      const response = await saveProfile({ address: addressPayload });
      const confirmed = creating
        ? response.data.addresses[0]
        : response.data.addresses.find((item) => item.id === address.id);
      if (confirmed) {
        const confirmedValues = values(confirmed);
        setBaseline(confirmedValues);
        setDraft(confirmedValues);
      }
      onProfileChange(response.data);
      setStatus("Changes saved.");
    } catch (caught) {
      const addressErrors = caught.data?.address;
      const serverErrors = typeof addressErrors === "object" && !Array.isArray(addressErrors)
        ? Object.fromEntries(
          ["title", "full_address", "postal_code"]
            .map((field) => [field, message(addressErrors[field])])
            .filter(([, errorMessage]) => errorMessage),
        )
        : {};
      setErrors(serverErrors);
      if (Object.keys(serverErrors).length) focusFirst(serverErrors);
      else setFormError(message(addressErrors) || caught.message || "The address could not be saved.");
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  function input({ field, label, textarea = false, autoComplete }) {
    const id = `${prefix}-${field}`;
    const errorId = `${id}-error`;
    const common = {
      ref: refs[field],
      id,
      name: field,
      value: draft[field],
      autoComplete,
      "aria-invalid": Boolean(errors[field]),
      "aria-describedby": errors[field] ? errorId : undefined,
      onChange: (event) => change(field, event.target.value),
    };
    return (
      <div className={`account-field ${textarea ? "account-field-wide" : ""}`}>
        <label htmlFor={id}>{label}</label>
        {textarea ? (
          <textarea {...common} className="resize-none" rows="5" />
        ) : (
          <input {...common} maxLength={field === "title" ? 50 : 10} />
        )}
        {errors[field] ? <p id={errorId} className="field-error">{errors[field]}</p> : null}
      </div>
    );
  }

  return (
    <form
      className="address-editor"
      role="group"
      aria-label={creating ? "Add your first address" : `Edit ${address.title} address`}
      noValidate
      onSubmit={submit}
    >
      <h3>{creating ? "Add your first address" : address.title}</h3>
      <div className="account-field-grid">
        {input({ field: "title", label: "Address title", autoComplete: "off" })}
        {input({ field: "postal_code", label: "Postal code", autoComplete: "postal-code" })}
        {input({ field: "full_address", label: "Full address", textarea: true, autoComplete: "street-address" })}
      </div>
      {formError ? <p className="form-error" role="alert">{formError}</p> : null}
      <div className="account-form-actions">
        <button type="submit" className="button button-outline" disabled={submitting} aria-busy={submitting}>
          Save address
        </button>
        {status ? <p className="save-status" role="status">{status}</p> : null}
      </div>
    </form>
  );
}

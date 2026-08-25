import UnavailableControl from "./UnavailableControl";

export default function DisabledSmsOption({ label, note }) {
  return (
    <div className="auth-secondary-option">
      <div className="auth-divider" aria-hidden="true"><span>Or</span></div>
      <UnavailableControl
        label={label}
        className="auth-disabled-wrapper"
        buttonClassName="button button-outline auth-sms-button"
      />
      <p className="auth-unavailable-note">{note}</p>
    </div>
  );
}

import { forwardRef, useState } from "react";

const PasswordField = forwardRef(function PasswordField({
  id,
  name = "password",
  value,
  onChange,
  autoComplete,
  describedBy,
  invalid,
  minLength,
  maxLength,
}, ref) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="password-control">
      <input
        ref={ref}
        id={id}
        name={name}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        minLength={minLength}
        maxLength={maxLength}
        aria-invalid={invalid}
        aria-describedby={describedBy}
        onChange={onChange}
      />
      <button
        type="button"
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? "Hide" : "Show"}
      </button>
    </div>
  );
});

export default PasswordField;

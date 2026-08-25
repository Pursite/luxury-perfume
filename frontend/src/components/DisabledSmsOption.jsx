import { useId, useState } from "react";

const TOOLTIP = "This feature will be available later.";

export default function DisabledSmsOption({ label, note }) {
  const tooltipId = useId();
  const [tooltipVisible, setTooltipVisible] = useState(false);

  return (
    <div className="auth-secondary-option">
      <div className="auth-divider" aria-hidden="true"><span>Or</span></div>
      <div
        className="auth-disabled-wrapper"
        role="group"
        aria-label={`${label}, unavailable`}
        aria-describedby={tooltipId}
        tabIndex="0"
        onMouseEnter={() => setTooltipVisible(true)}
        onMouseLeave={() => setTooltipVisible(false)}
        onFocus={() => setTooltipVisible(true)}
        onBlur={() => setTooltipVisible(false)}
      >
        <button type="button" className="button button-outline auth-sms-button" disabled>
          {label}
        </button>
        <span
          id={tooltipId}
          className="auth-disabled-tooltip"
          role="tooltip"
          aria-hidden={!tooltipVisible}
        >
          {TOOLTIP}
        </span>
      </div>
      <p className="auth-unavailable-note">{note}</p>
    </div>
  );
}

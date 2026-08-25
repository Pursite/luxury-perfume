import { useId, useState } from "react";

export const UNAVAILABLE_TOOLTIP = "This feature will be available later.";

export default function UnavailableControl({
  label,
  className = "",
  buttonClassName = "button button-outline",
  role = "group",
  tabIndex = 0,
  ariaLabel = `${label}, unavailable`,
  onKeyDown,
}) {
  const tooltipId = useId();
  const [tooltipVisible, setTooltipVisible] = useState(false);

  return (
    <div
      className={`unavailable-control ${className}`.trim()}
      role={role}
      aria-label={ariaLabel}
      aria-disabled="true"
      aria-describedby={tooltipId}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setTooltipVisible(true)}
      onMouseLeave={() => setTooltipVisible(false)}
      onFocus={() => setTooltipVisible(true)}
      onBlur={() => setTooltipVisible(false)}
    >
      <button type="button" className={buttonClassName} disabled tabIndex="-1">
        {label}
      </button>
      <span
        id={tooltipId}
        className="unavailable-tooltip"
        role="tooltip"
        aria-hidden={!tooltipVisible}
      >
        {UNAVAILABLE_TOOLTIP}
      </span>
    </div>
  );
}

import { forwardRef, useId, useState } from "react";

export const UNAVAILABLE_TOOLTIP = "This feature will be available later.";

const UnavailableControl = forwardRef(function UnavailableControl({
  label,
  className = "",
  buttonClassName = "button button-outline",
  role = "group",
  tabIndex = 0,
  ariaLabel = `${label}, unavailable`,
  onKeyDown,
  onFocus,
  onBlur,
  onMouseEnter,
  onMouseLeave,
  ...wrapperProps
}, ref) {
  const tooltipId = useId();
  const [tooltipVisible, setTooltipVisible] = useState(false);

  return (
    <div
      ref={ref}
      className={`unavailable-control ${className}`.trim()}
      role={role}
      aria-label={ariaLabel}
      aria-disabled="true"
      aria-describedby={tooltipId}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
      onMouseEnter={(event) => {
        setTooltipVisible(true);
        onMouseEnter?.(event);
      }}
      onMouseLeave={(event) => {
        setTooltipVisible(false);
        onMouseLeave?.(event);
      }}
      onFocus={(event) => {
        setTooltipVisible(true);
        onFocus?.(event);
      }}
      onBlur={(event) => {
        setTooltipVisible(false);
        onBlur?.(event);
      }}
      {...wrapperProps}
    >
      <button type="button" className={buttonClassName} disabled tabIndex="-1" aria-hidden={role === "menuitem"}>
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
});

export default UnavailableControl;

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function ConfirmAction({ triggerLabel, title, description, confirmLabel, onConfirm, busy }) {
  const [open, setOpen] = useState(false);
  const [actionError, setActionError] = useState("");
  const triggerRef = useRef(null);
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const root = document.getElementById("root");
    const trigger = triggerRef.current;
    root?.setAttribute("inert", "");
    cancelRef.current?.focus();

    function handleKeydown(event) {
      if (event.key === "Escape" && !busy) {
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll("button:not(:disabled)") || [];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeydown);
    return () => {
      root?.removeAttribute("inert");
      document.removeEventListener("keydown", handleKeydown);
      trigger?.focus();
    };
  }, [busy, open]);

  async function confirm() {
    setActionError("");
    try {
      await onConfirm();
      setOpen(false);
    } catch (error) {
      setActionError(error.message || "The action could not be completed. Try again.");
    }
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="clear-cart-button"
        onClick={() => { setActionError(""); setOpen(true); }}
        disabled={busy}
      >
        {triggerLabel}
      </button>
      {open ? createPortal(
        <div className="dialog-backdrop">
          <section
            ref={dialogRef}
            className="confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby={actionError ? "confirm-description confirm-error" : "confirm-description"}
          >
            <p className="eyebrow">Please confirm</p>
            <h2 id="confirm-title">{title}</h2>
            <p id="confirm-description">{description}</p>
            {actionError ? <p id="confirm-error" className="dialog-error" role="alert">{actionError}</p> : null}
            <div className="dialog-actions">
              <button ref={cancelRef} type="button" className="button button-outline" onClick={() => setOpen(false)} disabled={busy}>
                Keep items
              </button>
              <button type="button" className="button button-danger" onClick={confirm} disabled={busy} aria-busy={busy}>
                {confirmLabel}
              </button>
            </div>
          </section>
        </div>,
        document.body,
      ) : null}
    </>
  );
}

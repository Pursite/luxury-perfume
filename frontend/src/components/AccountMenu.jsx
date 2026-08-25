import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import useAuth from "../hooks/useAuth";
import { AccountIcon } from "./Icons";
import UnavailableControl from "./UnavailableControl";

const LAST_ITEM = 3;

export default function AccountMenu() {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [signingOut, setSigningOut] = useState(false);
  const wrapperRef = useRef(null);
  const triggerRef = useRef(null);
  const accountRef = useRef(null);
  const ordersRef = useRef(null);
  const ticketsRef = useRef(null);
  const signOutRef = useRef(null);
  const itemRefs = [accountRef, ordersRef, ticketsRef, signOutRef];
  const signOutInFlight = useRef(false);
  const restoringTriggerFocus = useRef(false);

  useEffect(() => {
    if (!open) return undefined;
    function closeFromOutside(event) {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeFromOutside);
    return () => document.removeEventListener("pointerdown", closeFromOutside);
  }, [open]);

  function openMenu(focusIndex = null) {
    if (focusIndex !== null) {
      setActiveIndex(focusIndex);
      requestAnimationFrame(() => itemRefs[focusIndex].current?.focus());
    }
    setOpen(true);
  }

  function closeMenu({ restoreFocus = false } = {}) {
    setOpen(false);
    if (restoreFocus) {
      restoringTriggerFocus.current = true;
      requestAnimationFrame(() => {
        triggerRef.current?.focus();
        restoringTriggerFocus.current = false;
      });
    }
  }

  function focusItem(index) {
    setActiveIndex(index);
    itemRefs[index].current?.focus();
  }

  function onTriggerKeyDown(event) {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openMenu(0);
    }
  }

  function onMenuKeyDown(event) {
    const current = itemRefs.findIndex((ref) => ref.current === document.activeElement);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusItem(current < 0 || current === LAST_ITEM ? 0 : current + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusItem(current <= 0 ? LAST_ITEM : current - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusItem(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusItem(LAST_ITEM);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeMenu({ restoreFocus: true });
    }
  }

  async function signOut() {
    if (signOutInFlight.current) return;
    signOutInFlight.current = true;
    setSigningOut(true);
    setOpen(false);
    try {
      await auth.logout();
    } catch {
      // AuthContext still clears the local session in its finally path.
    } finally {
      signOutInFlight.current = false;
      setSigningOut(false);
    }
  }

  return (
    <div
      ref={wrapperRef}
      className="account-menu"
      onMouseEnter={() => openMenu()}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="account-menu-trigger"
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="account-menu-list"
        onFocus={() => {
          if (!restoringTriggerFocus.current) openMenu();
        }}
        onClick={() => openMenu()}
        onKeyDown={onTriggerKeyDown}
      >
        <AccountIcon />
      </button>
      {open ? (
        <div
          id="account-menu-list"
          className="account-menu-list"
          role="menu"
          aria-label="Account menu"
          onKeyDown={onMenuKeyDown}
        >
          <Link
            ref={accountRef}
            to="/account"
            role="menuitem"
            aria-label="Account Details"
            tabIndex={activeIndex === 0 ? 0 : -1}
            onFocus={() => setActiveIndex(0)}
            onClick={() => setOpen(false)}
          >
            Account Details
          </Link>
          <UnavailableControl
            ref={ordersRef}
            label="Orders"
            role="menuitem"
            ariaLabel="Orders"
            className="account-menu-unavailable"
            buttonClassName="account-menu-disabled-button"
            tabIndex={activeIndex === 1 ? 0 : -1}
            onFocus={() => setActiveIndex(1)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") event.preventDefault();
            }}
          />
          <UnavailableControl
            ref={ticketsRef}
            label="Tickets"
            role="menuitem"
            ariaLabel="Tickets"
            className="account-menu-unavailable"
            buttonClassName="account-menu-disabled-button"
            tabIndex={activeIndex === 2 ? 0 : -1}
            onFocus={() => setActiveIndex(2)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") event.preventDefault();
            }}
          />
          <button
            ref={signOutRef}
            type="button"
            role="menuitem"
            aria-label="Sign Out"
            tabIndex={activeIndex === 3 ? 0 : -1}
            disabled={signingOut}
            aria-busy={signingOut}
            onFocus={() => setActiveIndex(3)}
            onClick={signOut}
          >
            Sign Out
          </button>
        </div>
      ) : null}
    </div>
  );
}

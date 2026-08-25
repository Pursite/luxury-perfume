import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import useAuth from "../hooks/useAuth";
import useCart from "../hooks/useCart";

export default function Header() {
  const auth = useAuth();
  const { cart } = useCart();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  async function signOut() {
    setMenuOpen(false);
    await auth.logout();
  }

  return (
    <header className="site-header">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Link className="wordmark" to="/" aria-label="EXON+ home">EXON+</Link>
      <button
        ref={menuButtonRef}
        className="menu-toggle"
        type="button"
        aria-expanded={menuOpen}
        aria-controls="store-navigation"
        onClick={() => setMenuOpen((value) => !value)}
      >
        Menu
      </button>
      <nav id="store-navigation" className={menuOpen ? "store-navigation is-open" : "store-navigation"} aria-label="Storefront">
        <NavLink to="/" onClick={() => setMenuOpen(false)}>Products</NavLink>
        <NavLink className="cart-navigation-link" to="/cart" onClick={() => setMenuOpen(false)}>
          Cart
          {auth.isAuthenticated && cart.total_quantity > 0 ? (
            <span className="cart-badge" aria-label={`${cart.total_quantity} items in cart`}>
              {cart.total_quantity > 99 ? "99+" : cart.total_quantity}
            </span>
          ) : null}
        </NavLink>
        {auth.isAuthenticated ? (
          <>
            <span className="account-state">Signed in</span>
            <button type="button" onClick={signOut}>Sign out</button>
          </>
        ) : (
          <NavLink to="/login" onClick={() => setMenuOpen(false)}>Login</NavLink>
        )}
      </nav>
    </header>
  );
}

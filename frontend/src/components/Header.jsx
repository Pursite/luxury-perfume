import { Link, NavLink } from "react-router-dom";

import useAuth from "../hooks/useAuth";
import useCart from "../hooks/useCart";
import AccountMenu from "./AccountMenu";
import { CartIcon, ProductsIcon } from "./Icons";

export default function Header() {
  const auth = useAuth();
  const { cart } = useCart();

  return (
    <header className="site-header">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Link className="wordmark" to="/" aria-label="Luxury Perfume home">Luxury Perfume</Link>
      <nav className="store-navigation" aria-label="Storefront">
        <NavLink className="navigation-link" to="/" aria-label="Products">
          <span className="navigation-icon"><ProductsIcon /></span>
          <span className="navigation-label">Products</span>
        </NavLink>
        <NavLink className="navigation-link cart-navigation-link" to="/cart" aria-label="Cart">
          <span className="navigation-icon"><CartIcon /></span>
          <span className="navigation-label">Cart</span>
          {auth.isAuthenticated && cart.total_quantity > 0 ? (
            <span className="cart-badge" aria-label={`${cart.total_quantity} items in cart`}>
              {cart.total_quantity > 99 ? "99+" : cart.total_quantity}
            </span>
          ) : null}
        </NavLink>
      </nav>
      <div className="header-account">
        {auth.isAuthenticated ? (
          <AccountMenu />
        ) : (
          <NavLink className="sign-in-link" to="/login">Sign in</NavLink>
        )}
      </div>
    </header>
  );
}

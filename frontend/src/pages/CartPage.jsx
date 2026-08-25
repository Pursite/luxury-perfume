import { useState } from "react";
import { Link } from "react-router-dom";

import ConfirmAction from "../components/ConfirmAction";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import QuantityControl from "../components/QuantityControl";
import useCart from "../hooks/useCart";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { formatMoney } from "../utils/currency";
import { imageSource } from "../utils/images";

function CartLoading() {
  return (
    <div className="cart-loading" role="status" aria-label="Loading cart">
      <span className="sr-only">Loading cart</span>
      <div /><div />
    </div>
  );
}

function CartLine({ item, mutating, updateItem, removeItem }) {
  const [imageFailed, setImageFailed] = useState(false);
  const source = imageSource(item.product.primary_image, true);
  return (
    <article className={!item.available ? "cart-line is-unavailable" : "cart-line"}>
      <Link className="cart-line-image" to={`/products/${item.product.slug}`}>
        {source && !imageFailed ? (
          <img src={source} alt={`${item.product.name} perfume`} onError={() => setImageFailed(true)} />
        ) : <span className="image-fallback" aria-hidden="true">EX+</span>}
      </Link>
      <div className="cart-line-copy">
        <p className="eyebrow">Selected fragrance</p>
        <h2><Link to={`/products/${item.product.slug}`}>{item.product.name}</Link></h2>
        {!item.available ? (
          <div className="cart-unavailable" role="status">
            <strong>Currently unavailable</strong>
            <span>Current stock: {item.available_stock}</span>
          </div>
        ) : <p className="stock-note">Current stock: {item.available_stock}</p>}
        <QuantityControl item={item} disabled={mutating} onUpdate={(quantity) => updateItem(item.product.slug, quantity)} />
      </div>
      <dl className="cart-line-pricing">
        <div><dt>Current unit price</dt><dd>{formatMoney(item.unit_price)}</dd></div>
        <div><dt>Line total</dt><dd>{formatMoney(item.line_total)}</dd></div>
      </dl>
      <button
        type="button"
        className="remove-item-button"
        aria-label={`Remove ${item.product.name}`}
        onClick={() => removeItem(item.product.slug)}
        disabled={mutating}
      >
        Remove
      </button>
    </article>
  );
}

export default function CartPage() {
  useDocumentTitle("Shopping cart");
  const { cart, loading, mutating, error, reload, updateItem, removeItem, clear } = useCart();
  if (loading && !cart.items.length) return <div className="cart-page page-frame"><CartLoading /></div>;
  if (error && !cart.items.length) {
    return <div className="page-frame"><ErrorState title="Your cart could not be loaded" message={error} onRetry={() => reload()} /></div>;
  }
  if (!cart.items.length) {
    return (
      <div className="cart-page page-frame">
        <EmptyState
          title="Your cart is empty"
          action={<Link className="button" to="/">Explore the collection</Link>}
        >
          Your next signature fragrance is waiting in the collection.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="cart-page page-frame">
      <header className="cart-heading">
        <div><p className="eyebrow">Your selection</p><h1>Shopping cart</h1></div>
        <ConfirmAction
          triggerLabel="Clear cart"
          title="Clear your cart?"
          description="Every selected fragrance will be removed. This action cannot be undone."
          confirmLabel="Clear cart permanently"
          onConfirm={clear}
          busy={mutating}
        />
      </header>
      {error ? <div className="cart-inline-error" role="alert">{error}</div> : null}
      {cart.has_unavailable_items ? (
        <div className="cart-availability-notice" role="status">
          One or more fragrances are no longer available in the selected quantity. They remain in your cart for review.
        </div>
      ) : null}
      <section className="cart-lines" aria-label="Cart items">
        {cart.items.map((item) => (
          <CartLine
            key={`${item.product.uuid}-${item.quantity}`}
            item={item}
            mutating={mutating}
            updateItem={updateItem}
            removeItem={removeItem}
          />
        ))}
      </section>
      <aside className="cart-summary" aria-labelledby="cart-summary-title">
        <p className="eyebrow">Current total</p>
        <h2 id="cart-summary-title">Summary</h2>
        <dl>
          <div><dt>Total quantity</dt><dd>{cart.total_quantity}</dd></div>
          <div><dt>Total price</dt><dd>{formatMoney(cart.total_price)}</dd></div>
        </dl>
        <div className="payment-tooltip-wrapper" tabIndex="0" data-payment-tooltip-trigger="true" aria-describedby="payment-tooltip">
          <button type="button" className="button payment-button" disabled>Proceed to Payment</button>
          <span id="payment-tooltip" className="payment-tooltip" role="tooltip">Currently unavailable</span>
        </div>
        <p className="payment-note">Online payments are currently unavailable. Your cart will remain a selection only.</p>
      </aside>
    </div>
  );
}

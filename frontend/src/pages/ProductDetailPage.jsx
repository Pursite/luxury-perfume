import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { getProduct } from "../api/products";
import Availability from "../components/Availability";
import ErrorState from "../components/ErrorState";
import Price from "../components/Price";
import ProductGallery from "../components/ProductGallery";
import useAuth from "../hooks/useAuth";
import useCart from "../hooks/useCart";
import useDocumentTitle from "../hooks/useDocumentTitle";

function displayValue(value) {
  if (value == null || value === "") return null;
  return String(value).replaceAll("_", " ");
}

function Notes({ title, notes }) {
  if (!notes?.length) return null;
  return (
    <section className="note-tier">
      <h3>{title}</h3>
      <ul>{notes.map((note) => <li key={note.uuid}>{note.name}</li>)}</ul>
    </section>
  );
}

function ProductLoading() {
  return (
    <div className="detail-skeleton" role="status" aria-label="Loading product">
      <span className="sr-only">Loading product</span>
      <div className="detail-skeleton-media" />
      <div className="detail-skeleton-copy" />
    </div>
  );
}

function ProductPurchase({ product }) {
  const auth = useAuth();
  const { addItem, mutating } = useCart();
  const navigate = useNavigate();
  const location = useLocation();
  const [quantity, setQuantity] = useState("1");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const unavailable = product.stock <= 0 || !product.is_active;

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!auth.isAuthenticated) {
      navigate("/login", { state: { returnTo: `${location.pathname}${location.search}` } });
      return;
    }
    const value = Number.parseInt(quantity, 10);
    if (!Number.isInteger(value) || value < 1 || value > product.stock) {
      setError(`Choose a quantity between 1 and ${product.stock}.`);
      return;
    }
    try {
      await addItem(product.slug, value);
      setMessage("Added to your cart.");
    } catch (caught) {
      setError(caught.message || "This fragrance could not be added to your cart.");
    }
  }

  return (
    <form className="product-purchase" noValidate onSubmit={submit}>
      <label htmlFor={`add-quantity-${product.slug}`}>Quantity</label>
      <div className="product-purchase-controls">
        <input
          id={`add-quantity-${product.slug}`}
          type="number"
          inputMode="numeric"
          min="1"
          max={product.stock}
          value={quantity}
          disabled={unavailable || mutating}
          onChange={(event) => setQuantity(event.target.value)}
        />
        <button type="submit" className="button" disabled={unavailable || mutating || auth.status === "initializing"} aria-busy={mutating}>
          {unavailable
            ? "Out of stock"
            : auth.isAuthenticated
              ? (mutating ? "Adding…" : "Add to cart")
              : "Sign in to add to cart"}
        </button>
      </div>
      {message ? <p className="purchase-status" role="status" aria-label="Cart update">{message}</p> : null}
      {error ? <p className="purchase-error" role="alert">{error}</p> : null}
    </form>
  );
}

export default function ProductDetailPage() {
  const { slug } = useParams();
  const [state, setState] = useState({ product: null, error: null, request: null });
  const [attempt, setAttempt] = useState(0);
  const request = `${slug}:${attempt}`;
  const loading = state.request !== request;
  const product = loading ? null : state.product;
  const error = loading ? null : state.error;
  useDocumentTitle(product?.name || (error?.status === 404 ? "Fragrance not found" : "Loading fragrance"));

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    async function loadProduct() {
      try {
        const nextProduct = await getProduct(slug, controller.signal);
        if (active) setState({ product: nextProduct, error: null, request });
      } catch (caught) {
        if (active && caught.name !== "AbortError") {
          setState({ product: null, error: caught, request });
        }
      }
    }
    loadProduct();
    return () => {
      active = false;
      controller.abort();
    };
  }, [request, slug]);

  if (loading) return <div className="page-frame"><ProductLoading /></div>;
  if (error?.status === 404) {
    return (
      <div className="page-frame">
        <section className="state-panel" aria-labelledby="missing-product-title">
          <p className="eyebrow">Outside the collection</p>
          <h1 id="missing-product-title">Fragrance not found</h1>
          <p>This fragrance may have moved or is no longer part of the collection.</p>
          <Link className="button button-outline" to="/">Return to the collection</Link>
        </section>
      </div>
    );
  }
  if (error) {
    return (
      <div className="page-frame">
        <ErrorState
          title="This fragrance could not be loaded"
          message="Check your connection and try again."
          onRetry={() => setAttempt((value) => value + 1)}
        />
      </div>
    );
  }

  const details = [
    ["Volume", product.volume_ml ? `${product.volume_ml} ml` : null],
    ["Concentration", displayValue(product.concentration)],
    ["Audience", displayValue(product.target_audience)],
    ["Fragrance family", displayValue(product.fragrance_family)],
    ["Introduced", product.introduction_year],
    ["Origin", displayValue(product.country_of_origin)],
    ["Season", displayValue(product.suitable_season)],
    ["Best worn", displayValue(product.suitable_usage_time)],
  ].filter(([, value]) => value != null);

  return (
    <article className="product-detail page-frame">
      <Link className="back-link" to="/">← The collection</Link>
      <div className="product-detail-hero">
        <ProductGallery images={product.images} productName={product.name} brandName={product.brand?.name} />
        <section className="product-detail-copy" aria-labelledby="product-title">
          <p className="eyebrow">{product.brand?.name || product.category?.name}</p>
          <h1 id="product-title">{product.name}</h1>
          <p className="product-detail-category">{product.category?.name}</p>
          <Price price={product.price} finalPrice={product.final_price} discountPrice={product.discount_price} />
          <Availability stock={product.stock} />
          <ProductPurchase product={product} />
          {product.description ? <p className="product-description">{product.description}</p> : null}
          <dl className="product-specifications">
            {details.map(([name, value]) => (
              <div key={name}><dt>{name}</dt><dd>{value}</dd></div>
            ))}
          </dl>
        </section>
      </div>
      {(product.top_notes?.length || product.middle_notes?.length || product.base_notes?.length) ? (
        <section className="fragrance-pyramid" aria-labelledby="pyramid-title">
          <div className="pyramid-intro">
            <p className="eyebrow">Composition</p>
            <h2 id="pyramid-title">The fragrance pyramid</h2>
          </div>
          <div className="note-tiers">
            <Notes title="Top notes" notes={product.top_notes} />
            <Notes title="Heart notes" notes={product.middle_notes} />
            <Notes title="Base notes" notes={product.base_notes} />
          </div>
        </section>
      ) : null}
    </article>
  );
}

import { useRef, useState } from "react";

export default function QuantityControl({ item, disabled, onUpdate }) {
  const [quantity, setQuantity] = useState(String(item.quantity));
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const inputId = `quantity-${item.product.slug}`;
  const errorId = `${inputId}-error`;

  function submit(event) {
    event.preventDefault();
    const value = Number(quantity);
    if (!Number.isInteger(value) || value < 1 || value > item.available_stock) {
      setError(`Choose a quantity between 1 and ${item.available_stock}.`);
      inputRef.current?.focus();
      return;
    }
    setError("");
    onUpdate(value);
  }

  return (
    <form className="quantity-form" noValidate onSubmit={submit}>
      <label htmlFor={inputId}>Quantity for {item.product.name}</label>
      <div>
        <input
          ref={inputRef}
          id={inputId}
          type="number"
          inputMode="numeric"
          min="1"
          max={item.available_stock}
          value={quantity}
          disabled={disabled || !item.available}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => {
            setQuantity(event.target.value);
            setError("");
          }}
        />
        <button
          type="submit"
          className="button button-outline"
          aria-label={`Update ${item.product.name} quantity`}
          disabled={disabled || !item.available || Number(quantity) === item.quantity}
        >
          Update
        </button>
      </div>
      {error ? <p id={errorId} className="field-error" role="alert">{error}</p> : null}
    </form>
  );
}

import { useState } from "react";

export default function QuantityControl({ item, disabled, onUpdate }) {
  const [quantity, setQuantity] = useState(String(item.quantity));

  function submit(event) {
    event.preventDefault();
    const value = Number.parseInt(quantity, 10);
    if (Number.isInteger(value) && value >= 1 && value <= item.available_stock) {
      onUpdate(value);
    }
  }

  return (
    <form className="quantity-form" noValidate onSubmit={submit}>
      <label htmlFor={`quantity-${item.product.slug}`}>Quantity for {item.product.name}</label>
      <div>
        <input
          id={`quantity-${item.product.slug}`}
          type="number"
          inputMode="numeric"
          min="1"
          max={item.available_stock}
          value={quantity}
          disabled={disabled || !item.available}
          onChange={(event) => setQuantity(event.target.value)}
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
    </form>
  );
}

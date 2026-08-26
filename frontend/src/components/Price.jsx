import { formatMoney } from "../utils/currency";

export default function Price({ price, finalPrice, discountPrice, className = "" }) {
  const discounted = discountPrice != null && String(price) !== String(finalPrice);
  return (
    <p className={`price ${className}`.trim()}>
      {discounted ? <del className="price-original">{formatMoney(price)}</del> : null}
      <span className="price-current">{formatMoney(finalPrice)}</span>
    </p>
  );
}

export default function Availability({ stock, available = stock > 0 }) {
  return (
    <span className={`availability ${available ? "is-available" : "is-unavailable"}`}>
      {available ? `${stock} available` : "Out of stock"}
    </span>
  );
}

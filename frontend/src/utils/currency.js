export function formatMoney(value) {
  if (value == null || value === "") return "";
  const [integerPart, decimalPart = ""] = String(value).split(".");
  const sign = integerPart.startsWith("-") ? "-" : "";
  const digits = sign ? integerPart.slice(1) : integerPart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const meaningfulDecimal = decimalPart.replace(/0+$/, "");
  return `${sign}${grouped}${meaningfulDecimal ? `.${meaningfulDecimal}` : ""} toman`;
}

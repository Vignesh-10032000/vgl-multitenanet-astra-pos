/** Old menus identify parcel dishes by category; explicit owner choices take priority. */
export function productMenuType(product) {
  return product.menu_type ?? (/parcel/i.test(product.category) ? "parcel" : "regular");
}

export function validateMenuType(value) {
  if (!["regular", "parcel"].includes(value))
    throw new Error("Choose Regular or Parcel");
  return value;
}

/** Normalize a fixed portion weight exactly, with gram precision. */
export function kilograms(value) {
  const source = String(value).trim();
  if (!/^\d{1,4}(?:\.\d{1,3})?$/.test(source))
    throw new Error("Enter kilograms with at most three decimal places");
  const [whole, fraction = ""] = source.split(".");
  const grams = BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, "0"));
  if (grams <= 0n || grams > 9999000n)
    throw new Error("Kilograms must be between 0.001 and 9999");
  const decimals = String(grams % 1000n).padStart(3, "0").replace(/0+$/, "");
  return `${grams / 1000n}${decimals ? "." + decimals : ""}`;
}

/** Read old fixed kg labels without rewriting their saved spelling. */
export function portionKilograms(portion = "") {
  const value = portion.trim().match(/^(\d+(?:\.\d+)?|[13]\/[24])\s*kg$/i)?.[1];
  if (!value) return "";
  const fractions = { "1/2": "0.5", "1/4": "0.25", "3/4": "0.75", "3/2": "1.5" };
  return kilograms(fractions[value] || value);
}

export function fixedKgPortion(value, portion) {
  if (value === undefined || String(value).trim() === "") return portion;
  const normalized = kilograms(value);
  return portionKilograms(portion) === normalized ? portion : `${normalized} kg`;
}

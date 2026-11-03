/** Exact integer-paise arithmetic; BigInt prevents intermediate multiplication loss. */
export function integer(
  value,
  name = "Amount",
  minimum = 0,
  maximum = 100000000000,
) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum)
    throw new Error(`${name} is invalid`);
  return value;
}

export function paise(text) {
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(String(text).trim()))
    throw new Error("Enter a valid amount with at most two decimal places");
  const [whole, fraction = ""] = String(text).trim().split(".");
  return integer(
    Number(BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"))),
  );
}

export function decimal(amount) {
  integer(Math.abs(amount));
  const n = BigInt(Math.abs(amount));
  return `${amount < 0 ? "-" : ""}${n / 100n}.${String(n % 100n).padStart(2, "0")}`;
}
export const money = (amount) => `₹${decimal(amount)}`;
/** Format total or split GST percentages without binary fractional arithmetic. */
export function percent(basisPoints, parts = 1) {
  integer(basisPoints, "GST rate", 0, 2800);
  integer(parts, "GST components", 1, 2);
  const scaled = BigInt(basisPoints) * (parts === 2 ? 5n : 10n);
  const fraction = String(scaled % 1000n)
    .padStart(3, "0")
    .replace(/0+$/, "");
  return `${scaled / 1000n}${fraction ? "." + fraction : ""}`;
}

/** Secure UUIDs also work on Android 11 WebViews predating crypto.randomUUID. */
export function operationId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const s = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}
export function halfUp(n, d) {
  return Number((BigInt(n) * 2n + BigInt(d)) / (BigInt(d) * 2n));
}

export function dayAt(iso = new Date().toISOString()) {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) throw new Error("Invalid date");
  return new Date(date.getTime() + 19800000).toISOString().slice(0, 10);
}
export function financialYear(iso) {
  const day = dayAt(iso);
  const year = Number(day.slice(0, 4)) - (Number(day.slice(5, 7)) < 4 ? 1 : 0);
  return `${year}-${String(year + 1).slice(2)}`;
}
export function billNumber(series, fy, sequence) {
  if (!/^[A-Z0-9]{1,4}$/.test(series))
    throw new Error("Bill series must be 1–4 letters/numbers");
  integer(sequence, "Financial-year bill count", 1, 999999);
  return `${series}/${fy.slice(2, 4)}${fy.slice(-2)}/${String(sequence).padStart(6, "0")}`;
}
export function dateBounds(from, to) {
  for (const day of [from, to]) {
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(day) ||
      dayAt(`${day}T00:00:00+05:30`) !== day
    )
      throw new Error("Invalid date range");
  }
  if (from > to) throw new Error("From date must be before To date");
  return [
    new Date(`${from}T00:00:00+05:30`).toISOString(),
    new Date(
      new Date(`${to}T00:00:00+05:30`).getTime() + 86400000,
    ).toISOString(),
  ];
}

/** Snapshot the price basis; old settings without a basis retain inclusive arithmetic. */
export function quote(items, discount = 0, settings = {}) {
  if (!Array.isArray(items) || !items.length || items.length > 200)
    throw new Error("Add at least one item (maximum 200 lines)");
  const mode = settings.receipt_mode ?? "training";
  if (!["training", "bill_of_supply", "tax_invoice"].includes(mode))
    throw new Error("Invalid receipt mode");
  const rate =
    mode === "tax_invoice" ? integer(settings.tax_bps, "GST rate", 1, 2800) : 0;
  if (settings.tax_inclusive !== undefined && ![true, false, 0, 1].includes(settings.tax_inclusive))
    throw new Error("Invalid GST price basis");
  const inclusive = settings.tax_inclusive !== false && settings.tax_inclusive !== 0;
  const lines = items.map((item) => {
    const quantity = integer(item.quantity, "Quantity", 1, 9999);
    const unit_paise = integer(item.unit_paise, "Selling price", 1);
    return {
      ...item,
      quantity,
      unit_paise,
      gross_paise: integer(Number(BigInt(quantity) * BigInt(unit_paise))),
    };
  });
  const gross = integer(lines.reduce((n, line) => n + line.gross_paise, 0));
  integer(discount, "Discount", 0, gross);
  let distributed = 0;
  let cumulative = 0;
  for (const line of lines) {
    cumulative += line.gross_paise;
    const allocation = Number(
      (BigInt(discount) * BigInt(cumulative)) / BigInt(gross),
    );
    line.discount_paise = allocation - distributed;
    distributed = allocation;
    const discounted = line.gross_paise - line.discount_paise;
    line.tax_inclusive = inclusive ? 1 : 0;
    line.tax_paise = rate
      ? halfUp(BigInt(discounted) * BigInt(rate), inclusive ? 10000 + rate : 10000)
      : 0;
    line.net_paise = integer(discounted + (inclusive ? 0 : line.tax_paise));
    line.taxable_paise = line.net_paise - line.tax_paise;
    line.cgst_paise = Math.floor(line.tax_paise / 2);
    line.sgst_paise = line.tax_paise - line.cgst_paise;
  }
  const net = integer(lines.reduce((n, line) => n + line.net_paise, 0));
  const total = settings.round_rupee ? halfUp(net, 100) * 100 : net;
  return {
    tax_inclusive: inclusive ? 1 : 0,
    lines,
    gross_paise: gross,
    discount_paise: discount,
    tax_paise: lines.reduce((n, l) => n + l.tax_paise, 0),
    taxable_paise: lines.reduce((n, l) => n + l.taxable_paise, 0),
    cgst_paise: lines.reduce((n, l) => n + l.cgst_paise, 0),
    sgst_paise: lines.reduce((n, l) => n + l.sgst_paise, 0),
    round_paise: total - net,
    total_paise: total,
  };
}

export function payment(total, method, tendered) {
  integer(total);
  if (!["cash", "upi"].includes(method)) throw new Error("Choose Cash or GPay");
  tendered =
    method === "upi" ? total : integer(tendered, "Cash tendered", total);
  return {
    method,
    amount_paise: total,
    tendered_paise: tendered,
    change_paise: tendered - total,
  };
}

/** Validate exact allocations; only Cash may have tendered money above its share. */
export function payments(total, entries) {
  integer(total);
  if (!Array.isArray(entries) || entries.length < 1 || entries.length > 2)
    throw new Error("Choose Cash, GPay, or both");
  if (total === 0 && entries.length > 1)
    throw new Error("Use one payment method for a zero-total bill");
  const seen = new Set();
  const result = entries.map((entry) => {
    if (seen.has(entry.method)) throw new Error("Duplicate payment method");
    seen.add(entry.method);
    const amount = integer(
      entry.amount_paise,
      "Payment share",
      total === 0 ? 0 : 1,
      total,
    );
    const row = payment(amount, entry.method, entry.tendered_paise ?? amount);
    if (
      entry.method === "upi" &&
      entry.tendered_paise != null &&
      entry.tendered_paise !== amount
    )
      throw new Error("GPay received must equal its payment share");
    return row;
  });
  if (result.reduce((sum, row) => sum + row.amount_paise, 0) !== total)
    throw new Error("Cash and GPay shares must equal the bill total");
  return result;
}

export function text(value, name, required = false, max = 160) {
  const result = String(value ?? "").trim();
  if (
    (required && !result) ||
    result.length > max ||
    // Intentional rejection of control characters in user-entered text.
    // eslint-disable-next-line no-control-regex
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(result)
  )
    throw new Error(`${name} is invalid`);
  return result;
}

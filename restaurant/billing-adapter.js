import { decimal, integer, paise, payment, payments, quote } from "./domain.js";

/** Translate the original controller's decimal/string contract at the ledger boundary. */
export function menuProduct(product) {
  return {
    ...product,
    selling_price: decimal(product.price_paise),
    category_id: product.category,
    uom: product.portion,
  };
}

export function ledgerItems(cart) {
  return cart.map(({ product_id, quantity, product }) => {
    if (!/^\d{1,4}(?:\.0{1,3})?$/.test(String(quantity)))
      throw new Error("Choose a whole number of menu portions (1–9999)");
    return {
      product_id,
      quantity: integer(
        Number(String(quantity).split(".")[0]),
        "Quantity",
        1,
        9999,
      ),
      name: product.name,
      portion: product.portion,
      unit_paise: paise(product.selling_price),
    };
  });
}

export function billingQuote(cart, discount, settings) {
  const q = quote(ledgerItems(cart), paise(discount || "0"), settings);
  return {
    gross_amount: decimal(q.gross_paise),
    discount_amount: decimal(q.discount_paise),
    taxable_amount: decimal(q.taxable_paise),
    cgst_amount: decimal(q.cgst_paise),
    sgst_amount: decimal(q.sgst_paise),
    igst_amount: "0.00",
    cess_amount: "0.00",
    round_off: decimal(q.round_paise),
    net_amount: decimal(q.total_paise),
    lines: q.lines.map((line) => ({ total_amount: decimal(line.net_paise) })),
  };
}

export function controllerTenders(totalText, rows) {
  if (
    !Array.isArray(rows) ||
    rows.length < 1 ||
    rows.length > 2 ||
    rows.some((p) => !["CASH", "UPI"].includes(p.method))
  )
    throw new Error("Choose Cash, GPay, or both");
  const total = paise(totalText);
  if (rows.length === 1) {
    const p = rows[0];
    if (p.method === "UPI" && paise(p.amount) !== total)
      throw new Error("GPay amount must equal the bill total");
    return [payment(total, p.method.toLowerCase(), paise(p.amount))];
  }
  const cash = rows.find((p) => p.method === "CASH"),
    upi = rows.find((p) => p.method === "UPI");
  if (!cash || !upi) throw new Error("Choose each payment method only once");
  const upiAmount = paise(upi.amount);
  if (upiAmount > total)
    throw new Error("GPay received exceeds the bill total");
  const cashShare = total - upiAmount;
  const entries = [];
  if (cashShare || total === 0)
    entries.push({
      method: "cash",
      amount_paise: cashShare,
      tendered_paise: paise(cash.amount),
    });
  else if (paise(cash.amount))
    throw new Error("Use one GPay payment or enter the actual cash share");
  if (upiAmount)
    entries.push({
      method: "upi",
      amount_paise: upiAmount,
      tendered_paise: upiAmount,
    });
  return payments(total, entries);
}

export function checkoutInput(
  cart,
  discount,
  customerId,
  operation,
  rows,
  total,
) {
  if (!rows.length || rows.some((p) => !["CASH", "UPI"].includes(p.method)))
    throw new Error("Choose Cash or GPay");
  const input = {
    operation_id: operation,
    items: ledgerItems(cart),
    discount_paise: paise(discount || "0"),
    customer_id: customerId || null,
  };
  if (rows.length === 1)
    return {
      ...input,
      method: rows[0].method.toLowerCase(),
      tendered_paise: rows[0].method === "CASH" ? paise(rows[0].amount) : null,
    };
  return { ...input, payments: controllerTenders(total, rows) };
}

export function billingPaymentPreview(total, rows) {
  const tenders = controllerTenders(total, rows);
  return {
    balance_due: "0.00",
    change_due: decimal(tenders.reduce((n, p) => n + p.change_paise, 0)),
  };
}

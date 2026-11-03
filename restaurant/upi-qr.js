import { decimal, integer, paise } from "./domain.js";

/** Encode only a verified merchant destination; never supply a sample bank account. */
export function merchantPaymentUri(settings, amount, reference = "") {
  integer(amount, "GPay amount", 1);
  if (
    settings.upi_confirmed !== true ||
    !/^[\w.-]+@[\w.-]+$/.test(settings.upi_id || "") ||
    settings.upi_id.length > 120 ||
    typeof settings.upi_payee !== "string" ||
    !settings.upi_payee.trim() ||
    settings.upi_payee.length > 120 ||
    [...settings.upi_payee].some((character) => character.charCodeAt(0) < 32)
  )
    throw new Error(
      "Configure and verify the merchant UPI details in Settings",
    );
  const params = new URLSearchParams({
    pa: settings.upi_id,
    pn: settings.upi_payee,
    am: decimal(amount),
    cu: "INR",
  });
  if (reference) {
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(reference))
      throw new Error("Invalid payment reference");
    params.set("tr", reference);
  }
  return `upi://pay?${params}`;
}

/** A split QR requests the UPI share, independently of cash tendered/change. */
export function paymentQrAmount(totalText, rows) {
  const total = paise(totalText);
  if (
    !Array.isArray(rows) ||
    rows.length < 1 ||
    rows.length > 2 ||
    rows.some((p) => !["CASH", "UPI"].includes(p.method)) ||
    new Set(rows.map((p) => p.method)).size !== rows.length
  )
    throw new Error("Choose GPay, or split Cash + GPay");
  const upi = rows.find((p) => p.method === "UPI");
  if (!upi) throw new Error("Choose GPay to display its payment QR");
  const amount = paise(upi.amount);
  if (!amount || amount > total || (rows.length === 1 && amount !== total))
    throw new Error(
      "Enter a GPay share greater than zero and within the bill total",
    );
  return amount;
}

/** Unconfigured preview is non-payment text, never a payable sample UPI URI. */
export function paymentQrRequest(settings, total, rows, operation) {
  const amount = paymentQrAmount(total, rows);
  const reference = String(operation).replaceAll("-", "");
  const demo = !(
    settings.upi_id &&
    settings.upi_payee &&
    settings.upi_confirmed === true
  );
  return {
    demo,
    amount_paise: amount,
    payee: demo ? settings.name : settings.upi_payee,
    upi_id: demo ? "" : settings.upi_id,
    payload: demo
      ? JSON.stringify({
          format: "vgl-pos-qr-demo",
          payment: false,
          amount: decimal(amount),
          currency: "INR",
          reference,
        })
      : merchantPaymentUri(settings, amount, reference),
  };
}

/** Local bundled encoder: no QR service, network request or payment callback. */
export async function paymentQrImage(payload) {
  const { default: QRCode } = await import("qrcode");
  return QRCode.toDataURL(payload, {
    width: 420,
    margin: 4,
    errorCorrectionLevel: "M",
  });
}

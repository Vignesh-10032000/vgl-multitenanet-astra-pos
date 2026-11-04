import { Capacitor, registerPlugin } from "@capacitor/core";
import { paymentLabel } from "./labels.js";
import { decimal, money, percent } from "./domain.js";
const menuReference = new URL(
  "../resources/references/menu-price-card.jpeg",
  import.meta.url,
).href;

const NativeDocuments = registerPlugin("RestaurantDocuments");
export const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const e = escapeHTML;

export async function receiptHTML(sale, images) {
  const s = sale.identity;
  const tenders = sale.payments || [sale.payment];
  const logo = s.logo ? await images.read(s.logo) : null;
  let qr = "";
  if (s.upi_id && s.upi_confirmed && s.upi_payee) {
    const { default: QRCode } = await import("qrcode");
    const uri = `upi://pay?${new URLSearchParams({ pa: s.upi_id, pn: s.upi_payee, am: decimal(tenders.length > 1 ? tenders.find((p) => p.method === "upi").amount_paise : sale.total_paise), cu: "INR" })}`;
    qr = `<img class="receipt-qr" alt="Merchant UPI payment QR" src="${await QRCode.toDataURL(uri, { width: 300, margin: 2, errorCorrectionLevel: "M" })}"><p class="center">${e(s.upi_payee)}<br>${e(s.upi_id)}</p>`;
  }
  const corrected = sale.adjustments.reduce((n, a) => n + a.amount_paise, 0);
  const cgst = sale.lines.reduce((n, line) => n + line.cgst_paise, 0);
  const sgst = sale.lines.reduce((n, line) => n + line.sgst_paise, 0);
  // Reuse the item table columns so tax figures stay beneath RATE on paper.
  const summaryRow = (key, label, amount) => `<tr data-receipt-total="${key}"><th colspan="2" scope="row">${label}: </th><td class="amount receipt-summary-value">${money(amount)}</td><td></td></tr>`;
  const gst = sale.mode === "tax_invoice"
    ? `${sale.tax_inclusive === 0 ? summaryRow("taxable", "Taxable value", sale.lines.reduce((n, line) => n + line.taxable_paise, 0)) + '<tr><td colspan="4" class="receipt-tax-note">GST added to menu prices</td></tr>' : ""}${summaryRow("cgst", `CGST ${percent(sale.tax_bps, 2)}%`, cgst)}${summaryRow("sgst", `SGST ${percent(sale.tax_bps, 2)}%`, sgst)}` : "";
  const type = sale.mode === "tax_invoice" ? "Tax invoice" : sale.mode === "bill_of_supply" ? "Bill of supply" : "Training receipt";
  const created = new Date(sale.created_at);
  const date = created.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "numeric", year: "numeric" });
  const time = created.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: true });
  // Standard receipts follow the owner's compact reference. Keep settlement facts
  // when they matter (split, GPay or cash change) without adding another sale.
  const settlement = tenders.length > 1 || tenders.some(p => p.method === "upi" || p.change_paise)
    ? `<p class="receipt-settlement">Payment: ${tenders.map(p => `${e(paymentLabel(p.method))}: ${money(p.amount_paise)}${p.method === "cash" && p.change_paise ? `<br>Tendered: ${money(p.tendered_paise)} · Change: ${money(p.change_paise)}` : p.method === "upi" ? "<br>UPI recorded by cashier" : ""}`).join("<br>")}</p>` : "";
  return `<article class="receipt-paper ${s.receipt_font === "mono" ? "mono" : ""}" aria-label="${type}">
    ${sale.mode === "training" ? '<p class="training-banner">TRAINING — NOT FOR LIVE BILLING</p>' : ""}
    <header class="receipt-heading">
      ${logo ? `<img class="receipt-logo" alt="Restaurant logo" src="${e(logo)}">` : s.menu_logo ? menuLogo() : ""}
      <h2>${e(s.name)}</h2>
      <p class="center">${e(s.address).replace(/\n/g, "<br>")}${s.phone ? `<br>Phone: ${e(s.phone)}` : ""}${s.gstin ? `<br>GSTIN: ${e(s.gstin)}` : ""}</p>
    </header>
    <p class="receipt-meta"><strong>Bill: ${e(sale.bill_number)}</strong><br>${e(date)}, ${e(time)}<br>Customer: ${e(sale.customer?.name || "Walk-in")}${sale.customer?.phone ? ` / ${e(sale.customer.phone)}` : ""}</p>
    <table aria-label="Bill items"><colgroup><col class="receipt-item-column"><col class="receipt-qty-column"><col class="receipt-rate-column"><col class="receipt-amount-column"></colgroup><thead><tr><th>ITEM</th><th class="amount">QTY</th><th class="amount">RATE</th><th class="amount">AMOUNT</th></tr></thead><tbody>${sale.lines.map(l => `<tr><td>${e(l.name)}${l.portion ? `<br><span>${e(l.portion)}</span>` : ""}</td><td class="amount">${l.quantity}</td><td class="amount">${decimal(l.unit_paise)}</td><td class="amount">${decimal(l.gross_paise)}</td></tr>`).join("")}</tbody><tfoot class="receipt-breakdown">${summaryRow("discount", "Discount", sale.discount_paise)}${gst}${summaryRow("round", "Round off", sale.round_paise)}</tfoot></table>
    <div class="net"><span>TOTAL</span><span>${money(sale.total_paise)}</span></div>
    ${settlement}
    ${sale.mode === "bill_of_supply" ? '<p class="center">Composition taxable person, not eligible to collect tax on supplies.</p>' : ""}
    ${corrected || sale.adjustments.length ? `<p class="training-banner">${e(sale.adjustments.some(a => a.kind === "void") ? "VOID" : "REFUND RECORDED")} ${money(corrected)}</p>${sale.adjustments.map(a => `<p>${e(a.kind)}: ${money(a.amount_paise)} — ${e(a.reason)}</p>`).join("")}` : ""}
    ${qr}<p class="center receipt-footer">${e(s.footer).replace(/\n/g, "<br>")}</p></article>`;
}
/** Viewport into the supplied original menu photograph; preserves its actual Tamil artwork. */
export function menuLogo() {
  return `<span class="menu-logo"><img src="${menuReference}" alt="Restaurant Tamil logo from supplied menu"></span>`;
}

export async function printSavedReceipt(sale, images, { transport = "usb" } = {}) {
  const html = await receiptHTML(sale, images);
  if (Capacitor.getPlatform() === "android" && transport !== "service") {
    const { printDirectReceipt } = await import("./direct-print.js");
    return printDirectReceipt(html);
  }
  let target = document.querySelector("#print-document");
  if (!target) {
    target = document.createElement("div");
    target.id = "print-document";
    target.hidden = true;
    document.body.append(target);
  }
  target.innerHTML = html;
  await document.fonts.ready;
  await Promise.all(
    [...target.querySelectorAll("img")].map((img) => img.decode()),
  );
  if (Capacitor.isNativePlatform())
    return NativeDocuments.printReceipt({ name: sale.bill_number });
  window.print();
  return {
    state: "submitted",
    detail: "Browser print dialog opened; confirm paper output",
  };
}

export function bytesBase64(bytes) {
  let result = "";
  for (let i = 0; i < bytes.length; i += 16384)
    result += String.fromCharCode(...bytes.subarray(i, i + 16384));
  return btoa(result);
}
export async function saveFile(name, type, bytes) {
  if (typeof bytes === "string") bytes = new TextEncoder().encode(bytes);
  if (Capacitor.isNativePlatform())
    return NativeDocuments.saveDocument({
      name,
      mime: type,
      data: bytesBase64(bytes),
    });
  const blob = new Blob([bytes], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  return { state: "download_requested" };
}

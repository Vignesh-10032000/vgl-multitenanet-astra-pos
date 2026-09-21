import "../css/print.css";

import { ArrowLeft, Printer } from "lucide";

import { whenAppReady } from "./app.js";
import { formatDate, formatMoney, formatQuantity, localizedName, t } from "./i18n.js";
import { getCachedStoreProfile, getOfflineReceipt } from "./offline.js";
import { clearChildren, createCell, registerIcons, showToast } from "./ui.js";

registerIcons({ ArrowLeft, Printer });

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value ?? "—";
}

function applyPaper(paper) {
  const normalized = ["58", "80", "a5"].includes(paper) ? paper : "80";
  const invoice = document.querySelector("#offline-invoice");
  invoice.classList.remove("paper-58", "paper-80", "paper-a5");
  invoice.classList.add(`paper-${normalized}`);
  document.querySelectorAll("[data-paper-value]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.paperValue === normalized);
  });
  localStorage.setItem("vglpos.paper", normalized);
}

function renderLines(entry) {
  const body = document.querySelector("#receipt-lines");
  clearChildren(body);
  entry.cart.forEach((item, index) => {
    const quoteLine = entry.quote.lines[index];
    const row = document.createElement("tr");
    row.append(createCell(localizedName(item.product), item.product.sku));
    for (const value of [
      formatQuantity(item.quantity),
      formatMoney(item.product.selling_price),
      formatMoney(quoteLine.total_amount),
    ]) {
      const cell = createCell(value);
      cell.classList.add("numeric");
      row.append(cell);
    }
    body.append(row);
  });
}

function renderReceipt(entry, profile) {
  setText("#receipt-company", profile?.name || "VGL POS");
  setText("#receipt-legal-name", profile?.legal_name || "");
  setText("#receipt-address", profile?.address || "");
  setText("#receipt-gstin", profile?.gstin || t("receipt.unregistered"));
  setText("#receipt-number", entry.provisional_number);
  setText("#receipt-date", formatDate(entry.created_at, {
    dateStyle: "medium",
    timeStyle: "short",
  }));
  setText("#receipt-customer", entry.payload.customer_id
    ? `#${entry.payload.customer_id}`
    : t("receipt.walk_in"));
  for (const [selector, field] of Object.entries({
    "#receipt-gross": "gross_amount",
    "#receipt-discount": "discount_amount",
    "#receipt-taxable": "taxable_amount",
    "#receipt-cgst": "cgst_amount",
    "#receipt-sgst": "sgst_amount",
    "#receipt-igst": "igst_amount",
    "#receipt-cess": "cess_amount",
    "#receipt-round": "round_off",
    "#receipt-total": "net_amount",
  })) setText(selector, formatMoney(entry.quote[field]));
  renderLines(entry);
  const payments = document.querySelector("#receipt-payments");
  clearChildren(payments);
  entry.payload.payments.forEach((payment) => {
    const row = document.createElement("p");
    row.textContent = `${payment.method}: ${formatMoney(payment.amount)}`;
    payments.append(row);
  });
  document.querySelector("#offline-invoice").setAttribute("aria-busy", "false");
}

async function loadReceipt() {
  const invoice = document.querySelector("#offline-invoice");
  const identifier = location.pathname.split("/").filter(Boolean).at(-1)
    || invoice.dataset.offlineUuid;
  const entry = await getOfflineReceipt(identifier);
  if (!entry) throw new Error("The provisional receipt is not stored on this terminal.");
  if (entry.status === "synced" && entry.sale?.id) {
    location.replace(`/receipt/${entry.sale.id}`);
    return;
  }
  renderReceipt(entry, await getCachedStoreProfile());
}

whenAppReady(() => {
  applyPaper(new URLSearchParams(location.search).get("paper")
    || localStorage.getItem("vglpos.paper") || "80");
  document.querySelectorAll("[data-paper-value]").forEach((button) => {
    button.addEventListener("click", () => applyPaper(button.dataset.paperValue));
  });
  document.querySelector("#print-receipt").addEventListener("click", () => window.print());
  loadReceipt().catch((error) => showToast(error.message, { tone: "danger" }));
});

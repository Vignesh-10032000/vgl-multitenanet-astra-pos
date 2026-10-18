import "../css/print.css";

import { ArrowLeft, Printer } from "lucide";

import { whenAppReady } from "./app.js";
import { formatMoney, formatQuantity, localizedName, t } from "./i18n.js";
import { apiJson } from "./session.js";
import { renderReceiptIdentity, renderReceiptTender } from "./receipt-layout.js";
import { clearChildren, createCell, registerIcons, showToast } from "./ui.js";

registerIcons({ ArrowLeft, Printer });

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value ?? "—";
}

function applyPaper(paper) {
  const normalized = ["58", "80", "a5"].includes(paper) ? paper : "80";
  const invoice = document.querySelector("#invoice");
  invoice.classList.remove("paper-58", "paper-80", "paper-a5");
  invoice.classList.add(`paper-${normalized}`);
  document.querySelectorAll("[data-paper-value]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.paperValue === normalized);
  });
  localStorage.setItem("vglpos.paper", normalized);
}

function renderLines(sale) {
  const body = document.querySelector("#receipt-lines");
  clearChildren(body);
  sale.items.forEach((item) => {
    const row = document.createElement("tr");
    row.append(createCell(localizedName(item), item.sku || `#${item.product_id}`));
    const quantity = createCell(formatQuantity(item.quantity));
    quantity.classList.add("numeric");
    row.append(quantity);
    const rate = createCell(formatMoney(item.unit_price));
    rate.classList.add("numeric");
    row.append(rate);
    const amount = createCell(formatMoney(item.total_amount));
    amount.classList.add("numeric");
    row.append(amount);
    body.append(row);
  });
}

function renderPayments(sale) {
  renderReceiptTender(document.querySelector("#receipt-payments"), sale.payments, sale.net_amount);
}

function renderReceipt(sale, profile) {
  setText("#receipt-company", profile.name);
  setText("#receipt-legal-name", profile.legal_name);
  setText("#receipt-address", profile.address);
  setText("#receipt-gstin", profile.gstin || t("receipt.unregistered"));
  setText("#receipt-number", sale.invoice_number);
  renderReceiptIdentity(sale.created_at, profile);
  setText("#receipt-cashier", `#${sale.cashier_id}`);
  setText("#receipt-customer", sale.customer_id ? `#${sale.customer_id}` : t("receipt.walk_in"));
  setText("#receipt-gross", formatMoney(sale.gross_amount));
  setText("#receipt-discount", formatMoney(sale.discount_amount));
  setText("#receipt-taxable", formatMoney(sale.taxable_amount));
  setText("#receipt-cgst", formatMoney(sale.cgst_amount));
  setText("#receipt-sgst", formatMoney(sale.sgst_amount));
  setText("#receipt-igst", formatMoney(sale.igst_amount));
  setText("#receipt-cess", formatMoney(sale.cess_amount));
  setText("#receipt-round", formatMoney(sale.round_off));
  setText("#receipt-total", formatMoney(sale.net_amount));
  renderLines(sale);
  renderPayments(sale);
  const compliance = document.querySelector("#receipt-compliance");
  if (sale.e_invoice?.irn) {
    setText("#receipt-irn", sale.e_invoice.irn);
    setText("#receipt-ack", sale.e_invoice.ack_number);
    const qr = document.querySelector("#receipt-irp-qr");
    if (sale.e_invoice.qr_data_uri) qr.src = sale.e_invoice.qr_data_uri;
    compliance.hidden = false;
  } else {
    compliance.hidden = true;
  }
  const declaration = document.querySelector("#receipt-composition");
  declaration.textContent = sale.composition_declaration || "";
  declaration.hidden = !sale.composition_declaration;
  document.querySelector("#invoice").setAttribute("aria-busy", "false");
}

async function loadReceipt() {
  const invoice = document.querySelector("#invoice");
  const saleId = invoice.dataset.saleId;
  try {
    const [sale, profile] = await Promise.all([
      apiJson(`/api/v1/sales/${saleId}`),
      apiJson("/api/v1/settings/store-profile"),
    ]);
    renderReceipt(sale, profile);
    if (new URLSearchParams(location.search).get("print") === "1") window.setTimeout(() => window.print(), 100);
  } catch (error) {
    invoice.setAttribute("aria-busy", "false");
    showToast(`${t("errors.receipt")}: ${error.message}`, { tone: "danger", duration: 10000 });
  }
}

whenAppReady(() => {
  const requestedPaper = new URLSearchParams(location.search).get("paper");
  applyPaper(requestedPaper || localStorage.getItem("vglpos.paper") || "80");
  document.querySelectorAll("[data-paper-value]").forEach((button) => {
    button.addEventListener("click", () => applyPaper(button.dataset.paperValue));
  });
  document.querySelector("#print-receipt").addEventListener("click", () => window.print());
  loadReceipt();
});

document.addEventListener("vgl:locale-changed", loadReceipt);

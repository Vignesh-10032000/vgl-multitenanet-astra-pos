import "../css/print.css";

import { ArrowLeft, Printer } from "lucide";

import { whenAppReady } from "./app.js";
import { formatInteger, formatMoney, t } from "./i18n.js";
import { apiJson } from "./session.js";
import { clearChildren, registerIcons, showToast } from "./ui.js";

registerIcons({ ArrowLeft, Printer });

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value ?? "—";
}

function renderPaymentTotals(totals) {
  const container = document.querySelector("#z-payment-totals");
  clearChildren(container);
  Object.entries(totals).sort(([left], [right]) => left.localeCompare(right)).forEach(([method, amount]) => {
    const row = document.createElement("p");
    const label = document.createElement("span");
    label.textContent = method;
    const value = document.createElement("strong");
    value.textContent = formatMoney(amount);
    row.append(label, value);
    container.append(row);
  });
}

function renderReport(report) {
  setText("#z-shift-id", formatInteger(report.shift_id));
  setText("#z-transactions", formatInteger(report.transaction_count));
  setText("#z-gross-sales", formatMoney(report.gross_sales));
  setText("#z-discounts", formatMoney(report.discount_total));
  setText("#z-net-sales", formatMoney(report.net_sales));
  setText("#z-cash-sales", formatMoney(report.cash_sales));
  setText("#z-cash-movements", formatMoney(report.cash_movements));
  setText("#z-expected-cash", formatMoney(report.expected_cash));
  setText("#z-counted-cash", report.counted_cash === null ? "—" : formatMoney(report.counted_cash));
  setText("#z-variance", report.variance === null ? "—" : formatMoney(report.variance));
  setText("#z-voids", `${formatInteger(report.void_count)} · ${formatMoney(report.void_total)}`);
  setText("#z-returns", `${formatInteger(report.return_count)} · ${formatMoney(report.return_total)}`);
  setText("#z-no-sales", formatInteger(report.no_sale_count));
  setText("#z-cgst", formatMoney(report.cgst_amount));
  setText("#z-sgst", formatMoney(report.sgst_amount));
  setText("#z-igst", formatMoney(report.igst_amount));
  setText("#z-cess", formatMoney(report.cess_amount));
  renderPaymentTotals(report.payment_totals);
  document.querySelector("#z-report").setAttribute("aria-busy", "false");
}

async function loadReport() {
  const reportElement = document.querySelector("#z-report");
  try {
    const report = await apiJson(`/api/v1/shifts/${reportElement.dataset.shiftId}/z-report`);
    renderReport(report);
  } catch (error) {
    reportElement.setAttribute("aria-busy", "false");
    showToast(`${t("errors.z_report")}: ${error.message}`, { tone: "danger", duration: 10000 });
  }
}

whenAppReady(() => {
  document.querySelector("#print-z-report").addEventListener("click", () => window.print());
  loadReport();
});

document.addEventListener("vgl:locale-changed", loadReport);

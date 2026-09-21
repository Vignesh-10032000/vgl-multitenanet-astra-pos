import {
  ArrowUpRight,
  BadgePercent,
  ChevronRight,
  IndianRupee,
  Landmark,
  LockKeyhole,
  Receipt,
} from "lucide";

import { renderRevenueBars } from "./charts.js";
import { whenAppReady } from "./app.js";
import { localDateIso } from "./data.js";
import { formatDate, formatInteger, formatMoney, t } from "./i18n.js";
import { apiJson } from "./session.js";
import { clearChildren, createBadge, createCell, registerIcons, showToast } from "./ui.js";

registerIcons({
  ArrowUpRight,
  BadgePercent,
  ChevronRight,
  IndianRupee,
  Landmark,
  LockKeyhole,
  Receipt,
});

function setMetric(name, value) {
  const element = document.querySelector(`[data-metric="${name}"] .metric-value`);
  if (!element) return;
  element.classList.remove("skeleton-line");
  element.textContent = value;
}

function renderSales(sales) {
  const body = document.querySelector("#recent-sales");
  clearChildren(body);
  if (!sales.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = t("sales.empty_title");
    row.append(cell);
    body.append(row);
    return;
  }
  sales.forEach((sale) => {
    const row = document.createElement("tr");
    row.append(createCell(sale.invoice_number));
    row.append(createCell(formatDate(sale.created_at, { hour: "2-digit", minute: "2-digit" })));
    row.append(createCell(sale.payment_method));
    const status = document.createElement("td");
    status.append(createBadge(sale.sale_status, sale.sale_status === "COMPLETED" ? "success" : "danger"));
    row.append(status);
    const amount = createCell(formatMoney(sale.net_amount));
    amount.classList.add("numeric");
    row.append(amount);
    body.append(row);
  });
}

async function loadDashboard() {
  try {
    const date = localDateIso();
    const [summary, revenue, sales] = await Promise.all([
      apiJson(`/api/v1/reports/daily-summary?on_date=${date}`),
      apiJson("/api/v1/reports/revenue?days=7"),
      apiJson(`/api/v1/sales?limit=5&start_date=${date}&end_date=${date}`),
    ]);
    setMetric("net", formatMoney(summary.net_amount));
    setMetric("bills", formatInteger(summary.total_bills));
    setMetric("tax", formatMoney(summary.cgst_amount));
    setMetric("discount", formatMoney(summary.discount_amount));
    renderRevenueBars(document.querySelector("#revenue-chart"), revenue.items);
    renderSales(sales.items);
  } catch (error) {
    showToast(`${t("errors.dashboard")}: ${error.message}`, { tone: "danger", duration: 8000 });
  }
}

whenAppReady(() => {
  document.querySelector("#day-close-button")?.addEventListener("click", () => {
    location.href = "/pos?shiftClose=1";
  });
  loadDashboard();
});
document.addEventListener("vgl:locale-changed", loadDashboard);

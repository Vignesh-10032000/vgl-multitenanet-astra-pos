import {
  ArrowUpRight, BadgeIndianRupee, CalendarDays, ChevronRight, IndianRupee,
  LockKeyhole, Receipt, RefreshCw, TriangleAlert, Wallet,
} from "lucide";

import "../css/dashboard.css";

import { whenAppReady } from "./app.js";
import { renderRevenueBars } from "./charts.js";
import { localDateIso, scaledInteger } from "./data.js";
import { formatDate, formatInteger, formatMoney, formatQuantity, localizedName, t } from "./i18n.js";
import { apiJson, getSession } from "./session.js";
import { clearChildren, createBadge, createCell, registerIcons } from "./ui.js";

registerIcons({ ArrowUpRight, BadgeIndianRupee, CalendarDays, ChevronRight, IndianRupee,
  LockKeyhole, Receipt, RefreshCw, TriangleAlert, Wallet });

let loadSequence = 0;
let lastOverview = null;

function setMetric(name, value) {
  const element = document.querySelector(`[data-metric="${name}"] .metric-value`);
  if (!element) return;
  element.classList.remove("skeleton-line");
  element.textContent = value;
}

function emptyList(container, key) {
  clearChildren(container);
  const message = document.createElement("p");
  message.className = "dashboard-placeholder";
  message.textContent = t(key);
  container.append(message);
}

function renderProducts(products) {
  const container = document.querySelector("#top-products");
  emptyList(container, "dashboard.no_top_products");
  if (!products.length) return;
  clearChildren(container);
  const largest = scaledInteger(products[0].revenue, 2);
  products.forEach((product, index) => {
    const row = document.createElement("div");
    row.className = "dashboard-ranked-item";
    const rank = document.createElement("span");
    rank.className = "dashboard-rank";
    rank.textContent = String(index + 1).padStart(2, "0");
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = localizedName(product);
    const quantity = document.createElement("small");
    quantity.textContent = t("dashboard.units_sold", { quantity: formatQuantity(product.quantity) });
    const progress = document.createElement("div");
    progress.className = "dashboard-progress";
    const fill = document.createElement("span");
    const level = largest > 0n ? Number(scaledInteger(product.revenue, 2) * 10n / largest) : 0;
    fill.className = `dashboard-progress-${Math.max(0, Math.min(10, level))}`;
    progress.append(fill);
    detail.append(name, quantity, progress);
    const amount = document.createElement("b");
    amount.textContent = formatMoney(product.revenue);
    row.append(rank, detail, amount);
    container.append(row);
  });
}

function renderStock(products) {
  const container = document.querySelector("#low-stock");
  emptyList(container, "dashboard.stock_healthy");
  if (!products.length) return;
  clearChildren(container);
  products.forEach((product) => {
    const row = document.createElement("div");
    row.className = "dashboard-stock-item";
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = localizedName(product);
    const sku = document.createElement("small");
    sku.textContent = product.sku;
    detail.append(name, sku);
    const quantity = scaledInteger(product.quantity, 3);
    const status = createBadge(quantity <= 0n ? t("dashboard.out_of_stock") : t("dashboard.stock_left", {
      quantity: formatQuantity(product.quantity),
    }), quantity <= 0n ? "danger" : "warning");
    row.append(detail, status);
    container.append(row);
  });
}

function renderPayments(payments) {
  const container = document.querySelector("#payment-mix");
  emptyList(container, "dashboard.no_payments");
  if (!payments.length) return;
  clearChildren(container);
  payments.forEach((payment) => {
    const row = document.createElement("div");
    row.className = "dashboard-payment-item";
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = payment.payment_method;
    const count = document.createElement("small");
    count.textContent = t("dashboard.payment_bills", { count: formatInteger(payment.transaction_count) });
    detail.append(name, count);
    const amount = document.createElement("b");
    amount.textContent = formatMoney(payment.amount);
    row.append(detail, amount);
    container.append(row);
  });
}

function renderSales(sales) {
  const body = document.querySelector("#recent-sales");
  clearChildren(body);
  if (!sales.length) {
    const row = document.createElement("tr");
    const cell = createCell(t("sales.empty_title"));
    cell.colSpan = 7;
    row.append(cell);
    body.append(row);
    return;
  }
  sales.forEach((sale) => {
    const row = document.createElement("tr");
    const invoice = createCell(sale.invoice_number);
    if (getSession()?.user?.permissions?.includes("sale.view")) {
      const link = document.createElement("a");
      link.href = `/receipt/${sale.id}`;
      link.textContent = sale.invoice_number;
      invoice.replaceChildren(link);
    }
    row.append(invoice, createCell(sale.customer_name || t("dashboard.walk_in")));
    const quantity = createCell(formatQuantity(sale.item_quantity));
    quantity.classList.add("numeric");
    row.append(quantity, createCell(formatDate(sale.created_at, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    })), createCell(sale.payment_method));
    const status = document.createElement("td");
    status.append(createBadge(sale.sale_status, sale.sale_status === "COMPLETED" ? "success" : "danger"));
    const amount = createCell(formatMoney(sale.net_amount));
    amount.classList.add("numeric");
    row.append(status, amount);
    body.append(row);
  });
}

function renderOverview(overview) {
  const summary = overview.summary;
  const amounts = {
    net: summary.net_amount, week: overview.week_sales, month: overview.month_sales,
    average: overview.average_bill, cgst: summary.cgst_amount, sgst: summary.sgst_amount,
    igst: summary.igst_amount, cess: summary.cess_amount, discount: summary.discount_amount,
  };
  Object.entries(amounts).forEach(([key, value]) => setMetric(key, formatMoney(value)));
  const tax = [summary.cgst_amount, summary.sgst_amount, summary.igst_amount, summary.cess_amount]
    .reduce((total, value) => total + scaledInteger(value, 2), 0n);
  setMetric("tax", formatMoney(`${tax / 100n}.${String(tax % 100n).padStart(2, "0")}`));
  setMetric("bills", formatInteger(summary.total_bills));
  setMetric("products", formatInteger(overview.total_products));
  setMetric("customers", formatInteger(overview.total_customers));
  setMetric("low_stock", formatInteger(overview.low_stock_count));
  renderRevenueBars(document.querySelector("#revenue-chart"), overview.revenue);
  renderProducts(overview.top_products);
  renderStock(overview.low_stock);
  renderPayments(overview.payment_mix);
  renderSales(overview.recent_sales);
}

async function loadDashboard() {
  const requestSequence = ++loadSequence;
  const content = document.querySelector("#dashboard-content");
  const button = document.querySelector("#dashboard-refresh");
  const error = document.querySelector("#dashboard-error");
  const selectedDate = document.querySelector("#dashboard-date").value || localDateIso();
  content.setAttribute("aria-busy", "true");
  button.disabled = true;
  error.classList.add("is-hidden");
  try {
    const overview = await apiJson(`/api/v1/reports/dashboard?on_date=${encodeURIComponent(selectedDate)}`, {
      signal: AbortSignal.timeout(20000),
    });
    if (requestSequence !== loadSequence) return;
    lastOverview = overview;
    renderOverview(overview);
  } catch {
    if (requestSequence !== loadSequence) return;
    error.querySelector("span").textContent = t(lastOverview ? "dashboard.refresh_failed" : "dashboard.unavailable");
    error.classList.remove("is-hidden");
    if (!lastOverview) {
      document.querySelectorAll(".metric-value").forEach((element) => {
        element.classList.remove("skeleton-line");
        element.textContent = "—";
      });
      for (const selector of ["#revenue-chart", "#top-products", "#low-stock", "#payment-mix"]) {
        emptyList(document.querySelector(selector), "dashboard.data_unavailable");
      }
      const row = document.createElement("tr");
      const cell = createCell(t("dashboard.data_unavailable"));
      cell.colSpan = 7;
      row.append(cell);
      document.querySelector("#recent-sales").replaceChildren(row);
    }
  } finally {
    if (requestSequence === loadSequence) {
      content.setAttribute("aria-busy", "false");
      button.disabled = false;
    }
  }
}

whenAppReady(() => {
  document.querySelector("#dashboard-date").value = localDateIso();
  document.querySelector("#dashboard-date").addEventListener("change", loadDashboard);
  document.querySelector("#dashboard-refresh").addEventListener("click", loadDashboard);
  document.querySelector("#day-close-button")?.addEventListener("click", () => {
    location.href = "/pos?shiftClose=1";
  });
  loadDashboard();
});

document.addEventListener("vgl:locale-changed", () => {
  if (lastOverview) renderOverview(lastOverview);
});

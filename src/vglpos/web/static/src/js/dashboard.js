import {
  ArrowUpRight,
  BadgeIndianRupee,
  ChartNoAxesCombined,
  IndianRupee,
  Plus,
  Receipt,
  RotateCcw,
  Smartphone,
  Wallet,
} from "lucide";
import "../css/dashboard.css";
import { scaledInteger } from "./data.js";
import { formatMoney, formatQuantity, localizedName } from "./i18n.js";
import {
  clearChildren,
  createBadge,
  createCell,
  registerIcons,
  refreshIcons,
} from "./ui.js";
import { decimal } from "../../../../../../restaurant/domain.js";
import {
  uiLabels as labels,
  metrics,
  paymentLabel,
} from "../../../../../../restaurant/labels.js";

function setMetric(name, value) {
  const element = document.querySelector(
    `[data-metric="${name}"] .metric-value`,
  );
  if (element) element.textContent = value;
}
function emptyList(container) {
  clearChildren(container);
  const message = document.createElement("p");
  message.className = "dashboard-placeholder";
  message.textContent = labels.empty;
  container.append(message);
}
function renderProducts(products) {
  const container = document.querySelector("#top-products");
  emptyList(container);
  if (!products.length) return;
  clearChildren(container);
  const largest = products.reduce(
    (n, p) =>
      scaledInteger(p.revenue, 2) > n ? scaledInteger(p.revenue, 2) : n,
    0n,
  );
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
    quantity.textContent = `${formatQuantity(product.quantity)} × ${product.portion}`;
    const progress = document.createElement("div");
    progress.className = "dashboard-progress";
    const fill = document.createElement("span");
    const level =
      largest > 0n
        ? Number((scaledInteger(product.revenue, 2) * 10n) / largest)
        : 0;
    fill.className = `dashboard-progress-${Math.max(0, Math.min(10, level))}`;
    progress.append(fill);
    detail.append(name, quantity, progress);
    const amount = document.createElement("b");
    amount.textContent = formatMoney(product.revenue);
    row.append(rank, detail, amount);
    container.append(row);
  });
}
function renderPayments(totals) {
  const container = document.querySelector("#payment-mix");
  clearChildren(container);
  for (const method of ["cash", "upi"]) {
    const row = document.createElement("div");
    row.className = "dashboard-payment-item";
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = paymentLabel(method);
    const subtitle = document.createElement("small");
    subtitle.textContent = metrics[`${method}_paise`].ta;
    detail.append(name, subtitle);
    const amount = document.createElement("b");
    amount.textContent = formatMoney(decimal(totals[`${method}_paise`]));
    row.append(detail, amount);
    container.append(row);
  }
}
function renderSales(sales, showReceipt) {
  const body = document.querySelector("#recent-sales");
  clearChildren(body);
  if (!sales.length) {
    const row = document.createElement("tr"),
      cell = createCell(labels.empty);
    cell.colSpan = 6;
    row.append(cell);
    body.append(row);
    return;
  }
  sales.forEach((sale) => {
    const row = document.createElement("tr"),
      invoice = document.createElement("td"),
      button = document.createElement("button");
    button.type = "button";
    button.className = "text-button";
    button.textContent = sale.bill_number;
    button.addEventListener("click", () => showReceipt(sale.id));
    invoice.append(button);
    const status = document.createElement("td");
    status.append(
      createBadge(
        sale.has_void
          ? labels.cancelled
          : sale.correction_count
            ? labels.returned
            : labels.saved,
        sale.correction_count ? "warning" : "success",
      ),
    );
    row.append(
      invoice,
      createCell(JSON.parse(sale.customer)?.name || "Walk-in"),
      createCell(
        new Date(sale.created_at).toLocaleString("en-IN", {
          timeZone: "Asia/Kolkata",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        }),
      ),
      createCell(paymentLabel(sale.method)),
      status,
      createCell(formatMoney(decimal(sale.total_paise))),
    );
    body.append(row);
  });
}
export function renderDashboard(report, showReceipt, storeName) {
  registerIcons({
    ArrowUpRight,
    BadgeIndianRupee,
    ChartNoAxesCombined,
    IndianRupee,
    Plus,
    Receipt,
    RotateCcw,
    Smartphone,
    Wallet,
  });
  document.querySelector("#dashboard-brand").textContent = storeName;
  document.querySelector("#dashboard-heading").textContent =
    labels.overviewHeading;
  document.querySelector("#dashboard-subtitle").textContent =
    labels.overviewHint;
  const grid = document.querySelector("#dashboard-metrics");
  clearChildren(grid);
  for (const [key, label] of Object.entries(metrics)) {
    const card = document.createElement("article");
    card.className = "metric-card";
    card.dataset.metric = key;
    const icon = document.createElement("div");
    icon.className = "metric-icon";
    const glyph = document.createElement("i");
    glyph.dataset.lucide = label.icon;
    icon.append(glyph);
    const copy = document.createElement("div"),
      en = document.createElement("p"),
      ta = document.createElement("p"),
      value = document.createElement("strong");
    en.className = "metric-label-en";
    en.textContent = label.en;
    ta.className = "metric-label-ta";
    ta.lang = "ta";
    ta.textContent = label.ta;
    value.className = "metric-value";
    copy.append(en, ta, value);
    if (label.helper) {
      const helper = document.createElement("small");
      helper.textContent = label.helper;
      copy.append(helper);
    }
    card.append(icon, copy);
    grid.append(card);
    setMetric(
      key,
      key === "bills"
        ? String(report.totals[key])
        : formatMoney(decimal(report.totals[key])),
    );
  }
  renderProducts(
    report.top_items.map((p) => ({ ...p, revenue: decimal(p.matched_paise) })),
  );
  renderPayments(report.totals);
  renderSales(report.invoices.slice(-5).reverse(), showReceipt);
  document
    .querySelector("#dashboard-content")
    .setAttribute("aria-busy", "false");
  refreshIcons();
}

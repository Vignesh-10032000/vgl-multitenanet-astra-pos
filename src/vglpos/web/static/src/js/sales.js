import { ChevronDown, ListFilter } from "lucide";

import { whenAppReady } from "./app.js";
import { localDateIso } from "./data.js";
import { formatDate, formatMoney, t } from "./i18n.js";
import { apiJson } from "./session.js";
import { clearChildren, createBadge, createCell, registerIcons, showToast } from "./ui.js";

registerIcons({ ChevronDown, ListFilter });

const state = { cursor: null, sales: [] };

function renderSales() {
  const body = document.querySelector("#sales-rows");
  clearChildren(body);
  document.querySelector("#sales-empty").classList.toggle("is-hidden", state.sales.length > 0);
  state.sales.forEach((sale) => {
    const row = document.createElement("tr");
    row.append(createCell(sale.invoice_number, sale.customer_id ? `#${sale.customer_id}` : t("receipt.walk_in")));
    row.append(createCell(formatDate(`${sale.business_date}T00:00:00`), formatDate(sale.created_at, { hour: "2-digit", minute: "2-digit" })));
    row.append(createCell(sale.payment_method));
    const status = document.createElement("td");
    const tone = sale.sale_status === "COMPLETED" ? "success" : sale.sale_status === "CANCELLED" ? "danger" : "warning";
    status.append(createBadge(sale.sale_status, tone));
    row.append(status);
    const tax = createCell(formatMoney(sale.cgst_amount));
    tax.classList.add("numeric");
    row.append(tax);
    const amount = createCell(formatMoney(sale.net_amount));
    amount.classList.add("numeric");
    row.append(amount);
    const actions = document.createElement("td");
    const link = document.createElement("a");
    link.className = "button button-secondary";
    link.href = `/receipt/${sale.id}`;
    link.textContent = t("sales.view_invoice");
    actions.append(link);
    row.append(actions);
    body.append(row);
  });
  document.querySelector("#sales-more").classList.toggle("is-hidden", !state.cursor);
}

function queryParameters(append) {
  const parameters = new URLSearchParams({ limit: "50" });
  const from = document.querySelector("#sales-from").value;
  const to = document.querySelector("#sales-to").value;
  const status = document.querySelector("#sales-status").value;
  if (from) parameters.set("start_date", from);
  if (to) parameters.set("end_date", to);
  if (status) parameters.set("status", status);
  if (append && state.cursor) parameters.set("cursor", state.cursor);
  return parameters;
}

async function loadSales({ append = false } = {}) {
  try {
    const page = await apiJson(`/api/v1/sales?${queryParameters(append)}`);
    state.sales = append ? [...state.sales, ...page.items] : page.items;
    state.cursor = page.next_cursor;
    renderSales();
  } catch (error) {
    showToast(`${t("errors.sales")}: ${error.message}`, { tone: "danger" });
  }
}

whenAppReady(() => {
  const today = localDateIso();
  document.querySelector("#sales-from").value = today;
  document.querySelector("#sales-to").value = today;
  loadSales();
  document.querySelector("#sales-apply").addEventListener("click", () => loadSales());
  document.querySelector("#sales-more").addEventListener("click", () => loadSales({ append: true }));
});

document.addEventListener("vgl:locale-changed", renderSales);

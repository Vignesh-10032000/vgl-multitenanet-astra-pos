import { Download, IndianRupee, Printer, Receipt, RefreshCw, Warehouse } from "lucide";

import { whenAppReady } from "./app.js";
import { renderRevenueBars } from "./charts.js";
import { downloadJson, localDateIso } from "./data.js";
import { formatInteger, formatMoney, localizedName, t } from "./i18n.js";
import { apiJson } from "./session.js";
import { clearChildren, createCell, registerIcons, showToast } from "./ui.js";

registerIcons({ Download, IndianRupee, Printer, Receipt, RefreshCw, Warehouse });

function renderValuation(valuation) {
  const body = document.querySelector("#valuation-rows");
  clearChildren(body);
  valuation.items.slice(0, 100).forEach((item) => {
    const row = document.createElement("tr");
    row.append(createCell(localizedName(item), item.sku));
    const quantity = createCell(item.quantity);
    quantity.classList.add("numeric");
    row.append(quantity);
    const value = createCell(formatMoney(item.value));
    value.classList.add("numeric");
    row.append(value);
    body.append(row);
  });
  document.querySelector("#stock-value").textContent = formatMoney(valuation.total_value);
}

async function loadReports() {
  try {
    const days = document.querySelector("#report-days").value;
    const method = document.querySelector("#valuation-method").value;
    const [revenue, valuation] = await Promise.all([
      apiJson(`/api/v1/reports/revenue?days=${days}`),
      apiJson(`/api/v1/reports/inventory-valuation?method=${method}`),
    ]);
    renderRevenueBars(document.querySelector("#report-revenue-chart"), revenue.items);
    document.querySelector("#report-revenue").textContent = formatMoney(revenue.net_amount);
    document.querySelector("#report-bills").textContent = formatInteger(revenue.total_bills);
    renderValuation(valuation);
  } catch (error) {
    showToast(`${t("errors.reports")}: ${error.message}`, { tone: "danger" });
  }
}

async function exportGstr1() {
  const from = document.querySelector("#gstr-from").value;
  const to = document.querySelector("#gstr-to").value;
  if (!from || !to) return;
  try {
    const report = await apiJson(`/api/v1/reports/gstr1?start_date=${from}&end_date=${to}`);
    downloadJson(`gstr1-${from}-${to}.json`, report);
    showToast(t("reports.export_ready"), { tone: "success" });
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  }
}

whenAppReady(() => {
  const today = localDateIso();
  const monthStart = `${today.slice(0, 8)}01`;
  document.querySelector("#gstr-from").value = monthStart;
  document.querySelector("#gstr-to").value = today;
  loadReports();
  document.querySelector("#reports-refresh").addEventListener("click", loadReports);
  document.querySelector("#report-print").addEventListener("click", () => window.print());
  document.querySelector("#gstr-export").addEventListener("click", exportGstr1);
});

document.addEventListener("vgl:locale-changed", loadReports);

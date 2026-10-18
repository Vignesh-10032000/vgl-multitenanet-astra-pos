import { Download, IndianRupee, Printer, Receipt, RefreshCw, Warehouse } from "lucide";

import { whenAppReady } from "./app.js";
import { renderRevenueBars } from "./charts.js";
import { localDateIso } from "./data.js";
import { formatDate, formatInteger, formatMoney, localizedName, t } from "./i18n.js";
import { apiFetch, apiJson } from "./session.js";
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
    if (revenue.items.length) {
      const dates = revenue.items.map((item) => item.business_date).sort();
      const display = (value) => formatDate(`${value}T00:00:00`, { dateStyle: "medium" });
      document.querySelector("#report-date-range").textContent = `${display(dates[0])} – ${display(dates.at(-1))}`;
    }
  } catch (error) {
    showToast(`${t("errors.reports")}: ${error.message}`, { tone: "danger" });
  }
}

async function exportGstr1() {
  const from = document.querySelector("#gstr-from").value;
  const to = document.querySelector("#gstr-to").value;
  if (!from || !to) return;
  try {
    let job = await apiJson("/api/v1/reports/jobs", {
      method: "POST",
      body: JSON.stringify({
        report_name: "GSTR1",
        output_format: "JSON",
        parameters: { start_date: from, end_date: to },
      }),
    });
    for (let attempt = 0; attempt < 120 && !["COMPLETED", "FAILED"].includes(job.status); attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      job = await apiJson(`/api/v1/reports/jobs/${job.id}`);
    }
    if (job.status === "FAILED") throw new Error(job.error_message || "Report generation failed.");
    if (job.status !== "COMPLETED" || !job.download_url) {
      throw new Error("Report generation is still pending. Try again shortly.");
    }
    const response = await apiFetch(job.download_url);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `gstr1-${from}-${to}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
  document.querySelector("#report-days").addEventListener("change", loadReports);
  document.querySelector("#valuation-method").addEventListener("change", loadReports);
  document.querySelector("#report-print").addEventListener("click", () => window.print());
  document.querySelector("#gstr-export").addEventListener("click", exportGstr1);
});

document.addEventListener("vgl:locale-changed", loadReports);

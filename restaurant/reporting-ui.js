import { Capacitor } from "@capacitor/core";
import { money } from "./domain.js";
import { escapeHTML as e } from "./documents.js";
import { uiLabels as labels, metrics, metricText } from "./labels.js";
const paymentLabel = method => labels[method] || method;
import { datePreset } from "./report-dates.js";
import { renderDashboard } from "../src/vglpos/web/static/src/js/dashboard.js";
import { icon } from "./workspace-icons.js";
import { refreshIcons } from "../src/vglpos/web/static/src/js/ui.js";
import {
  analyticsSummary,
  revenueChart,
  paymentChart,
  rollingDates,
} from "./analytics.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const timestamp = (value) =>
  new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
const metricHTML = (key) =>
  `<span>${e(metrics[key].en)}<small lang="ta">${e(metrics[key].ta)}</small></span>`;
function table(columns, rows, className = "") {
  return `<table class="${className}"><thead><tr>${columns.map((c) => `<th>${e(c).replaceAll("\n", "<br>")}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map((row) => `<tr>${row.map((value, i) => `<td data-label="${e(columns[i].replaceAll("\n", " / "))}">${value}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${columns.length}" class="empty-table">${e(labels.empty)}</td></tr>`}</tbody></table>`;
}

/** Independent filters and render targets prevent navigation from duplicating screens. */
export function createReporting({
  ledger,
  showReceipt,
  correctSale,
  notify,
  fail,
  storeName,
}) {
  let reportTab = "daily";
  let salesPage = 1,
    lastSales,
    chartGrouping = "daily";
  const requests = { dashboard: 0, sales: 0, reports: 0 };
  const formId = {
    dashboard: "dashboard-filter",
    sales: "sales-filter",
    reports: "report-filter",
  };
  let currentReport;
  const formFor = (page) => $(`#${formId[page]}`);
  for (const page of Object.keys(formId)) {
    const form = formFor(page);
    form.innerHTML = `<div class="date-chips" aria-label="Date shortcuts">${["today", "yesterday", "week", "month", "custom"].map((key) => `<button type="button" data-preset="${key}" data-label="${key}" class="date-chip" aria-pressed="false">${e(labels[key])}</button>`).join("")}</div><div class="filter-fields"><label><span data-label="from">${e(labels.from)}</span><input name="from" type="date" required></label><label><span data-label="to">${e(labels.to)}</span><input name="to" type="date" required></label><label><span data-label="payment">${e(labels.payment)}</span><select name="method"><option value="all" data-label="all">${e(labels.all)}</option><option value="cash" data-label="cash">${e(labels.cash)}</option><option value="upi" data-label="upi">${e(labels.upi)}</option></select></label>${page === "sales" ? `<label class="bill-search"><span data-label="search">${e(labels.search)}</span><input type="search" name="search" maxlength="160" placeholder="${e(labels.searchPlaceholder)}"></label>` : ""}<button type="submit" class="button button-primary"><span data-label="apply">${e(labels.apply)}</span></button></div>`;
    if (page === "sales") {
      const search = form.querySelector(".bill-search");
      search.classList.add("sales-searchbar");
      search.insertAdjacentHTML("afterbegin", icon("search"));
      form.prepend(search);
      form.querySelector('[type="submit"]').innerHTML =
        `${icon("search")} <span data-i18n="common.search">Search</span>`;
    }
    if (page === "reports") {
      form
        .querySelector(".date-chips")
        .insertAdjacentHTML(
          "beforeend",
          '<span class="rolling-presets"><button type="button" data-days="7" class="date-chip">7 Days</button><button type="button" data-days="30" class="date-chip">30 Days</button><button type="button" data-days="90" class="date-chip">90 Days</button></span>',
        );
      const payment = form.elements.method.closest("label");
      payment.classList.add("report-payment-filter");
      form.insertBefore(payment, form.querySelector(".filter-fields"));
    }
    const preset = page === "reports" ? "month" : "today";
    const dates = datePreset(preset);
    form.elements.from.value = dates.from;
    form.elements.to.value = dates.to;
    form.elements.method.value = "all";
    selectPreset(form, preset);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      render(page).catch(fail);
    });
    form.addEventListener("click", (event) => {
      const rolling = event.target.closest("[data-days]");
      if (rolling) {
        const range = rollingDates(Number(rolling.dataset.days));
        form.elements.from.value = range.from;
        form.elements.to.value = range.to;
        selectPreset(form, `rolling-${rolling.dataset.days}`);
        render(page).catch(fail);
        return;
      }
      const chip = event.target.closest("[data-preset]");
      if (!chip) return;
      selectPreset(form, chip.dataset.preset);
      if (chip.dataset.preset === "custom") {
        form.elements.from.focus();
        return;
      }
      const range = datePreset(chip.dataset.preset);
      form.elements.from.value = range.from;
      form.elements.to.value = range.to;
      render(page).catch(fail);
    });
    for (const input of [form.elements.from, form.elements.to])
      input.addEventListener("change", () => selectPreset(form, "custom"));
    form.elements.method.addEventListener("change", () =>
      render(page).catch(fail),
    );
    if (form.elements.search) {
      let timer;
      form.elements.search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => render(page).catch(fail), 200);
      });
    }
  }
  function selectPreset(form, key) {
    form.dataset.preset = key;
    form
      .querySelectorAll("[data-preset], [data-days]")
      .forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.preset === key || `rolling-${b.dataset.days}` === key)),
      );
  }
  function totals(target, totals) {
    $(target).innerHTML = Object.keys(metrics)
      .map(
        (key) =>
          `<div data-total="${key}"><div class="summary-icon summary-${key}">${icon(metrics[key].icon)}</div><div class="summary-copy">${metricHTML(key)}<strong>${key === "bills" ? totals[key] : money(totals[key])}</strong></div></div>`,
      )
      .join("");
  }
  function sales(r) {
    lastSales = r;
    const pages = Math.max(1, Math.ceil(r.invoices.length / 10));
    salesPage = Math.min(salesPage, pages);
    totals("#sales-totals", r.totals);
    $("#sales-list").innerHTML = table(
      [
        labels.bill,
        labels.dateTime,
        labels.customer,
        "Items",
        labels.payment,
        labels.billTotal,
        labels.status,
        labels.actions,
      ],
      r.invoices
        .slice()
        .reverse()
        .slice((salesPage - 1) * 10, salesPage * 10)
        .map((s) => [
          `<strong class="invoice-number">${e(s.bill_number)}</strong>`,
          `<span class="sale-date">${e(timestamp(s.created_at))}</span>`,
          `<span class="customer-cell">${icon("circle-user-round")}${e(JSON.parse(s.customer)?.name || "Walk-in")}</span>`,
          `<span class="sale-items">${r.lines
            .filter((line) => line.sale_id === s.id)
            .slice(0, 2)
            .map((line) => `${e(line.name)} <small>× ${line.quantity}</small>`)
            .join("<br>")}</span>`,
          `<span class="payment-badge payment-${e(s.method)}">${e(paymentLabel(s.method))}</span>`,
          `<strong>${money(s.total_paise)}</strong>${r.method !== "all" ? `<small>${e(labels.selectedAmount)}: ${money(s.matched_paise)}</small>` : ""}`,
          `<span class="status-badge ${s.correction_count ? "status-returned" : "status-saved"}">${e(
            s.has_void
              ? labels.cancelled
              : s.correction_count
                ? labels.returned
                : labels.saved,
          )}</span>`,
          `<div class="sale-actions"><button type="button" class="button button-secondary" aria-label="${e(labels.view)}" title="${e(labels.view)}" data-view-sale="${e(s.id)}">${icon("receipt")}View</button><button type="button" class="button button-secondary" data-correct-sale="${e(s.id)}" ${s.has_void || s.corrected_paise >= s.total_paise ? "disabled" : ""}>${icon("rotate-ccw")}${e(labels.cancelReturn)}</button></div>`,
        ]),
      "sales-table",
    );
    $("#sales-pagination").innerHTML =
      `<span>${r.invoices.length ? `Showing ${(salesPage - 1) * 10 + 1}–${Math.min(salesPage * 10, r.invoices.length)} of ${r.invoices.length} bills` : "No saved bills in this period"}</span><div><button class="button button-secondary" data-sales-page="${salesPage - 1}" ${salesPage === 1 ? "disabled" : ""} aria-label="Previous page">${icon("chevron-left")}</button><span>Page ${salesPage} of ${pages}</span><button class="button button-secondary" data-sales-page="${salesPage + 1}" ${salesPage === pages ? "disabled" : ""} aria-label="Next page">${icon("chevron-right")}</button></div>`;
    refreshIcons($("[data-view='sales']"));
  }
  function reports(r) {
    totals("#report-totals", r.totals);
    const a = analyticsSummary(r);
    $("#analytics-cards").innerHTML = [
      [
        "Final revenue",
        money(r.totals.net_paise),
        "banknote",
        "After cancellations and returns",
      ],
      [
        "Total bills",
        String(r.totals.bills),
        "receipt",
        "Saved invoices in the selected period",
      ],
      [
        "Average bill",
        money(a.average_paise),
        "chart-no-axes-combined",
        "Final revenue per saved bill",
      ],
      [
        "Invoiced GST",
        money(a.gst_paise),
        "indian-rupee",
        `CGST ${money(a.cgst_paise)} · SGST ${money(a.sgst_paise)}`,
      ],
    ]
      .map(
        ([title, value, glyph, hint]) =>
          `<article class="analytics-stat"><div class="analytics-stat-top"><span class="analytics-stat-icon">${icon(glyph)}</span><div><p>${e(title)}</p><strong>${value}</strong></div></div><small>${e(hint)}</small></article>`,
      )
      .join("");
    $("#revenue-chart").innerHTML = revenueChart(r, chartGrouping);
    $("#analytics-payments").innerHTML =
      paymentChart(r) +
      `<div class="payment-legend">${r.payment_totals.map((p) => `<div><span><i class="legend-dot legend-${p.method}"></i>${e(paymentLabel(p.method))}</span><strong>${money(p.net_paise)}</strong></div>`).join("")}</div><p class="chart-note">${a.split_bills} mixed bill${a.split_bills === 1 ? "" : "s"} · allocated to Cash and GPay once</p>`;
    $("#analytics-top-items").innerHTML = table(
      ["#", labels.item, labels.quantity, "Revenue"],
      r.top_items.map((item, i) => [
        `<span class="rank-dot">${i + 1}</span>`,
        `<span class="food-cell">${icon("utensils")}<span><strong>${e(item.name)}</strong><small>${e(item.portion)}</small></span></span>`,
        item.quantity,
        `<strong>${money(item.matched_paise)}</strong>`,
      ]),
    );
    $("#analytics-returns").innerHTML =
      `<div class="audit-metric"><span>Cancelled bills</span><strong>${r.adjustments.filter((x) => x.kind === "void").length}</strong></div><div class="audit-metric"><span>Return records</span><strong>${r.adjustments.filter((x) => x.kind === "refund").length}</strong></div>${r.payment_totals.map((p) => `<div class="audit-metric"><span>${e(paymentLabel(p.method))} returned</span><strong>${money(p.returned_paise)}</strong></div>`).join("")}<p class="chart-note">Returns use the date recorded. GST above is the original invoiced tax; this summary does not calculate GST credit notes.</p>`;
    $$("[data-report-tab]").forEach((b) =>
      b.setAttribute(
        "aria-selected",
        String(b.dataset.reportTab === reportTab),
      ),
    );
    let columns, rows;
    if (reportTab === "daily") {
      columns = [
        labels.date,
        metricText("bills"),
        metricText("sales_paise"),
        metricText("corrections_paise"),
        metricText("net_paise"),
      ];
      rows = r.daily.map((d) => [
        e(d.day),
        d.bills,
        money(d.sales_paise),
        money(d.corrections_paise),
        money(d.net_paise),
      ]);
    } else if (reportTab === "items") {
      columns = [
        labels.item,
        labels.portion,
        labels.quantity,
        labels.invoiced,
        labels.selectedAmount,
      ];
      rows = r.items.map((i) => [
        e(i.name),
        e(i.portion),
        i.quantity,
        money(i.net_paise),
        money(i.matched_paise),
      ]);
    } else if (reportTab === "payments") {
      columns = [
        labels.payment,
        metricText("bills"),
        labels.received,
        labels.returnedAmount,
        metricText("net_paise"),
      ];
      rows = r.payment_totals.map((p) => [
        e(paymentLabel(p.method)),
        p.bills,
        money(p.received_paise),
        money(p.returned_paise),
        money(p.net_paise),
      ]);
    } else {
      columns = [
        labels.bill,
        labels.dateTime,
        labels.correctionType,
        metricText("corrections_paise"),
        labels.cash,
        labels.upi,
        labels.reason,
      ];
      rows = r.adjustments.map((a) => [
        e(a.bill_number),
        e(timestamp(a.created_at)),
        e(a.kind === "void" ? labels.cancelled : labels.returned),
        money(a.matched_paise),
        money(a.cash_paise),
        money(a.upi_paise),
        e(a.reason),
      ]);
    }
    $("#report-details").innerHTML =
      `<div class="table-scroll">${table(columns, rows)}</div>`;
    refreshIcons($("[data-view='reports']"));
  }
  async function render(page) {
    if (!formId[page]) return;
    const sequence = ++requests[page];
    const filter = Object.fromEntries(new FormData(formFor(page)));
    const report = await ledger.report(filter);
    if (sequence !== requests[page]) return report;
    if (page === "reports") currentReport = report;
    if (page === "dashboard") {
      renderDashboard(report, (id) => showReceipt(id).catch(fail), storeName());
      const periods = await Promise.all(
        ["week", "month"].map((preset) =>
          ledger.report({ ...datePreset(preset), method: filter.method }),
        ),
      );
      if (sequence === requests[page])
        $("#dashboard-period-revenue").innerHTML = periods
          .map(
            (period, i) =>
              `<article class="period-revenue-card"><div class="period-revenue-icon">${icon(i ? "calendar-range" : "calendar-days")}</div><div><p>${i ? "Monthly revenue" : "Weekly revenue"}<small lang="ta">${i ? "மாத வருவாய்" : "வார வருவாய்"}</small></p><strong>${money(period.totals.net_paise)}</strong><span>${e(period.from)} — ${e(period.to)} · after returns</span></div>${icon("trending-up")}</article>`,
          )
          .join("");
      refreshIcons($("#dashboard-period-revenue"));
    } else if (page === "sales") {
      salesPage = 1;
      sales(report);
    } else reports(report);
    return report;
  }
  $("#sales-list").addEventListener("click", (event) => {
    const view = event.target.closest("[data-view-sale]");
    if (view) showReceipt(view.dataset.viewSale).catch(fail);
    const correct = event.target.closest("[data-correct-sale]");
    if (correct) correctSale(correct.dataset.correctSale).catch(fail);
  });
  $("#sales-pagination").addEventListener("click", (event) => {
    const button = event.target.closest("[data-sales-page]");
    if (button && !button.disabled && lastSales) {
      salesPage = Number(button.dataset.salesPage);
      sales(lastSales);
    }
  });
  $("#trend-grouping").addEventListener("change", (event) => {
    chartGrouping = event.target.value;
    if (currentReport)
      $("#revenue-chart").innerHTML = revenueChart(
        currentReport,
        chartGrouping,
      );
  });
  $$("[data-report-tab]").forEach((button) =>
    button.addEventListener("click", () => {
      reportTab = button.dataset.reportTab;
      $("#report-details").setAttribute("aria-labelledby", button.id);
      if (currentReport) reports(currentReport);
    }),
  );
  $$("[data-export]").forEach((button) =>
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const report = await render("reports");
        const { exportReport } = await import("./exports.js");
        await exportReport(report, button.dataset.export);
        notify(
          Capacitor.isNativePlatform()
            ? "File saved"
            : "Download requested — check your downloads",
        );
      } catch (error) {
        fail(error);
      } finally {
        button.disabled = false;
      }
    }),
  );
  return { show: render, refresh: () => render(document.body.dataset.page) };
}

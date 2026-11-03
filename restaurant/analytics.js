import { halfUp, money } from "./domain.js";
import { datePreset } from "./report-dates.js";
import { escapeHTML as e } from "./documents.js";

export function analyticsSummary(report) {
  let cgst = 0,
    sgst = 0;
  for (const sale of report.invoices) {
    const lines = report.lines.filter((line) => line.sale_id === sale.id);
    const selected = (amount) => {
      if (report.method === "all") return amount;
      const cash = sale.total_paise
        ? Number(
            (BigInt(amount) * BigInt(sale.cash_paise)) /
              BigInt(sale.total_paise),
          )
        : 0;
      return report.method === "cash" ? cash : amount - cash;
    };
    cgst += selected(lines.reduce((n, line) => n + line.cgst_paise, 0));
    sgst += selected(lines.reduce((n, line) => n + line.sgst_paise, 0));
  }
  return {
    average_paise: report.totals.bills
      ? (report.totals.net_paise < 0 ? -1 : 1) *
        halfUp(
          BigInt(Math.abs(report.totals.net_paise)),
          BigInt(report.totals.bills),
        )
      : 0,
    gst_paise: cgst + sgst,
    cgst_paise: cgst,
    sgst_paise: sgst,
    split_bills: report.invoices.filter((sale) => sale.method === "split")
      .length,
  };
}

export function rollingDates(days, today) {
  const { to } = datePreset("today", today);
  const date = new Date(`${to}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days + 1);
  return { from: date.toISOString().slice(0, 10), to };
}

/** Missing days are zero, and negative correction-only days remain visible. */
export function trendSeries(report, grouping = "daily") {
  const start = new Date(`${report.from}T00:00:00Z`),
    end = new Date(`${report.to}T00:00:00Z`);
  const map = new Map();
  for (
    let date = start;
    date <= end;
    date = new Date(date.getTime() + 86400000)
  ) {
    const day = date.toISOString().slice(0, 10);
    const key =
      grouping === "monthly"
        ? day.slice(0, 7)
        : grouping === "weekly"
          ? datePreset("week", day).from
          : day;
    const point = map.get(key) || { day: key, net_paise: 0 };
    point.net_paise +=
      report.daily.find((row) => row.day === day)?.net_paise || 0;
    map.set(key, point);
  }
  const points = [...map.values()];
  // Keep long ranges readable without silently dropping revenue.
  if (points.length > 40 && grouping === "daily")
    return trendSeries(report, "weekly");
  if (points.length > 40 && grouping === "weekly")
    return trendSeries(report, "monthly");
  return points;
}

export function revenueChart(report, grouping = "daily") {
  const points = trendSeries(report, grouping);
  const max = Math.max(1, ...points.map((p) => Math.abs(p.net_paise)));
  const negative = points.some((p) => p.net_paise < 0);
  const baseline = negative ? 174 : 244,
    scale = negative ? 132 : 200;
  const step = 760 / Math.max(points.length, 1),
    bar = Math.min(38, step * 0.54);
  const grid = [0, 1, 2, 3, 4]
    .map((i) => {
      const y = baseline - (i * scale) / 4;
      return `<line x1="65" y1="${y}" x2="850" y2="${y}" class="chart-grid"/><text x="52" y="${y + 4}" text-anchor="end">${e(money(halfUp(BigInt(max) * BigInt(i), 4)))}</text>`;
    })
    .join("");
  const bars = points
    .map((p, i) => {
      const h = (Math.abs(p.net_paise) / max) * scale,
        x = 78 + i * step;
      const label = new Date(
        `${p.day.length === 7 ? p.day + "-01" : p.day}T00:00:00Z`,
      ).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        timeZone: "UTC",
      });
      return `<g><rect x="${x}" y="${p.net_paise >= 0 ? baseline - h : baseline}" width="${bar}" height="${p.net_paise ? Math.max(h, 2) : 1}" rx="5" class="${p.net_paise < 0 ? "chart-bar-negative" : "chart-bar"}"><title>${e(p.day)}: ${e(money(p.net_paise))}</title></rect>${i % Math.max(1, Math.ceil(points.length / 10)) === 0 ? `<text x="${x + bar / 2}" y="${negative ? 325 : 276}" text-anchor="middle">${e(label)}</text>` : ""}</g>`;
    })
    .join("");
  return `<svg viewBox="0 0 880 ${negative ? 345 : 302}" role="img" aria-label="Final sales trend including recorded returns">${grid}${bars}</svg>`;
}

export function paymentChart(report) {
  const positive = report.payment_totals.map((p) => ({
    ...p,
    value: Math.max(0, p.net_paise),
  }));
  const total = positive.reduce((n, p) => n + p.value, 0);
  let offset = 0;
  const segments = positive
    .map((p) => {
      const length = total ? (p.value / total) * 100 : 0;
      const circle = `<circle cx="100" cy="100" r="72" pathLength="100" fill="none" stroke-width="23" class="donut-${p.method}" stroke-dasharray="${length} ${100 - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 100 100)"><title>${e(p.method)}: ${e(money(p.net_paise))}</title></circle>`;
      offset += length;
      return circle;
    })
    .join("");
  const hasNegative = report.payment_totals.some((p) => p.net_paise < 0);
  return `<div class="payment-donut"><svg viewBox="0 0 200 200" role="img" aria-label="Cash and GPay payment breakdown"><circle cx="100" cy="100" r="72" fill="none" stroke-width="23" class="donut-track"/>${segments}</svg><div><strong>${money(report.totals.net_paise)}</strong><small>FINAL SALES</small></div></div>${hasNegative ? '<p class="chart-note">Return amounts exceed receipts for one channel. Negative values appear in the payment table below.</p>' : ""}`;
}

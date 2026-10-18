import { formatDate, formatMoney, t } from "./i18n.js";
import { paymentSummary } from "./payment-display.js";
import { utcTimestamp } from "./data.js";

export function renderReceiptIdentity(createdAt, profile) {
  const timeZone = profile?.time_zone || undefined;
  const timestamp = utcTimestamp(createdAt);
  document.querySelector("#receipt-date").textContent = formatDate(timestamp, { dateStyle: "medium", timeZone });
  document.querySelector("#receipt-time").textContent = formatDate(timestamp, { timeStyle: "short", timeZone });
  const logo = document.querySelector("#receipt-store-logo");
  const source = profile?.logo_data_uri || "";
  const valid = /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(source);
  logo.hidden = !valid;
  if (valid) logo.src = source;
  document.querySelector(".receipt-brand-mark").hidden = valid;
}

export function renderReceiptTender(container, payments, total) {
  const summary = paymentSummary(total, payments);
  const addRow = (label, value) => {
    const row = document.createElement("p");
    const name = document.createElement("span");
    name.textContent = label;
    const amount = document.createElement("strong");
    amount.textContent = formatMoney(value);
    row.append(name, amount);
    container.append(row);
  };
  container.replaceChildren();
  payments.forEach((payment) => addRow((payment.payment_method || payment.method).replaceAll("_", " "), payment.amount));
  addRow(t("pos.received"), summary.received);
  addRow(t("pos.change_due"), summary.change);
  addRow(t("pos.balance"), summary.balance);
}

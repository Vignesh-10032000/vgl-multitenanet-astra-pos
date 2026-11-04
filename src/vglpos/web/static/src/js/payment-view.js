import { formatMoney, t } from "./i18n.js";
import { paymentSummary as summarizePayments } from "./payment-display.js";
import { clearChildren, refreshIcons } from "./ui.js";
import { uiLabels as labels } from "../../../../../../restaurant/labels.js";
import { createPaymentQr } from "../../../../../../restaurant/payment-qr-ui.js";

export function createPaymentView(state, getSettings) {
  const qr = createPaymentQr(state, getSettings);
  function paymentRow(payment) {
    const row = document.createElement("div");
    row.className = "payment-row";
    row.dataset.paymentId = payment.id;
    const method = document.createElement("select");
    method.setAttribute("aria-label", t("pos.payment_method"));
    ["CASH", "UPI"].forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "UPI" ? labels.upi : labels.cash;
      option.selected = payment.method === value;
      option.disabled = state.payments.some(
        (p) => p !== payment && p.method === value,
      );
      method.append(option);
    });
    method.dataset.paymentMethod = payment.id;
    method.id =
      state.payments[0] === payment
        ? "payment-method"
        : `payment-method-${payment.id}`;
    const amount = document.createElement("input");
    amount.inputMode = "decimal";
    amount.id =
      state.payments.length === 1 || payment.method === "CASH"
        ? "cash-tender"
        : "upi-received";
    amount.readOnly = payment.method === "UPI" && state.payments.length === 1;
    amount.placeholder = "0.00";
    amount.value = payment.amount;
    amount.dataset.paymentAmount = payment.id;
    amount.setAttribute("aria-label", t("pos.payment_amount"));
    const methodLabel = document.createElement("label");
    methodLabel.textContent = labels.payment;
    methodLabel.append(method);
    const amountLabel = document.createElement("label");
    amountLabel.textContent =
      payment.method === "CASH" ? labels.cashTendered : labels.upiReceived;
    amountLabel.append(amount);
    row.append(methodLabel, amountLabel);
    return row;
  }

  function renderPayments() {
    qr.render();
    const container = document.querySelector("#payment-rows");
    clearChildren(container);
    state.payments.forEach((payment, index) =>
      container.append(paymentRow(payment, index)),
    );
    const upi = state.payments.some((p) => p.method === "UPI");
    document.querySelector("#split-payment").textContent =
      state.payments.length > 1 ? labels.singlePayment : labels.splitPayment;
    document.querySelector("#upi-notice").hidden = !upi;
    document.querySelectorAll("[data-cash]").forEach((b) => {
      b.disabled =
        !state.payments.some((p) => p.method === "CASH") || state.saving;
    });
    refreshIcons(container);
  }

  function renderPaymentPreview() {
    qr.invalidate();
    const panel = document.querySelector(".change-due");
    try {
      const summary = summarizePayments(
        state.quote?.net_amount || "0.00",
        state.payments,
      );
      const remaining = summary.balance !== "0.00";
      document.querySelector("#payment-received").textContent = formatMoney(
        summary.received,
      );
      document.querySelector("#payment-balance").textContent = formatMoney(
        summary.balance,
      );
      document.querySelector("#payment-change").textContent = formatMoney(
        remaining ? summary.balance : summary.change,
      );
      document.querySelector("#payment-outcome-label").textContent = t(
        remaining
          ? "pos.still_to_collect"
          : summary.change !== "0.00"
            ? "pos.change_due"
            : "pos.exact_payment",
      );
      panel.classList.toggle("is-outstanding", remaining);
      document.querySelector("#complete-sale").disabled =
        state.saving || !state.paymentPreview || remaining;
    } catch (error) {
      document.querySelector("#payment-error").textContent = error.message;
      document.querySelector("#complete-sale").disabled = true;
    }
  }

  return { renderPayments, renderPaymentPreview, summary: summarizePayments };
}

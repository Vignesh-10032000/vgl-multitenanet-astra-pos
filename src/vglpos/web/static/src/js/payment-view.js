import { formatMoney, t } from "./i18n.js";
import { paymentSummary as summarizePayments } from "./payment-display.js";
import { clearChildren, refreshIcons } from "./ui.js";

export function createPaymentView(state) {
  function paymentRow(payment, index) {
    const row = document.createElement("div");
    row.className = "payment-row";
    row.dataset.paymentId = payment.id;
    const method = document.createElement("select");
    method.setAttribute("aria-label", t("pos.payment_method"));
    ["CASH", "UPI", "CARD", "BANK_TRANSFER", "CREDIT", "LOYALTY", "OTHER"].forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value.replace("_", " ");
      option.selected = payment.method === value;
      method.append(option);
    });
    method.dataset.paymentMethod = payment.id;
    const amount = document.createElement("input");
    amount.inputMode = "decimal";
    amount.placeholder = "0.00";
    amount.value = payment.amount;
    amount.dataset.paymentAmount = payment.id;
    amount.setAttribute("aria-label", t("pos.payment_amount"));
    const reference = document.createElement("input");
    reference.value = payment.reference || "";
    const requiredReference = ["UPI", "CARD"].includes(payment.method);
    reference.placeholder = t(requiredReference ? "pos.reference_required" : "pos.reference_optional");
    reference.required = requiredReference;
    reference.maxLength = 100;
    reference.dataset.paymentReference = payment.id;
    reference.setAttribute("aria-label", t(requiredReference ? "pos.reference_required" : "pos.reference_optional"));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-button";
    remove.dataset.removePayment = payment.id;
    remove.title = t("pos.remove_payment");
    remove.setAttribute("aria-label", t("pos.remove_payment"));
    const icon = document.createElement("i");
    icon.dataset.lucide = "x";
    remove.append(icon);
    if (index === 0 && state.payments.length === 1) remove.disabled = true;
    row.append(method, amount, reference, remove);
    return row;
  }

  function renderPayments() {
    const container = document.querySelector("#payment-rows");
    clearChildren(container);
    state.payments.forEach((payment, index) => container.append(paymentRow(payment, index)));
    document.querySelector("#add-payment-row").disabled = state.payments.length >= 5;
    refreshIcons(container);
  }

  function renderPaymentPreview() {
    const panel = document.querySelector(".change-due");
    try {
      const summary = summarizePayments(state.quote?.net_amount || "0.00", state.payments);
      const remaining = summary.balance !== "0.00";
      document.querySelector("#payment-received").textContent = formatMoney(summary.received);
      document.querySelector("#payment-balance").textContent = formatMoney(summary.balance);
      document.querySelector("#payment-change").textContent = formatMoney(remaining ? summary.balance : summary.change);
      document.querySelector("#payment-outcome-label").textContent = t(remaining ? "pos.still_to_collect" : summary.change !== "0.00" ? "pos.change_due" : "pos.exact_payment");
      panel.classList.toggle("is-outstanding", remaining);
      document.querySelector("#complete-sale").disabled = !state.paymentPreview || remaining;
    } catch (error) {
      document.querySelector("#payment-error").textContent = error.message;
      document.querySelector("#complete-sale").disabled = true;
    }
  }

  return { renderPayments, renderPaymentPreview, summary: summarizePayments };
}

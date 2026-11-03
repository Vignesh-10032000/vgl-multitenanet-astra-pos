import { paymentQrRequest, paymentQrImage } from "./upi-qr.js";
import {
  formatMoney,
  getLocale,
} from "../src/vglpos/web/static/src/js/i18n.js";
import { qrLabels } from "./labels.js";
import { decimal } from "./domain.js";

/** Display-only checkout preview; opening/closing it never writes the ledger. */
export function createPaymentQr(state, getSettings) {
  const button = document.querySelector("#show-payment-qr");
  const dialog = document.querySelector("#payment-qr-dialog");
  const image = dialog.querySelector("img");
  const status = dialog.querySelector("[data-qr-status]");
  let generation = 0;
  let displayedRequest = null;
  const fingerprint = () =>
    JSON.stringify([state.quote?.net_amount, state.payments, state.saleUuid]);
  const copy = () => qrLabels[getLocale()] || qrLabels.en;
  function translate() {
    const text = copy();
    button.textContent = text.show;
    for (const node of dialog.querySelectorAll("[data-qr-copy]"))
      node.textContent = text[node.dataset.qrCopy];
  }
  dialog.addEventListener("close", () => {
    ++generation;
    image.removeAttribute("src");
    image.hidden = true;
    if (document.querySelector("#payment-dialog").open) button.focus();
  });
  button.addEventListener("click", async () => {
    if (state.saving || dialog.open) return;
    const request = ++generation,
      before = fingerprint();
    displayedRequest = before;
    translate();
    image.hidden = true;
    image.removeAttribute("src");
    dialog.querySelector("[data-qr-details]").hidden = true;
    status.textContent = copy().loading;
    // Keep the parent payment dialog and its entered amounts intact.
    dialog.showModal();
    dialog.querySelector("button").focus();
    try {
      const settings = await getSettings();
      const model = paymentQrRequest(
        settings,
        state.quote?.net_amount,
        state.payments,
        state.saleUuid,
      );
      const source = await paymentQrImage(model.payload);
      if (request !== generation || !dialog.open) return;
      if (before !== fingerprint()) throw new Error(copy().changed);
      const text = copy();
      dialog.querySelector("[data-qr-mode]").textContent = model.demo
        ? text.demo
        : text.live;
      dialog
        .querySelector("[data-qr-mode]")
        .classList.toggle("is-demo", model.demo);
      dialog.querySelector("[data-qr-amount]").textContent = formatMoney(
        decimal(model.amount_paise),
      );
      dialog.querySelector("[data-qr-payee]").textContent = model.payee;
      dialog.querySelector("[data-qr-upi]").textContent =
        model.upi_id || text.noPayee;
      dialog.querySelector("[data-qr-hint]").textContent = model.demo
        ? text.demoHint
        : text.liveHint;
      dialog.querySelector("[data-qr-details]").hidden = false;
      image.alt = model.demo ? text.demoAlt : text.liveAlt;
      image.src = source;
      image.hidden = false;
      dialog.dataset.mode = model.demo ? "demo" : "merchant";
      status.textContent = "";
    } catch (error) {
      if (request === generation && dialog.open)
        status.textContent = error.message;
    }
  });
  return {
    invalidate() {
      if (!dialog.open || displayedRequest === fingerprint()) return;
      ++generation;
      image.removeAttribute("src");
      image.hidden = true;
      dialog.querySelector("[data-qr-details]").hidden = true;
      status.textContent = copy().changed;
    },
    render() {
      translate();
      button.hidden = !state.payments.some((p) => p.method === "UPI");
      button.disabled = state.saving;
    },
  };
}

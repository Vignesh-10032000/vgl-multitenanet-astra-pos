import { formatDate, formatMoney, localizedName, t } from "./i18n.js";
import { apiJson } from "./session.js";
import { clearChildren, closeDialog, openDialog, setBusy, showToast } from "./ui.js";

const DENOMINATIONS = [2000, 500, 200, 100, 50, 20, 10, 5, 2, 1];

function denominationCounts(form) {
  return Object.fromEntries(
    [...form.querySelectorAll("[data-denomination]")]
      .map((input) => [input.dataset.denomination, Number.parseInt(input.value || "0", 10)])
      .filter(([, count]) => Number.isInteger(count) && count > 0),
  );
}

function denominationTotal(form) {
  const total = [...form.querySelectorAll("[data-denomination]")].reduce((sum, input) => {
    const count = Number.parseInt(input.value || "0", 10);
    return sum + BigInt(input.dataset.denomination) * BigInt(Number.isInteger(count) ? count : 0);
  }, 0n);
  return `${total}.00`;
}

function updateDenominationTotal(form) {
  form.querySelector("[data-denomination-total]").textContent = formatMoney(denominationTotal(form));
}

function initializeDenominations() {
  document.querySelectorAll("[data-denominations]").forEach((container) => {
    clearChildren(container);
    DENOMINATIONS.forEach((denomination) => {
      const label = document.createElement("label");
      const text = document.createElement("span");
      text.textContent = formatMoney(`${denomination}.00`);
      const input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.step = "1";
      input.value = "0";
      input.dataset.denomination = String(denomination);
      input.setAttribute("aria-label", `${denomination} rupee count`);
      label.append(text, input);
      container.append(label);
    });
    const form = container.closest("form");
    form.addEventListener("input", (event) => {
      if (event.target.matches("[data-denomination]")) updateDenominationTotal(form);
    });
    updateDenominationTotal(form);
  });
}

export function createRetailOperations(context) {
  const {
    state,
    quotePayload,
    clearCart,
    productById,
    mutationComplete,
    renderTotals,
    offlineDatabase,
  } = context;

  function renderQuickKeys() {
    const container = document.querySelector("#quick-key-grid");
    clearChildren(container);
    state.quickKeys.forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "quick-key-button";
      button.dataset.quickProductId = String(entry.product.id);
      const key = document.createElement("kbd");
      key.textContent = entry.key_number <= 9 ? `Alt+${entry.key_number}` : String(entry.key_number);
      const name = document.createElement("span");
      name.textContent = localizedName(entry.product);
      button.append(key, name);
      container.append(button);
    });
  }

  async function loadQuickKeys() {
    if (!navigator.onLine) return;
    try {
      const response = await apiJson("/api/v1/retail/quick-keys");
      state.quickKeys = response.items;
      renderQuickKeys();
    } catch (error) {
      showToast(`${t("pos.quick_keys_failed")}: ${error.message}`, { tone: "warning" });
    }
  }

  function renderQuickKeySettings() {
    const container = document.querySelector("#quick-key-settings");
    clearChildren(container);
    const pinned = new Map(
      state.quickKeys.filter((entry) => entry.is_pinned)
        .map((entry) => [entry.key_number, entry.product.id]),
    );
    for (let number = 1; number <= 12; number += 1) {
      const label = document.createElement("label");
      const key = document.createElement("kbd");
      key.textContent = String(number);
      const select = document.createElement("select");
      select.dataset.quickKeyNumber = String(number);
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "—";
      select.append(empty);
      state.products.forEach((product) => {
        const option = document.createElement("option");
        option.value = String(product.id);
        option.textContent = `${localizedName(product)} · ${product.sku}`;
        option.selected = pinned.get(number) === product.id;
        select.append(option);
      });
      label.append(key, select);
      container.append(label);
    }
  }

  async function configureQuickKeys(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const assignments = [...form.querySelectorAll("[data-quick-key-number]")]
      .filter((select) => select.value)
      .map((select) => ({
        key_number: Number.parseInt(select.dataset.quickKeyNumber, 10),
        product_id: Number.parseInt(select.value, 10),
      }));
    setBusy(form, true);
    try {
      const response = await apiJson("/api/v1/retail/quick-keys", {
        method: "PUT",
        body: JSON.stringify({ assignments }),
      });
      state.quickKeys = response.items;
      renderQuickKeys();
      closeDialog("#quick-keys-dialog");
      showToast(t("pos.quick_keys_saved"), { tone: "success" });
    } catch (error) {
      showToast(error.message, { tone: "danger" });
    } finally {
      setBusy(form, false);
    }
  }

  async function holdBill() {
    if (!state.cart.length) {
      showToast(t("pos.nothing_to_hold"), { tone: "warning" });
      return;
    }
    if (!state.currentShift || !navigator.onLine) {
      showToast(t("pos.hold_requires_online_shift"), { tone: "warning" });
      return;
    }
    const form = document.querySelector("#hold-form");
    form.reset();
    document.querySelector("#hold-error").textContent = "";
    openDialog("#hold-dialog");
    form.elements.label.focus();
  }

  async function submitHeldBill(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const error = document.querySelector("#hold-error");
    error.textContent = "";
    setBusy(form, true);
    try {
      await apiJson("/api/v1/retail/held-bills", {
        method: "POST",
        body: JSON.stringify({
          ...quotePayload(),
          shift_id: state.currentShift.id,
          label: form.elements.label.value.trim() || null,
        }),
      });
      closeDialog("#hold-dialog");
      clearCart({ offerUndo: false });
      showToast(t("pos.bill_held"), { tone: "success" });
    } catch (failure) {
      error.textContent = failure.message;
    } finally {
      setBusy(form, false);
    }
  }

  async function fetchHeldBills() {
    const response = await apiJson("/api/v1/retail/held-bills");
    return response.items;
  }

  async function showHeldBills() {
    const list = document.querySelector("#held-list");
    clearChildren(list);
    let holds = [];
    try {
      holds = await fetchHeldBills();
    } catch (error) {
      showToast(error.message, { tone: "danger" });
      return;
    }
    if (!holds.length) {
      const message = document.createElement("p");
      message.textContent = t("pos.no_held_bills");
      list.append(message);
    }
    holds.forEach((hold) => {
      const row = document.createElement("div");
      row.className = "held-bill";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = hold.label || t("pos.held_items", { count: hold.item_count });
      const time = document.createElement("small");
      time.textContent = `${formatDate(hold.created_at, { dateStyle: "short", timeStyle: "short" })} · ${formatMoney(hold.net_amount)}`;
      const notice = document.createElement("small");
      notice.textContent = t("pos.stock_not_reserved");
      copy.append(title, time, notice);
      const actions = document.createElement("div");
      actions.className = "held-bill-actions";
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "button button-secondary";
      restore.dataset.recallHold = hold.id;
      restore.textContent = t("pos.restore");
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "button button-ghost";
      discard.dataset.discardHold = hold.id;
      discard.textContent = t("common.delete");
      actions.append(restore, discard);
      row.append(copy, actions);
      list.append(row);
    });
    openDialog("#holds-dialog");
  }

  async function restoreHeldBill(id) {
    if (state.cart.length) {
      showToast(t("pos.hold_current_first"), { tone: "warning" });
      return;
    }
    try {
      const hold = await apiJson(`/api/v1/retail/held-bills/${id}/recall`, {
        method: "POST",
        body: "{}",
      });
      const lines = hold.cart_payload.lines || [];
      const restored = lines.map((line) => ({
        product_id: line.product_id,
        quantity: line.quantity,
        product: productById(line.product_id),
      }));
      if (restored.some((line) => !line.product)) {
        throw new Error(t("pos.held_product_unavailable"));
      }
      state.cart = restored;
      state.saleUuid = crypto.randomUUID();
      document.querySelector("#order-discount").value = hold.cart_payload.order_discount || "0.00";
      document.querySelector("#pos-customer").value = hold.cart_payload.customer_id || "";
      closeDialog("#holds-dialog");
      mutationComplete();
    } catch (error) {
      showToast(error.message, { tone: "danger" });
    }
  }

  async function discardHeldBill(id) {
    try {
      await apiJson(`/api/v1/retail/held-bills/${id}`, { method: "DELETE" });
      await showHeldBills();
    } catch (error) {
      showToast(error.message, { tone: "danger" });
    }
  }

  function setCurrentShift(shift) {
    state.currentShift = shift;
    const status = document.querySelector("#shift-status");
    status.dataset.state = shift ? "open" : "closed";
    status.querySelector("span").textContent = shift
      ? t("pos.shift_open", { id: shift.id })
      : t("pos.shift_required");
    if (shift) sessionStorage.setItem("vglpos.shiftId", String(shift.id));
    else sessionStorage.removeItem("vglpos.shiftId");
    renderTotals();
  }

  async function ensureShift() {
    try {
      const response = await apiJson("/api/v1/shifts/current");
      setCurrentShift(response.shift);
      if (!response.shift) openDialog("#shift-open-dialog");
    } catch (error) {
      const stored = sessionStorage.getItem("vglpos.shiftId");
      if (stored && !navigator.onLine) {
        setCurrentShift({ id: Number.parseInt(stored, 10), status: "OPEN" });
        return;
      }
      setCurrentShift(null);
      showToast(error.message, { tone: "danger" });
      openDialog("#shift-open-dialog");
    }
  }

  async function openShift(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const error = document.querySelector("#shift-open-error");
    error.textContent = "";
    setBusy(form, true);
    try {
      const shift = await apiJson("/api/v1/shifts/open", {
        method: "POST",
        body: JSON.stringify({
          opening_cash: denominationTotal(form),
          denomination_counts: denominationCounts(form),
          notes: form.elements.notes.value.trim() || null,
        }),
      });
      setCurrentShift(shift);
      closeDialog("#shift-open-dialog");
      showToast(t("pos.shift_opened"), { tone: "success" });
    } catch (failure) {
      error.textContent = failure.message;
    } finally {
      setBusy(form, false);
    }
  }

  async function closeShift(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const error = document.querySelector("#shift-close-error");
    error.textContent = "";
    const summary = await (await offlineDatabase()).outboxSummary();
    if (summary.total && !form.elements.queue_acknowledged.checked) {
      error.textContent = t("pos.shift_queue_warning", { count: summary.total });
      return;
    }
    const heldCount = Number.parseInt(form.dataset.heldCount || "0", 10);
    if (heldCount && !form.elements.expire_held_bills.checked) {
      error.textContent = t("pos.held_close_warning", { count: heldCount });
      return;
    }
    setBusy(form, true);
    try {
      const shift = await apiJson("/api/v1/shifts/close", {
        method: "POST",
        body: JSON.stringify({
          shift_id: state.currentShift.id,
          counted_cash: denominationTotal(form),
          denomination_counts: denominationCounts(form),
          notes: form.elements.notes.value.trim() || null,
          expire_held_bills: form.elements.expire_held_bills.checked,
          approver_user_id: form.elements.approver_user_id.value
            ? Number.parseInt(form.elements.approver_user_id.value, 10)
            : null,
          approval_pin: form.elements.approval_pin.value || null,
          variance_reason: form.elements.variance_reason.value.trim() || null,
        }),
      });
      setCurrentShift(null);
      closeDialog("#shift-close-dialog");
      showToast(t("pos.shift_closed", { difference: formatMoney(shift.cash_difference) }), {
        tone: "success",
        duration: 8000,
      });
      location.href = `/z-report/${shift.id}`;
    } catch (failure) {
      error.textContent = failure.message;
      if (failure.status === 403) {
        document.querySelector("#variance-approval").classList.remove("is-hidden");
        form.elements.approver_user_id.required = true;
        form.elements.approval_pin.required = true;
        form.elements.variance_reason.required = true;
      }
    } finally {
      setBusy(form, false);
    }
  }

  async function openShiftClose() {
    if (!state.currentShift) {
      openDialog("#shift-open-dialog");
      return;
    }
    const summary = await (await offlineDatabase()).outboxSummary();
    const warning = document.querySelector("#shift-queue-warning");
    warning.classList.toggle("is-hidden", summary.total === 0);
    document.querySelector("#shift-queue-message").textContent = summary.total
      ? t("pos.shift_queue_warning", { count: summary.total })
      : "";
    warning.querySelector("input").checked = false;
    let held = [];
    try {
      held = await fetchHeldBills();
    } catch (error) {
      showToast(error.message, { tone: "warning" });
    }
    const form = document.querySelector("#shift-close-form");
    form.dataset.heldCount = String(held.length);
    form.elements.shift_id.value = String(state.currentShift.id);
    form.elements.expire_held_bills.checked = false;
    const heldWarning = document.querySelector("#held-bills-warning");
    heldWarning.classList.toggle("is-hidden", held.length === 0);
    document.querySelector("#held-bills-message").textContent = held.length
      ? t("pos.held_close_warning", { count: held.length })
      : "";
    document.querySelector("#variance-approval").classList.add("is-hidden");
    form.elements.approver_user_id.required = false;
    form.elements.approval_pin.required = false;
    form.elements.variance_reason.required = false;
    form.querySelectorAll("[data-denomination]").forEach((input) => { input.value = "0"; });
    updateDenominationTotal(form);
    openDialog("#shift-close-dialog");
  }

  function renderShiftState() {
    setCurrentShift(state.currentShift);
  }

  return {
    closeShift,
    configureQuickKeys,
    discardHeldBill,
    ensureShift,
    holdBill,
    initializeDenominations,
    loadQuickKeys,
    openShift,
    openShiftClose,
    renderQuickKeys,
    renderQuickKeySettings,
    renderShiftState,
    restoreHeldBill,
    showHeldBills,
    submitHeldBill,
  };
}

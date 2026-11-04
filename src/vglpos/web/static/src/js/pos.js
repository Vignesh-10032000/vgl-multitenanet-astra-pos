import "../css/pos.css";

import { scaledInteger } from "./data.js";
import { createPaymentView } from "./payment-view.js";
import {
  billingQuote,
  billingPaymentPreview,
  checkoutInput,
  ledgerItems,
  menuProduct,
} from "../../../../../../restaurant/billing-adapter.js";
import { operationId, percent } from "../../../../../../restaurant/domain.js";
import { formatInteger, formatMoney, localizedName, t } from "./i18n.js";

import {
  clearChildren,
  closeDialog,
  debounce,
  openDialog,
  registerIcons,
  refreshIcons,
  setBusy,
  showToast,
} from "./ui.js";

const state = {
  products: [],
  catalogue: [],
  categories: [],
  customers: [],
  cart: [],
  quote: null,
  billingSettings: null,
  payments: [],
  paymentPreview: null,
  paymentSequence: 0,
  selectedCategory: "",
  focusedProductId: null,
  saleUuid: operationId(),
  quoteSequence: 0,
  saving: false,
};

let services;
let draftTail = Promise.resolve();
let draftFailure = null;
let loadSequence = 0;
let paymentView = null;
const debouncedPaymentPreview = debounce(requestPaymentPreview, 150);

function schedulePaymentPreview() {
  state.paymentSequence += 1;
  state.paymentPreview = null;
  renderPaymentPreview();
  debouncedPaymentPreview();
}

function exactQuantity(value) {
  const match = String(value ?? "")
    .trim()
    .match(/^(\d{1,4})(?:\.0{1,3})?$/);
  if (!match || Number(match[1]) < 1) return null;
  return `${Number(match[1])}.000`;
}

function quantityFromScaled(value) {
  const integer = value / 1000n;
  const fraction = String(value % 1000n).padStart(3, "0");
  return `${integer}.${fraction}`;
}

function changedQuantity(current, delta) {
  return quantityFromScaled(scaledInteger(current, 3) + BigInt(delta) * 1000n);
}

function cartRecord() {
  return {
    cart: state.cart,
    orderDiscount:
      document.querySelector("#order-discount").value.trim() || "0.00",
    customerId: document.querySelector("#pos-customer").value,
    saleUuid: state.saleUuid,
  };
}

async function persistCart() {
  if (!services || state.saving) return;
  const record = cartRecord();
  const value = {
    items: ledgerItems(record.cart),
    discount: record.orderDiscount,
    customer_id: record.customerId,
    operation: record.saleUuid,
    originalCart: record.cart,
  };
  // Capture before queueing so rapid taps cannot mutate an earlier write.
  const snapshot = JSON.parse(JSON.stringify(value));
  document.querySelector("#draft-status").textContent = "Saving cart…";
  const work = draftTail.then(() => services.ledger.saveDraft(snapshot));
  draftTail = work.then(
    () => {
      draftFailure = null;
      document.querySelector("#draft-status").textContent =
        "Cart saved locally";
    },
    (error) => {
      draftFailure = error;
      document.querySelector("#draft-status").textContent =
        "Cart not saved — keep app open";
    },
  );
  return work;
}

export async function flushBillingDraft() {
  await draftTail;
  if (draftFailure) throw draftFailure;
}

export function isBillingSaving() {
  return state.saving;
}

function persistSoon() {
  persistCart().catch(() =>
    showToast(t("pos.persistence_failed"), { tone: "warning" }),
  );
}

function productById(productId) {
  return (
    state.products.find((product) => product.id === productId) ||
    state.cart.find((item) => item.product_id === productId)?.product ||
    state.catalogue.find((product) => product.id === productId) ||
    null
  );
}

function renderCategories() {
  const strip = document.querySelector("#category-strip");
  strip
    .querySelectorAll("[data-dynamic-category]")
    .forEach((element) => element.remove());
  state.categories.forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "category-button";
    button.dataset.dynamicCategory = "";
    button.dataset.categoryId = String(category.id);
    button.textContent = localizedName(category);
    strip.append(button);
  });
  strip.querySelectorAll("[data-category-id]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      button.dataset.categoryId === state.selectedCategory,
    );
  });
}

function productTile(product) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "product-tile";
  button.dataset.productId = product.id;
  const visual = document.createElement("span");
  visual.className = "product-visual";
  if (product.imageSource) {
    const image = document.createElement("img");
    image.src = product.imageSource;
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    visual.append(image);
  } else {
    const icon = document.createElement("i");
    icon.dataset.lucide = "utensils";
    visual.append(icon);
  }
  const copy = document.createElement("span");
  copy.className = "product-copy";
  const name = document.createElement("strong");
  name.textContent = localizedName(product);
  const portion = document.createElement("small");
  portion.textContent = visiblePortion(product);
  copy.append(name, portion);
  const meta = document.createElement("span");
  meta.className = "product-meta";
  const price = document.createElement("strong");
  price.textContent = formatMoney(product.selling_price);
  meta.append(price);
  button.append(visual, copy, meta);
  return button;
}

function renderProducts() {
  const grid = document.querySelector("#pos-product-grid");
  const empty = document.querySelector("#pos-products-empty");
  const menuType = document.querySelector("#billing-menu-filter").value;
  const filtered = state.products.filter(product =>
    (!state.selectedCategory || String(product.category_id) === state.selectedCategory) &&
    (!menuType || product.menu_type === menuType));
  clearChildren(grid);
  grid.setAttribute("aria-busy", "false");
  grid.classList.toggle("is-hidden", filtered.length === 0);
  empty.classList.toggle("is-hidden", filtered.length > 0);
  filtered.forEach((product, index) =>
    grid.append(productTile(product, index)),
  );
  refreshIcons(grid);
}

function createQuantityControl(item) {
  const control = document.createElement("div");
  control.className = "quantity-control";
  const decrement = document.createElement("button");
  decrement.type = "button";
  decrement.dataset.quantityAction = "decrement";
  decrement.dataset.productId = String(item.product_id);
  decrement.setAttribute("aria-label", t("pos.decrease_quantity"));
  decrement.textContent = "−";
  const input = document.createElement("input");
  input.inputMode = "decimal";
  // Display whole portion counts without touching the persisted three-place value.
  input.value = String(item.quantity).replace(/\.0{1,3}$/, "");
  input.dataset.quantityInput = String(item.product_id);
  input.setAttribute("aria-label", t("pos.quantity"));
  const increment = document.createElement("button");
  increment.type = "button";
  increment.dataset.quantityAction = "increment";
  increment.dataset.productId = String(item.product_id);
  increment.setAttribute("aria-label", t("pos.increase_quantity"));
  increment.textContent = "+";
  control.append(decrement, input, increment);
  return control;
}

function cartLine(item, index) {
  const product = item.product;
  const line = document.createElement("div");
  line.className = "cart-line";
  if (state.focusedProductId === item.product_id)
    line.classList.add("is-focused");
  line.dataset.cartProductId = String(item.product_id);
  line.tabIndex = 0;

  const copy = document.createElement("div");
  copy.className = "cart-line-copy";
  const name = document.createElement("strong");
  name.textContent = localizedName(product);
  const unit = document.createElement("small");
  const portion = visiblePortion(product);
  unit.textContent = `${formatMoney(product.selling_price)}${portion ? ` · ${portion}` : ""}`;
  const total = document.createElement("span");
  total.className = "cart-line-total";
  total.textContent = state.quote?.lines?.[index]
    ? formatMoney(state.quote.lines[index].total_amount)
    : t("pos.calculating");
  copy.append(name, unit, total);

  const controls = document.createElement("div");
  controls.append(createQuantityControl(item));
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "cart-line-remove";
  remove.dataset.removeProductId = String(item.product_id);
  remove.title = t("pos.remove_item");
  remove.setAttribute("aria-label", t("pos.remove_item"));
  const icon = document.createElement("i");
  icon.dataset.lucide = "x";
  remove.append(icon);
  controls.append(remove);
  line.append(copy, controls);
  return line;
}

function renderTotals() {
  const quote = state.quote;
  const values = quote || {
    gross_amount: "0.00",
    discount_amount: "0.00",
    taxable_amount: "0.00",
    cgst_amount: "0.00",
    sgst_amount: "0.00",
    igst_amount: "0.00",
    cess_amount: "0.00",
    round_off: "0.00",
    net_amount: "0.00",
  };
  const bindings = {
    "#total-gross": values.gross_amount,
    "#total-discount": values.discount_amount,
    "#total-taxable": values.taxable_amount,
    "#total-cgst": values.cgst_amount,
    "#total-sgst": values.sgst_amount,
    "#total-igst": values.igst_amount,
    "#total-cess": values.cess_amount,
    "#total-round": values.round_off,
    "#total-net": values.net_amount,
  };
  Object.entries(bindings).forEach(([selector, value]) => {
    document.querySelector(selector).textContent = formatMoney(value);
  });
  document.querySelector("#pay-button").disabled =
    !state.cart.length || !state.quote || state.saving;
}

function renderCart(highlightId = null) {
  const container = document.querySelector("#cart-lines");
  clearChildren(container);
  document.querySelector("#cart-count").textContent = formatInteger(
    state.cart.length,
  );
  if (!state.cart.length) {
    const empty = document.createElement("div");
    empty.className = "cart-empty";
    const icon = document.createElement("i");
    icon.dataset.lucide = "shopping-cart";
    const title = document.createElement("h3");
    title.textContent = t("pos.empty_cart");
    const copy = document.createElement("p");
    copy.textContent = t("pos.empty_cart_hint");
    empty.append(icon, title, copy);
    container.append(empty);
  } else {
    state.cart.forEach((item, index) => {
      const line = cartLine(item, index);
      if (item.product_id === highlightId) line.classList.add("is-added");
      container.append(line);
    });
  }
  renderTotals();
  refreshIcons(container);
}

function mutationComplete(highlightId = null) {
  if (state.saving) return;
  state.quote = null;
  state.paymentPreview = null;
  persistSoon();
  requestQuote(highlightId);
}

function addProduct(product, quantity = "1.000") {
  const existing = state.cart.find((item) => item.product_id === product.id);
  const requested = existing
    ? quantityFromScaled(
        scaledInteger(existing.quantity, 3) + scaledInteger(quantity, 3),
      )
    : quantity;
  if (state.saving) return;
  if (!exactQuantity(requested)) {
    showToast("Quantity must be 1–9999 whole portions", { tone: "warning" });
    return;
  }
  if (existing) existing.quantity = requested;
  else state.cart.push({ product_id: product.id, quantity, product });
  state.focusedProductId = product.id;
  mutationComplete(product.id);
}

function selectProduct(product) {
  if (state.saving) return;
  addProduct(product);
}

function updateQuantity(productId, quantity) {
  if (state.saving) return;
  const item = state.cart.find(
    (candidate) => candidate.product_id === productId,
  );
  if (!item) return;
  const normalized = exactQuantity(quantity);
  if (!normalized) {
    showToast(t("pos.invalid_quantity"), { tone: "warning" });
    renderCart();
    return;
  }
  item.quantity = normalized;
  mutationComplete(productId);
}

function adjustQuantity(productId, delta) {
  if (state.saving) return;
  const item = state.cart.find(
    (candidate) => candidate.product_id === productId,
  );
  if (!item) return;
  const next = changedQuantity(item.quantity, delta);
  if (scaledInteger(next, 3) <= 0n) {
    removeItem(productId);
    return;
  }
  updateQuantity(productId, next);
}

function removeItem(productId) {
  if (state.saving) return;
  const index = state.cart.findIndex((item) => item.product_id === productId);
  if (index < 0) return;
  const [removed] = state.cart.splice(index, 1);
  const operation = state.saleUuid;
  mutationComplete();
  showToast(t("pos.item_removed", { name: localizedName(removed.product) }), {
    actionLabel: t("pos.undo"),
    duration: 5000,
    onAction: () => {
      if (state.saving || state.saleUuid !== operation) return;
      if (state.cart.some((item) => item.product_id === removed.product_id)) {
        addProduct(removed.product, removed.quantity);
        return;
      }
      state.cart.splice(index, 0, removed);
      mutationComplete(removed.product_id);
    },
  });
}

function visiblePortion(product) {
  if (product.portion !== "Standard") return product.portion || "";
  const portions = state.catalogue.filter(candidate => candidate.name === product.name && candidate.category === product.category);
  return portions.length > 1 ? product.portion : "";
}

function clearCart({ offerUndo = true } = {}) {
  if (state.saving) return;
  if (!state.cart.length) return;
  const previous = cartRecord();
  state.cart = [];
  state.quote = null;
  state.paymentPreview = null;
  ++state.quoteSequence;
  state.saleUuid = operationId();
  const clearedOperation = state.saleUuid;
  document.querySelector("#order-discount").value = "0.00";
  renderCart();
  persistSoon();
  if (offerUndo) {
    showToast(t("pos.cart_cleared"), {
      actionLabel: t("pos.undo"),
      duration: 5000,
      onAction: () => {
        if (state.saving || state.saleUuid !== clearedOperation) return;
        state.cart = previous.cart;
        state.saleUuid = previous.saleUuid;
        document.querySelector("#order-discount").value =
          previous.orderDiscount;
        document.querySelector("#pos-customer").value = previous.customerId;
        mutationComplete();
      },
    });
  }
}

async function localQuote() {
  return billingQuote(
    state.cart,
    document.querySelector("#order-discount").value,
    state.billingSettings || await services.ledger.settings(),
  );
}

async function requestQuote(highlightId = null) {
  const sequence = ++state.quoteSequence;
  state.paymentPreview = null;
  renderPaymentPreview();
  if (!state.cart.length) {
    state.quote = null;
    renderCart(highlightId);
    return;
  }
  try {
    const quote = await localQuote();
    if (sequence !== state.quoteSequence) return;
    state.quote = quote;
    document.querySelector("#cart-error").textContent = "";
    renderCart(highlightId);
    if (document.querySelector("#payment-dialog").open) {
      document.querySelector("#payment-total").textContent = formatMoney(
        quote.net_amount,
      );
      schedulePaymentPreview();
    }
  } catch (error) {
    if (sequence !== state.quoteSequence) return;
    state.quote = null;
    renderCart();
    document.querySelector("#cart-error").textContent = error.message;
  }
}

async function loadProducts(query = "") {
  const sequence = ++loadSequence;
  const products = await services.ledger.products();
  state.catalogue = products.filter((p) => p.active).map(menuProduct);
  const active = products.filter(
    (p) =>
      p.active &&
      [p.name, p.portion, p.category].some((v) =>
        v.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
      ),
  );
  const mapped = await Promise.all(
    active.map(async (p) => ({
      ...menuProduct(p),
      imageSource: p.image ? await services.images.read(p.image) : null,
    })),
  );
  if (sequence !== loadSequence) return;
  state.products = mapped;
  renderProducts();
}

async function loadReferenceData() {
  const [products, customers] = await Promise.all([
    services.ledger.products(),
    services.ledger.customers(),
  ]);
  state.categories = [
    ...new Set(products.filter((p) => p.active).map((p) => p.category)),
  ].map((name) => ({ id: name, name }));
  state.customers = customers;
  renderCategories();
  const select = document.querySelector("#pos-customer");
  const selected = select.value;
  select
    .querySelectorAll("option:not(:first-child)")
    .forEach((option) => option.remove());
  customers.forEach((customer) => {
    const option = document.createElement("option");
    option.value = customer.id;
    option.textContent = `${customer.name}${customer.phone ? " · " + customer.phone : ""}`;
    select.append(option);
  });
  select.value = selected;
  const settings = await services.ledger.settings();
  state.billingSettings = settings;
  const priceBasis = document.querySelector("#scanner-status span");
  priceBasis.dataset.i18n = settings.receipt_mode === "tax_invoice"
    ? settings.tax_inclusive === false ? "restaurant.pricesExclusive" : "restaurant.pricesInclusive"
    : "restaurant.localBilling";
  priceBasis.textContent = t(priceBasis.dataset.i18n);
  document.querySelector("#cgst-label").textContent =
    `CGST ${percent(settings.tax_bps, 2)}%`;
  document.querySelector("#sgst-label").textContent =
    `SGST ${percent(settings.tax_bps, 2)}%`;
  document.querySelectorAll("[data-gst-row]").forEach((row) => {
    row.hidden = settings.receipt_mode !== "tax_invoice";
  });
}

async function restoreCart() {
  const saved = await services.ledger.draft();
  if (!saved) return;
  state.cart =
    saved.originalCart ||
    (saved.items || []).map((item) => ({
      product_id: item.product_id,
      quantity: `${item.quantity}.000`,
      product: menuProduct({
        id: item.product_id,
        name: item.name,
        portion: item.portion,
        price_paise: item.unit_paise,
      }),
    }));
  state.saleUuid = saved.operation || operationId();
  document.querySelector("#order-discount").value = saved.discount || "0.00";
  document.querySelector("#pos-customer").value = saved.customer_id || "";
  await requestQuote();
  if (state.cart.length) showToast(t("pos.cart_restored"), { tone: "success" });
}

function renderPayments() {
  paymentView?.renderPayments();
}
function renderPaymentPreview() {
  paymentView?.renderPaymentPreview();
}
function paymentSummary(...args) {
  return paymentView.summary(...args);
}

async function requestPaymentPreview() {
  ++state.paymentSequence;
  state.paymentPreview = null;
  try {
    if (state.quote && !state.saving)
      state.paymentPreview = billingPaymentPreview(
        state.quote.net_amount,
        state.payments,
      );
    document.querySelector("#payment-error").textContent = "";
  } catch (error) {
    document.querySelector("#payment-error").textContent = error.message;
  }
  renderPaymentPreview();
}

async function openPayment() {
  try {
    paymentView ||= createPaymentView(state, () => services.ledger.settings());
  } catch (error) {
    showToast(error.message, { tone: "danger" });
    return;
  }
  if (state.saving || !state.cart.length || !state.quote) {
    showToast(t("pos.wait_for_total"), { tone: "warning" });
    return;
  }
  state.payments = [
    {
      id: operationId(),
      method: "CASH",
      amount: state.quote.net_amount,
      reference: "",
    },
  ];
  state.paymentPreview = null;
  document.querySelector("#payment-total").textContent = formatMoney(
    state.quote.net_amount,
  );
  document.querySelector("#payment-error").textContent = "";
  renderPayments();
  renderPaymentPreview();
  openDialog("#payment-dialog", document.querySelector("#pay-button"));
  document.querySelector("[data-payment-amount]")?.focus();
  document.querySelector("[data-payment-amount]")?.select();
  requestPaymentPreview();
}

async function completeSale() {
  if (state.saving || !state.paymentPreview || !state.quote) return;
  state.saving = true;
  renderTotals();
  document
    .querySelectorAll(
      "#payment-dialog button, #payment-dialog input, #payment-dialog select",
    )
    .forEach((element) => {
      element.disabled = true;
    });
  let sale;
  let saveError;
  try {
    const input = checkoutInput(
      state.cart,
      document.querySelector("#order-discount").value,
      document.querySelector("#pos-customer").value,
      state.saleUuid,
      state.payments,
      state.quote.net_amount,
    );
    // No pending draft may run after checkout's atomic draft removal.
    await flushBillingDraft();
    sale = await services.ledger.checkout(input);
  } catch (error) {
    saveError = error;
  } finally {
    state.saving = false;
    document
      .querySelectorAll(
        "#payment-dialog button, #payment-dialog input, #payment-dialog select",
      )
      .forEach((element) => {
        element.disabled = false;
      });
  }
  if (!sale) {
    renderTotals();
    await requestPaymentPreview();
    document.querySelector("#payment-error").textContent = saveError.message;
    return;
  }
  // Commit has succeeded. Receipt failures must never leave a payable copy of this cart.
  state.cart = [];
  state.quote = null;
  state.payments = [];
  state.paymentPreview = null;
  state.saleUuid = operationId();
  document.querySelector("#order-discount").value = "0.00";
  document.querySelector("#draft-status").textContent = "Bill saved locally";
  closeDialog("#payment-dialog");
  renderCart();
  try {
    await services.showReceipt(sale.id);
  } catch (error) {
    showToast(
      `Bill ${sale.bill_number} saved. Open Sales to reprint: ${error.message}`,
      { tone: "warning" },
    );
  }
}

async function holdBill() {
  if (state.saving || !state.cart.length) return;
  const form = document.querySelector("#hold-form");
  form.reset();
  document.querySelector("#hold-error").textContent = "";
  openDialog("#hold-dialog");
  form.elements.label.focus();
}

async function submitHeldBill(event) {
  event.preventDefault();
  if (state.saving) return;
  const form = event.currentTarget;
  state.saving = true;
  setBusy(form, true);
  try {
    await flushBillingDraft();
    await services.ledger.holdCart(
      cartRecord(),
      form.elements.label.value.trim(),
    );
    state.cart = [];
    state.quote = null;
    state.saleUuid = operationId();
    document.querySelector("#order-discount").value = "0.00";
    closeDialog("#hold-dialog");
    renderCart();
  } catch (error) {
    document.querySelector("#hold-error").textContent = error.message;
  } finally {
    state.saving = false;
    setBusy(form, false);
    renderTotals();
  }
}

async function fetchHeldBills() {
  return services.ledger.heldBills();
}

async function showHeldBills() {
  const list = document.querySelector("#held-list");
  clearChildren(list);
  let holds;
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
    title.textContent =
      hold.label || t("pos.held_items", { count: hold.item_count });
    const time = document.createElement("small");
    time.textContent = hold.created_at;
    copy.append(title, time);
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
  if (state.saving) return;
  if (state.cart.length) {
    showToast(t("pos.hold_current_first"), { tone: "warning" });
    return;
  }
  state.saving = true;
  try {
    await flushBillingDraft();
    const saved = await services.ledger.recallHeldBill(id);
    state.cart = saved.cart;
    state.saleUuid = saved.saleUuid || operationId();
    document.querySelector("#order-discount").value =
      saved.orderDiscount || "0.00";
    document.querySelector("#pos-customer").value = saved.customerId || "";
    closeDialog("#holds-dialog");
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  } finally {
    state.saving = false;
    mutationComplete();
  }
}

async function discardHeldBill(id) {
  try {
    await services.ledger.discardHeldBill(id);
    await showHeldBills();
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  }
}



function initializeEvents() {
  document.querySelector("#billing-menu-filter").addEventListener("change", renderProducts);
  document
    .querySelector("#pos-product-grid")
    .addEventListener("click", (event) => {
      const tile = event.target.closest("[data-product-id]");
      if (!tile) return;
      const product = productById(tile.dataset.productId);
      if (product) selectProduct(product);
    });
  document
    .querySelector("#category-strip")
    .addEventListener("click", (event) => {
      const button = event.target.closest("[data-category-id]");
      if (!button) return;
      state.selectedCategory = button.dataset.categoryId;
      renderCategories();
      renderProducts();
    });
  document.querySelector("#cart-lines").addEventListener("focusin", (event) => {
    const line = event.target.closest("[data-cart-product-id]");
    if (line) {
      state.focusedProductId = line.dataset.cartProductId;
      document
        .querySelectorAll(".cart-line")
        .forEach((row) => row.classList.toggle("is-focused", row === line));
    }
  });
  document.querySelector("#cart-lines").addEventListener("click", (event) => {
    const action = event.target.closest("[data-quantity-action]");
    if (action)
      adjustQuantity(
        action.dataset.productId,
        action.dataset.quantityAction === "increment" ? 1 : -1,
      );
    const remove = event.target.closest("[data-remove-product-id]");
    if (remove) removeItem(remove.dataset.removeProductId);
  });
  document.querySelector("#cart-lines").addEventListener("change", (event) => {
    if (event.target.matches("[data-quantity-input]"))
      updateQuantity(event.target.dataset.quantityInput, event.target.value);
  });
  document.querySelector("#pos-search").addEventListener(
    "input",
    debounce((event) => loadProducts(event.target.value.trim()), 250),
  );
  document
    .querySelector("#pos-customer")
    .addEventListener("change", () => mutationComplete());
  document
    .querySelector("#order-discount")
    .addEventListener("input", () => mutationComplete());
  document
    .querySelector("#clear-cart")
    .addEventListener("click", () => {
      if (!state.saving && state.cart.length) openDialog("#clear-cart-dialog");
    });
  document.querySelector("#confirm-clear-cart").addEventListener("click", () => {
    if (state.saving) return;
    closeDialog("#clear-cart-dialog");
    clearCart();
  });
  document.querySelector("#pay-button").addEventListener("click", openPayment);
  document.querySelector("#hold-bill").addEventListener("click", holdBill);
  document
    .querySelector("#recall-bill")
    .addEventListener("click", showHeldBills);
  document.querySelector("#split-payment").addEventListener("click", () => {
    if (state.saving) return;
    if (state.payments.length === 1)
      state.payments = [
        {
          id: operationId(),
          method: "CASH",
          amount: state.quote.net_amount,
          reference: "",
        },
        { id: operationId(), method: "UPI", amount: "0.00", reference: "" },
      ];
    else
      state.payments = [
        {
          id: operationId(),
          method: "CASH",
          amount: state.quote.net_amount,
          reference: "",
        },
      ];
    renderPayments();
    schedulePaymentPreview();
  });
  document.querySelector("#payment-rows").addEventListener("input", (event) => {
    const id =
      event.target.dataset.paymentAmount ||
      event.target.dataset.paymentReference ||
      event.target.dataset.paymentMethod;
    const payment = state.payments.find((item) => item.id === id);
    if (!payment || state.saving) return;
    if (event.target.dataset.paymentAmount)
      payment.amount = event.target.value.trim();
    if (event.target.dataset.paymentReference)
      payment.reference = event.target.value;
    if (event.target.dataset.paymentMethod) payment.method = event.target.value;
    if (event.target.dataset.paymentMethod) {
      if (state.payments.length === 1) payment.amount = state.quote.net_amount;
      renderPayments();
    }
    schedulePaymentPreview();
  });
  document
    .querySelector("#payment-rows")
    .addEventListener("change", (event) => {
      if (event.target.matches("select"))
        event.target.dispatchEvent(new Event("input", { bubbles: true }));
    });
  document.querySelectorAll("[data-cash]").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.saving) return;
      const cash = state.payments.find((p) => p.method === "CASH");
      if (!cash || cash.method !== "CASH") return;
      if (button.dataset.cash === "exact") {
        try {
          cash.amount = paymentSummary(
            state.quote.net_amount,
            state.payments.filter((item) => item !== cash),
          ).balance;
        } catch {
          return;
        }
      } else cash.amount = `${button.dataset.cash}.00`;
      renderPayments();
      schedulePaymentPreview();
    });
  });
  document
    .querySelector("#complete-sale")
    .addEventListener("click", completeSale);
  document.querySelector("#held-list").addEventListener("click", (event) => {
    const recall = event.target.closest("[data-recall-hold]");
    if (recall) {
      restoreHeldBill(recall.dataset.recallHold);
    }
    const discard = event.target.closest("[data-discard-hold]");
    if (discard) {
      discardHeldBill(discard.dataset.discardHold);
    }
  });
  document.querySelector("#hold-form").addEventListener("submit", (event) => {
    submitHeldBill(event);
  });
}

export async function initializePos(localServices) {
  services = localServices;
  registerIcons((await import("./pos-icons.js")).posIcons);
  initializeEvents();
  await refreshBilling();
  await restoreCart();
}

export async function refreshBilling() {
  state.billingSettings = null;
  await Promise.all([
    loadProducts(document.querySelector("#pos-search").value.trim()),
    loadReferenceData(),
  ]);
  if (state.cart.length) await requestQuote();
}

document.addEventListener("vgl:locale-changed", () => {
  if (!services) return;
  renderCategories();
  renderProducts();
  renderCart();
  if (document.querySelector("#payment-dialog").open) renderPayments();
});

export function selectBillingCustomer(id) {
  if (state.saving) return;
  document.querySelector("#pos-customer").value = id;
  mutationComplete();
}

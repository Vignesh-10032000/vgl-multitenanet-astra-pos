import "../css/pos.css";


import { decimalCompare, localDateIso, scaledInteger } from "./data.js";
import { whenAppReady } from "./app.js";
import {
  formatDate,
  formatInteger,
  formatMoney,
  formatQuantity,
  localizedName,
  t,
} from "./i18n.js";
import { apiJson, getSession } from "./session.js";
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
  categories: [],
  customers: [],
  cart: [],
  quote: null,
  payments: [],
  paymentPreview: null,
  selectedCategory: "",
  focusedProductId: null,
  weighedProduct: null,
  weightInput: "",
  saleUuid: crypto.randomUUID(),
  quoteSequence: 0,
  lastBarcode: null,
  lastBarcodeAt: 0,
  usingOfflineQuote: false,
};

let cartKey = "";
let holdsKey = "";
let quoteController = null;
let audioContext = null;
let offlinePromise = null;
let offlineDatabasePromise = null;
let taxEnginePromise = null;
let keyValuePromise = null;
const scheduleQuote = debounce(requestQuote, 150);
const schedulePaymentPreview = debounce(requestPaymentPreview, 150);

function offlineApi() {
  offlinePromise ||= import("./offline.js");
  return offlinePromise;
}

function offlineDatabase() {
  offlineDatabasePromise ||= import("./offline-db.js");
  return offlineDatabasePromise;
}

function taxEngine() {
  taxEnginePromise ||= import("./tax-engine.js");
  return taxEnginePromise;
}

function keyValueStore() {
  keyValuePromise ||= import("idb-keyval");
  return keyValuePromise;
}

function exactQuantity(value) {
  const match = String(value ?? "").trim().match(/^(\d{1,9})(?:\.(\d{0,3}))?$/);
  if (!match) return null;
  const quantity = `${match[1]}.${(match[2] || "").padEnd(3, "0")}`;
  return scaledInteger(quantity, 3) > 0n ? quantity : null;
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
    orderDiscount: document.querySelector("#order-discount").value.trim() || "0.00",
    customerId: document.querySelector("#pos-customer").value,
    saleUuid: state.saleUuid,
  };
}

async function persistCart() {
  if (!cartKey) return;
  const database = await offlineDatabase();
  if (!state.cart.length) {
    await database.deleteCart(cartKey);
    return;
  }
  await database.saveCart(cartKey, cartRecord());
}

function persistSoon() {
  persistCart().catch(() => showToast(t("pos.persistence_failed"), { tone: "warning" }));
}

function productById(productId) {
  return state.products.find((product) => product.id === productId) ||
    state.cart.find((item) => item.product_id === productId)?.product || null;
}

function quotePayload() {
  const customerValue = document.querySelector("#pos-customer").value;
  return {
    lines: state.cart.map((item) => ({
      product_id: item.product_id,
      quantity: item.quantity,
      line_discount: "0.00",
    })),
    customer_id: customerValue ? Number.parseInt(customerValue, 10) : null,
    business_date: localDateIso(),
    order_discount: document.querySelector("#order-discount").value.trim() || "0.00",
    apply_round_off: true,
  };
}

function setScannerStatus(key, tone = "") {
  const status = document.querySelector("#scanner-status");
  status.classList.remove("is-scanning", "is-miss");
  if (tone) status.classList.add(tone);
  status.querySelector("span").textContent = t(key);
}

function playTone(kind) {
  if (localStorage.getItem("vglpos.scannerSounds") === "false") return;
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) return;
  audioContext ||= new Audio();
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  oscillator.type = kind === "hit" ? "sine" : "square";
  oscillator.frequency.value = kind === "hit" ? 880 : 190;
  gain.gain.value = 0.08;
  oscillator.connect(gain);
  gain.connect(audioContext.destination);
  oscillator.start();
  oscillator.stop(audioContext.currentTime + (kind === "hit" ? 0.08 : 0.16));
}

function renderCategories() {
  const strip = document.querySelector("#category-strip");
  strip.querySelectorAll("[data-dynamic-category]").forEach((element) => element.remove());
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
    button.classList.toggle("is-active", button.dataset.categoryId === state.selectedCategory);
  });
}

function productTile(product, index) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "product-tile";
  button.dataset.productId = String(product.id);
  button.disabled = product.is_inventory_tracked &&
    !product.allow_negative_stock && decimalCompare(product.on_hand, "0.000") <= 0;

  const visual = document.createElement("span");
  visual.className = "product-visual";
  if (index % 3 === 1) visual.dataset.accent = "warm";
  const icon = document.createElement("i");
  icon.dataset.lucide = product.is_weighed ? "scale" : "package";
  visual.append(icon);

  const copy = document.createElement("span");
  copy.className = "product-copy";
  const name = document.createElement("strong");
  name.textContent = localizedName(product);
  const sku = document.createElement("small");
  sku.textContent = product.sku;
  copy.append(name, sku);

  const meta = document.createElement("span");
  meta.className = "product-meta";
  const price = document.createElement("strong");
  price.textContent = formatMoney(product.selling_price);
  const stock = document.createElement("span");
  stock.textContent = `${formatQuantity(product.on_hand)} ${product.uom}`;
  meta.append(price, stock);
  if (product.stock_unverified
      && decimalCompare(product.on_hand, product.low_stock_threshold) <= 0) {
    const warning = document.createElement("small");
    warning.className = "stock-unverified";
    warning.textContent = t("pos.stock_unverified");
    meta.append(warning);
  }
  button.append(visual, copy, meta);
  return button;
}

function renderProducts() {
  const grid = document.querySelector("#pos-product-grid");
  const empty = document.querySelector("#pos-products-empty");
  const filtered = state.selectedCategory
    ? state.products.filter((product) => String(product.category_id) === state.selectedCategory)
    : state.products;
  clearChildren(grid);
  grid.setAttribute("aria-busy", "false");
  grid.classList.toggle("is-hidden", filtered.length === 0);
  empty.classList.toggle("is-hidden", filtered.length > 0);
  filtered.forEach((product, index) => grid.append(productTile(product, index)));
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
  input.value = item.quantity;
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
  if (state.focusedProductId === item.product_id) line.classList.add("is-focused");
  line.dataset.cartProductId = String(item.product_id);
  line.tabIndex = 0;

  const copy = document.createElement("div");
  copy.className = "cart-line-copy";
  const name = document.createElement("strong");
  name.textContent = localizedName(product);
  const unit = document.createElement("small");
  unit.textContent = `${formatMoney(product.selling_price)} · ${product.uom}`;
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
  document.querySelector("#pay-button").disabled = !state.cart.length || !state.quote;
}

function renderCart(highlightId = null) {
  const container = document.querySelector("#cart-lines");
  clearChildren(container);
  document.querySelector("#cart-count").textContent = formatInteger(state.cart.length);
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
  state.quote = null;
  renderCart(highlightId);
  persistSoon();
  scheduleQuote();
}

function availableQuantity(product, requested) {
  return !product.is_inventory_tracked || product.allow_negative_stock ||
    decimalCompare(requested, product.on_hand) <= 0;
}

function addProduct(product, quantity = "1.000") {
  const existing = state.cart.find((item) => item.product_id === product.id);
  const requested = existing
    ? quantityFromScaled(scaledInteger(existing.quantity, 3) + scaledInteger(quantity, 3))
    : quantity;
  if (!availableQuantity(product, requested)) {
    showToast(t("pos.insufficient_stock"), { tone: "warning" });
    return;
  }
  if (existing) existing.quantity = requested;
  else state.cart.push({ product_id: product.id, quantity, product });
  state.focusedProductId = product.id;
  mutationComplete(product.id);
}

function selectProduct(product) {
  if (product.is_weighed) {
    state.weighedProduct = product;
    state.weightInput = "";
    document.querySelector("#weight-title").textContent = localizedName(product);
    document.querySelector("#weight-value").textContent = "0.000";
    openDialog("#weight-dialog");
    return;
  }
  addProduct(product);
}

function updateQuantity(productId, quantity) {
  const item = state.cart.find((candidate) => candidate.product_id === productId);
  if (!item) return;
  const normalized = exactQuantity(quantity);
  if (!normalized || !availableQuantity(item.product, normalized)) {
    showToast(t("pos.invalid_quantity"), { tone: "warning" });
    renderCart();
    return;
  }
  item.quantity = normalized;
  mutationComplete(productId);
}

function adjustQuantity(productId, delta) {
  const item = state.cart.find((candidate) => candidate.product_id === productId);
  if (!item) return;
  const next = changedQuantity(item.quantity, delta);
  if (scaledInteger(next, 3) <= 0n) {
    removeItem(productId);
    return;
  }
  updateQuantity(productId, next);
}

function removeItem(productId) {
  const index = state.cart.findIndex((item) => item.product_id === productId);
  if (index < 0) return;
  const [removed] = state.cart.splice(index, 1);
  mutationComplete();
  showToast(t("pos.item_removed", { name: localizedName(removed.product) }), {
    actionLabel: t("pos.undo"),
    duration: 5000,
    onAction: () => {
      state.cart.splice(index, 0, removed);
      mutationComplete(removed.product_id);
    },
  });
}

function clearCart({ offerUndo = true } = {}) {
  if (!state.cart.length) return;
  const previous = cartRecord();
  state.cart = [];
  state.quote = null;
  state.saleUuid = crypto.randomUUID();
  document.querySelector("#order-discount").value = "0.00";
  renderCart();
  persistSoon();
  if (offerUndo) {
    showToast(t("pos.cart_cleared"), {
      actionLabel: t("pos.undo"),
      duration: 5000,
      onAction: () => {
        state.cart = previous.cart;
        state.saleUuid = previous.saleUuid;
        document.querySelector("#order-discount").value = previous.orderDiscount;
        document.querySelector("#pos-customer").value = previous.customerId;
        mutationComplete();
      },
    });
  }
}

async function localQuote() {
  const facts = await (await offlineApi()).getOfflineFacts();
  if (!facts?.supplier_state) {
    throw new Error("Reconnect this terminal once before offline billing.");
  }
  const customerValue = document.querySelector("#pos-customer").value;
  const customer = customerValue
    ? state.customers.find((item) => item.id === Number.parseInt(customerValue, 10))
    : null;
  return (await taxEngine()).computeTax({
    lines: state.cart.map((item) => ({
      quantity: item.quantity,
      unit_price: item.product.selling_price,
      tax_rate: item.product.tax_rate,
      cess_rate: item.product.cess_rate,
      line_discount: "0.00",
      tax_inclusive: item.product.is_tax_inclusive,
    })),
    supplier_state: facts.supplier_state,
    place_of_supply: customer?.state_code || facts.supplier_state,
    order_discount: document.querySelector("#order-discount").value.trim() || "0.00",
    apply_round_off: true,
  });
}

async function useLocalQuote(sequence) {
  const quote = await localQuote();
  if (sequence !== state.quoteSequence) return;
  state.quote = quote;
  state.usingOfflineQuote = true;
  renderCart();
  if (document.querySelector("#payment-dialog").open) {
    document.querySelector("#payment-total").textContent = formatMoney(quote.net_amount);
    schedulePaymentPreview();
  }
}

async function requestQuote() {
  const sequence = ++state.quoteSequence;
  if (!state.cart.length) {
    state.quote = null;
    renderCart();
    return;
  }
  quoteController?.abort();
  quoteController = new AbortController();
  if (!navigator.onLine) {
    try {
      await useLocalQuote(sequence);
    } catch (error) {
      state.quote = null;
      renderCart();
      showToast(`${t("pos.quote_failed")}: ${error.message}`, { tone: "danger" });
    }
    return;
  }
  try {
    const quote = await apiJson("/api/v1/sales/quote", {
      method: "POST",
      body: JSON.stringify(quotePayload()),
      signal: quoteController.signal,
    });
    if (sequence !== state.quoteSequence) return;
    state.quote = quote;
    state.usingOfflineQuote = false;
    renderCart();
    if (document.querySelector("#payment-dialog").open) {
      document.querySelector("#payment-total").textContent = formatMoney(quote.net_amount);
      schedulePaymentPreview();
    }
  } catch (error) {
    if (error.name === "AbortError") return;
    if (!navigator.onLine || error instanceof TypeError) {
      try {
        await useLocalQuote(sequence);
        return;
      } catch (offlineError) {
        error = offlineError;
      }
    }
    state.quote = null;
    renderCart();
    showToast(`${t("pos.quote_failed")}: ${error.message}`, { tone: "danger" });
  }
}

async function loadProducts(query = "") {
  const grid = document.querySelector("#pos-product-grid");
  grid.setAttribute("aria-busy", "true");
  const cached = await (await offlineApi()).cachedReferenceData();
  try {
    const parameters = new URLSearchParams({ limit: "200" });
    if (query) parameters.set("q", query);
    const page = await apiJson(`/api/v1/products?${parameters}`);
    const cachedById = new Map(cached.products.map((product) => [product.id, product]));
    state.products = page.items.map((product) => ({
      ...product,
      tax_rate: cachedById.get(product.id)?.tax_rate,
      cess_rate: cachedById.get(product.id)?.cess_rate,
    }));
    renderProducts();
  } catch (error) {
    state.products = query
      ? cached.products.filter((product) => {
          const needle = query.toLocaleLowerCase();
          return [product.name, product.name_en, product.name_ta, product.sku, product.barcode]
            .some((value) => String(value || "").toLocaleLowerCase().includes(needle));
        })
      : cached.products;
    renderProducts();
    if (!state.products.length) {
      showToast(`${t("errors.products")}: ${error.message}`, { tone: "danger" });
    }
  }
}

async function loadReferenceData() {
  const cached = await (await offlineApi()).cachedReferenceData();
  try {
    const [categories, customers] = await Promise.all([
      apiJson("/api/v1/products/categories"),
      apiJson("/api/v1/customers?limit=200"),
    ]);
    state.categories = categories.items;
    state.customers = customers.items;
  } catch (error) {
    state.categories = [];
    state.customers = cached.customers;
    if (!state.customers.length) {
      showToast(`${t("pos.reference_failed")}: ${error.message}`, { tone: "warning" });
    }
  }
  renderCategories();
  const select = document.querySelector("#pos-customer");
  select.querySelectorAll("option:not(:first-child)").forEach((option) => option.remove());
  state.customers.forEach((customer) => {
    const option = document.createElement("option");
    option.value = String(customer.id);
    option.textContent = customer.gstin ? `${customer.name} · GSTIN` : customer.name;
    select.append(option);
  });
}

async function restoreCart() {
  const saved = await (await offlineDatabase()).loadCart(cartKey);
  if (!saved?.cart?.length) return;
  state.cart = saved.cart;
  state.saleUuid = saved.saleUuid || crypto.randomUUID();
  document.querySelector("#order-discount").value = saved.orderDiscount || "0.00";
  document.querySelector("#pos-customer").value = saved.customerId || "";
  renderCart();
  scheduleQuote();
  showToast(t("pos.cart_restored"), { tone: "success" });
}

async function processBarcode(barcode) {
  setScannerStatus("pos.scanning", "is-scanning");
  try {
    const product = await apiJson(`/api/v1/products/lookup?barcode=${encodeURIComponent(barcode)}`);
    if (!state.products.some((item) => item.id === product.id)) state.products.push(product);
    const now = Date.now();
    state.lastBarcode = barcode;
    state.lastBarcodeAt = now;
    selectProduct(product);
    playTone("hit");
    setScannerStatus("pos.scan_added", "is-scanning");
    window.setTimeout(() => setScannerStatus("pos.scanner_ready"), 1000);
  } catch (error) {
    const cached = (await (await offlineApi()).cachedReferenceData()).products.find(
      (product) => product.barcode === barcode,
    );
    if (cached) {
      if (!state.products.some((item) => item.id === cached.id)) state.products.push(cached);
      selectProduct(cached);
      playTone("hit");
      setScannerStatus("pos.scan_added", "is-scanning");
      window.setTimeout(() => setScannerStatus("pos.scanner_ready"), 1000);
      return;
    }
    playTone("miss");
    setScannerStatus("pos.scan_unknown", "is-miss");
    showToast(t("pos.unknown_barcode", { barcode }), {
      tone: "warning",
      duration: 7000,
      actionLabel: t("pos.add_new_product"),
      onAction: () => { location.href = `/products?barcode=${encodeURIComponent(barcode)}`; },
    });
    window.setTimeout(() => setScannerStatus("pos.scanner_ready"), 1600);
  }
}

function initializeScanner() {
  let characters = "";
  let lastTimestamp = 0;
  let resetTimer = null;
  let originalTarget = null;
  let originalValue = "";
  const reset = () => {
    characters = "";
    lastTimestamp = 0;
    originalTarget = null;
    originalValue = "";
    window.clearTimeout(resetTimer);
  };
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.altKey || event.metaKey) {
      reset();
      return;
    }
    if (event.key === "Enter") {
      if (characters.length >= 4 && event.timeStamp - lastTimestamp < 30) {
        event.preventDefault();
        event.stopPropagation();
        if (originalTarget && "value" in originalTarget) {
          originalTarget.value = originalValue;
          originalTarget.dispatchEvent(new Event("input", { bubbles: true }));
        }
        const barcode = characters;
        reset();
        processBarcode(barcode);
      } else {
        reset();
      }
      return;
    }
    if (event.key.length !== 1) return;
    const gap = lastTimestamp ? event.timeStamp - lastTimestamp : 0;
    if (characters && gap >= 30) reset();
    if (!characters) {
      originalTarget = event.target instanceof HTMLInputElement ? event.target : null;
      originalValue = originalTarget?.value || "";
    }
    characters += event.key;
    lastTimestamp = event.timeStamp;
    window.clearTimeout(resetTimer);
    resetTimer = window.setTimeout(reset, 40);
  }, true);
}

function paymentRow(payment, index) {
  const row = document.createElement("div");
  row.className = "payment-row";
  row.dataset.paymentId = payment.id;
  const method = document.createElement("select");
  method.setAttribute("aria-label", t("pos.payment_method"));
  ["CASH", "UPI", "CARD", "BANK_TRANSFER", "CREDIT", "OTHER"].forEach((value) => {
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
  reference.placeholder = t("pos.reference_optional");
  reference.dataset.paymentReference = payment.id;
  reference.setAttribute("aria-label", t("pos.reference_optional"));
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

function paymentPayload() {
  return state.payments
    .filter((payment) => scaledInteger(payment.amount, 2) > 0n)
    .map((payment) => ({
      method: payment.method,
      amount: payment.amount,
      reference_number: payment.reference.trim() || null,
    }));
}

function renderPaymentPreview() {
  const preview = state.paymentPreview;
  document.querySelector("#payment-received").textContent = formatMoney(preview?.amount_received || "0.00");
  document.querySelector("#payment-balance").textContent = formatMoney(preview?.balance_due || state.quote?.net_amount || "0.00");
  document.querySelector("#payment-change").textContent = formatMoney(preview?.change_due || "0.00");
  document.querySelector("#complete-sale").disabled = !preview || scaledInteger(preview.balance_due, 2) !== 0n;
}

async function requestPaymentPreview() {
  const payments = paymentPayload();
  state.paymentPreview = null;
  renderPaymentPreview();
  if (!state.quote || !payments.length) return;
  if (!navigator.onLine || state.usingOfflineQuote) {
    try {
      state.paymentPreview = (await taxEngine()).computePaymentPreview(state.quote, payments);
      document.querySelector("#payment-error").textContent = "";
    } catch (error) {
      document.querySelector("#payment-error").textContent = error.message;
    }
    renderPaymentPreview();
    return;
  }
  try {
    state.paymentPreview = await apiJson("/api/v1/sales/payment-preview", {
      method: "POST",
      body: JSON.stringify({ ...quotePayload(), payments }),
    });
    document.querySelector("#payment-error").textContent = "";
  } catch (error) {
    if (!navigator.onLine || error instanceof TypeError) {
      try {
        state.paymentPreview = (await taxEngine()).computePaymentPreview(state.quote, payments);
        state.usingOfflineQuote = true;
        document.querySelector("#payment-error").textContent = "";
      } catch (offlineError) {
        document.querySelector("#payment-error").textContent = offlineError.message;
      }
    } else {
      document.querySelector("#payment-error").textContent = error.message;
    }
  }
  renderPaymentPreview();
}

function openPayment() {
  if (!state.quote) {
    showToast(t("pos.wait_for_total"), { tone: "warning" });
    return;
  }
  state.payments = [{ id: crypto.randomUUID(), method: "CASH", amount: "", reference: "" }];
  state.paymentPreview = null;
  document.querySelector("#payment-total").textContent = formatMoney(state.quote.net_amount);
  document.querySelector("#payment-error").textContent = "";
  renderPayments();
  renderPaymentPreview();
  openDialog("#payment-dialog", document.querySelector("#pay-button"));
  document.querySelector("[data-payment-amount]")?.focus();
}

async function saveOfflineCheckout(payload) {
  const offline = await offlineApi();
  const provisionalNumber = await offline.nextProvisionalNumber();
  await offline.queueOfflineSale({
    payload,
    quote: state.quote,
    provisionalNumber,
    cart: state.cart,
  });
  localStorage.setItem("vglpos.lastReceiptPath", `/receipt/offline/${state.saleUuid}`);
  state.cart = [];
  await (await offlineDatabase()).deleteCart(cartKey);
  closeDialog("#payment-dialog");
  showToast(t("pos.offline_saved", { invoice: provisionalNumber }), {
    tone: "warning",
    duration: 8000,
  });
  location.href = `/receipt/offline/${payload.offline_uuid}?paper=${localStorage.getItem("vglpos.paper") || "80"}`;
}

async function completeSale() {
  if (!state.paymentPreview || scaledInteger(state.paymentPreview.balance_due, 2) !== 0n) return;
  const button = document.querySelector("#complete-sale");
  button.disabled = true;
  const shift = sessionStorage.getItem("vglpos.shiftId");
  const payload = {
    ...quotePayload(),
    payments: paymentPayload(),
    shift_id: shift ? Number.parseInt(shift, 10) : null,
    offline_uuid: state.saleUuid,
    notes: null,
  };
  if (!navigator.onLine || state.usingOfflineQuote) {
    try {
      await saveOfflineCheckout(payload);
    } catch (error) {
      document.querySelector("#payment-error").textContent = error.message;
      button.disabled = false;
    }
    return;
  }
  try {
    const sale = await apiJson("/api/v1/sales/checkout", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    localStorage.setItem("vglpos.lastSaleId", String(sale.id));
    localStorage.setItem("vglpos.lastReceiptPath", `/receipt/${sale.id}`);
    state.cart = [];
    await (await offlineDatabase()).deleteCart(cartKey);
    closeDialog("#payment-dialog");
    location.href = `/receipt/${sale.id}?paper=${localStorage.getItem("vglpos.paper") || "80"}`;
  } catch (error) {
    if (!navigator.onLine || error instanceof TypeError) {
      try {
        await saveOfflineCheckout(payload);
        return;
      } catch (offlineError) {
        error = offlineError;
      }
    }
    document.querySelector("#payment-error").textContent = error.message;
    button.disabled = false;
  }
}

async function holdBill() {
  if (!state.cart.length) {
    showToast(t("pos.nothing_to_hold"), { tone: "warning" });
    return;
  }
  const { get, set } = await keyValueStore();
  const holds = await get(holdsKey) || [];
  holds.unshift({ id: crypto.randomUUID(), createdAt: new Date().toISOString(), ...cartRecord() });
  await set(holdsKey, holds.slice(0, 20));
  clearCart({ offerUndo: false });
  showToast(t("pos.bill_held"), { tone: "success" });
}

async function showHeldBills() {
  const { get } = await keyValueStore();
  const holds = await get(holdsKey) || [];
  const list = document.querySelector("#held-list");
  clearChildren(list);
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
    title.textContent = t("pos.held_items", { count: hold.cart.length });
    const time = document.createElement("small");
    time.textContent = formatDate(hold.createdAt, { dateStyle: "short", timeStyle: "short" });
    copy.append(title, time);
    const restore = document.createElement("button");
    restore.type = "button";
    restore.className = "button button-secondary";
    restore.dataset.restoreHold = hold.id;
    restore.textContent = t("pos.restore");
    row.append(copy, restore);
    list.append(row);
  });
  openDialog("#holds-dialog");
}

async function restoreHeldBill(id) {
  if (state.cart.length) {
    showToast(t("pos.hold_current_first"), { tone: "warning" });
    return;
  }
  const { get, set } = await keyValueStore();
  const holds = await get(holdsKey) || [];
  const hold = holds.find((item) => item.id === id);
  if (!hold) return;
  state.cart = hold.cart;
  state.saleUuid = hold.saleUuid || crypto.randomUUID();
  document.querySelector("#order-discount").value = hold.orderDiscount || "0.00";
  document.querySelector("#pos-customer").value = hold.customerId || "";
  await set(holdsKey, holds.filter((item) => item.id !== id));
  closeDialog("#holds-dialog");
  mutationComplete();
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
  setBusy(form, true);
  try {
    const shift = await apiJson("/api/v1/shifts/close", {
      method: "POST",
      body: JSON.stringify({
        shift_id: Number.parseInt(form.elements.shift_id.value, 10),
        counted_cash: form.elements.counted_cash.value.trim(),
        notes: form.elements.notes.value.trim() || null,
      }),
    });
    sessionStorage.removeItem("vglpos.shiftId");
    closeDialog("#shift-close-dialog");
    showToast(t("pos.shift_closed", { difference: formatMoney(shift.cash_difference) }), { tone: "success", duration: 8000 });
  } catch (failure) {
    error.textContent = failure.message;
  } finally {
    setBusy(form, false);
  }
}

async function openShiftClose() {
  const summary = await (await offlineDatabase()).outboxSummary();
  const warning = document.querySelector("#shift-queue-warning");
  warning.classList.toggle("is-hidden", summary.total === 0);
  document.querySelector("#shift-queue-message").textContent = summary.total
    ? t("pos.shift_queue_warning", { count: summary.total })
    : "";
  warning.querySelector("input").checked = false;
  openDialog("#shift-close-dialog");
}

function runShortcut(key) {
  const focusedItem = state.focusedProductId || state.cart[0]?.product_id;
  if (key === "F1") openDialog("#help-dialog");
  else if (key === "F2") openPayment();
  else if (key === "F3") document.querySelector("#pos-search").focus();
  else if (key === "F4") holdBill();
  else if (key === "F5") showHeldBills();
  else if (key === "F6") document.querySelector("#pos-customer").focus();
  else if (key === "F7") document.querySelector("#order-discount").focus();
  else if (key === "F8" && focusedItem) document.querySelector(`[data-quantity-input="${focusedItem}"]`)?.focus();
  else if (key === "F9") {
    const receiptPath = localStorage.getItem("vglpos.lastReceiptPath");
    if (receiptPath) location.href = `${receiptPath}?print=1`;
    else showToast(t("pos.no_last_receipt"), { tone: "warning" });
  } else if (key === "F10") openShiftClose();
}

function initializeKeyboard() {
  document.addEventListener("keydown", (event) => {
    if (/^F(?:[1-9]|10)$/.test(event.key)) {
      event.preventDefault();
      runShortcut(event.key);
      return;
    }
    if (event.key === "Escape" && !document.querySelector("dialog[open]")) {
      event.preventDefault();
      clearCart();
      return;
    }
    const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement;
    if (!typing && (event.key === "+" || event.key === "-") && state.focusedProductId) {
      event.preventDefault();
      adjustQuantity(state.focusedProductId, event.key === "+" ? 1 : -1);
    }
  });
}

function initializeEvents() {
  document.querySelector("#pos-product-grid").addEventListener("click", (event) => {
    const tile = event.target.closest("[data-product-id]");
    if (!tile) return;
    const product = productById(Number.parseInt(tile.dataset.productId, 10));
    if (product) selectProduct(product);
  });
  document.querySelector("#category-strip").addEventListener("click", (event) => {
    const button = event.target.closest("[data-category-id]");
    if (!button) return;
    state.selectedCategory = button.dataset.categoryId;
    renderCategories();
    renderProducts();
  });
  document.querySelector("#cart-lines").addEventListener("focusin", (event) => {
    const line = event.target.closest("[data-cart-product-id]");
    if (line) {
      state.focusedProductId = Number.parseInt(line.dataset.cartProductId, 10);
      renderCart();
    }
  });
  document.querySelector("#cart-lines").addEventListener("click", (event) => {
    const action = event.target.closest("[data-quantity-action]");
    if (action) adjustQuantity(Number.parseInt(action.dataset.productId, 10), action.dataset.quantityAction === "increment" ? 1 : -1);
    const remove = event.target.closest("[data-remove-product-id]");
    if (remove) removeItem(Number.parseInt(remove.dataset.removeProductId, 10));
  });
  document.querySelector("#cart-lines").addEventListener("change", (event) => {
    if (event.target.matches("[data-quantity-input]")) updateQuantity(Number.parseInt(event.target.dataset.quantityInput, 10), event.target.value);
  });
  document.querySelector("#pos-search").addEventListener("input", debounce((event) => loadProducts(event.target.value.trim()), 250));
  document.querySelector("#pos-customer").addEventListener("change", () => { persistSoon(); scheduleQuote(); });
  document.querySelector("#order-discount").addEventListener("input", () => { persistSoon(); scheduleQuote(); });
  document.querySelector("#clear-cart").addEventListener("click", () => clearCart());
  document.querySelector("#pay-button").addEventListener("click", openPayment);
  document.querySelectorAll("[data-shortcut]").forEach((button) => button.addEventListener("click", () => runShortcut(button.dataset.shortcut)));

  document.querySelector("#weight-keypad").addEventListener("click", (event) => {
    const key = event.target.closest("[data-key]")?.dataset.key;
    if (!key) return;
    if (key === "backspace") state.weightInput = state.weightInput.slice(0, -1);
    else if (key === "." && state.weightInput.includes(".")) return;
    else if (state.weightInput.includes(".") && state.weightInput.split(".")[1].length >= 3) return;
    else state.weightInput += key;
    document.querySelector("#weight-value").textContent = state.weightInput || "0.000";
  });
  document.querySelector("#add-weight").addEventListener("click", () => {
    const quantity = exactQuantity(state.weightInput);
    if (!quantity || !state.weighedProduct) {
      showToast(t("pos.invalid_weight"), { tone: "warning" });
      return;
    }
    addProduct(state.weighedProduct, quantity);
    closeDialog("#weight-dialog");
  });

  document.querySelector("#add-payment-row").addEventListener("click", () => {
    if (state.payments.length >= 5) return;
    state.payments.push({ id: crypto.randomUUID(), method: "UPI", amount: "", reference: "" });
    renderPayments();
  });
  document.querySelector("#payment-rows").addEventListener("input", (event) => {
    const id = event.target.dataset.paymentAmount || event.target.dataset.paymentReference || event.target.dataset.paymentMethod;
    const payment = state.payments.find((item) => item.id === id);
    if (!payment) return;
    if (event.target.dataset.paymentAmount) payment.amount = event.target.value.trim();
    if (event.target.dataset.paymentReference) payment.reference = event.target.value;
    if (event.target.dataset.paymentMethod) payment.method = event.target.value;
    schedulePaymentPreview();
  });
  document.querySelector("#payment-rows").addEventListener("change", (event) => event.target.dispatchEvent(new Event("input", { bubbles: true })));
  document.querySelector("#payment-rows").addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-payment]");
    if (!remove) return;
    state.payments = state.payments.filter((payment) => payment.id !== remove.dataset.removePayment);
    renderPayments();
    schedulePaymentPreview();
  });
  document.querySelectorAll("[data-cash]").forEach((button) => {
    button.addEventListener("click", () => {
      let cash = state.payments.find((payment) => payment.method === "CASH");
      if (!cash && state.payments.length < 5) {
        cash = { id: crypto.randomUUID(), method: "CASH", amount: "", reference: "" };
        state.payments.push(cash);
      }
      if (!cash) return;
      cash.amount = button.dataset.cash === "exact" ? state.quote.net_amount : `${button.dataset.cash}.00`;
      renderPayments();
      schedulePaymentPreview();
    });
  });
  document.querySelector("#complete-sale").addEventListener("click", completeSale);
  document.querySelector("#held-list").addEventListener("click", (event) => {
    const restore = event.target.closest("[data-restore-hold]");
    if (restore) restoreHeldBill(restore.dataset.restoreHold);
  });
  document.querySelector("#shift-close-form").addEventListener("submit", closeShift);
}

async function initializePos(session) {
  registerIcons((await import("./pos-icons.js")).posIcons);
  cartKey = `vglpos.cart.${session.user.company_id}.${session.user.id}.${session.user.branch_id || 0}.${session.user.terminal_id || 0}`;
  holdsKey = `${cartKey}.holds`;
  initializeEvents();
  initializeKeyboard();
  initializeScanner();
  if (navigator.onLine) {
    try {
      await (await offlineApi()).syncReferenceData();
    } catch {
      await (await offlineApi()).publishStatus();
    }
  }
  await Promise.all([loadProducts(), loadReferenceData()]);
  await restoreCart();
  if (new URLSearchParams(location.search).get("shiftClose") === "1") {
    openShiftClose();
  }
}

whenAppReady((readySession) => {
  const session = readySession || getSession();
  if (session) initializePos(session);
});

document.addEventListener("vgl:locale-changed", () => {
  renderCategories();
  renderProducts();
  renderCart();
  if (document.querySelector("#payment-dialog").open) renderPayments();
});

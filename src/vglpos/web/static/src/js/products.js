import { ChevronDown, PackageOpen, Plus, RefreshCw, Save, Search, Trash2 } from "lucide";

import { whenAppReady } from "./app.js";
import { decimalCompare } from "./data.js";
import { formatMoney, formatQuantity, localizedName, t } from "./i18n.js";
import { apiJson } from "./session.js";
import {
  clearChildren,
  confirmRisk,
  createBadge,
  createCell,
  debounce,
  openDialog,
  registerIcons,
  refreshIcons,
  setBusy,
  showToast,
} from "./ui.js";

registerIcons({ ChevronDown, PackageOpen, Plus, RefreshCw, Save, Search, Trash2 });

const state = { cursor: null, query: "", products: [], editing: null };

function actionButton(iconName, label, action, product) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.dataset.action = action;
  button.dataset.productId = String(product.id);
  const icon = document.createElement("i");
  icon.dataset.lucide = iconName;
  button.append(icon);
  return button;
}

function renderProducts() {
  const body = document.querySelector("#product-rows");
  const empty = document.querySelector("#products-empty");
  clearChildren(body);
  empty.classList.toggle("is-hidden", state.products.length > 0);
  state.products.forEach((product) => {
    const row = document.createElement("tr");
    row.append(createCell(localizedName(product), product.name_ta || product.description));
    row.append(createCell(product.sku));
    row.append(createCell(product.barcode || "—"));
    const stockTone = decimalCompare(product.on_hand, product.low_stock_threshold) <= 0 ? "warning" : "";
    const stock = document.createElement("td");
    stock.append(createBadge(`${formatQuantity(product.on_hand)} ${product.uom}`, stockTone));
    row.append(stock);
    const price = createCell(formatMoney(product.selling_price));
    price.classList.add("numeric");
    row.append(price);
    const status = document.createElement("td");
    status.append(createBadge(product.is_active ? t("common.active") : t("common.inactive"), product.is_active ? "success" : "danger"));
    row.append(status);
    const actions = document.createElement("td");
    actions.className = "table-actions";
    actions.append(
      actionButton("settings", t("common.edit"), "edit", product),
      actionButton("trash-2", t("common.delete"), "delete", product),
    );
    row.append(actions);
    body.append(row);
  });
  document.querySelector("#products-more").classList.toggle("is-hidden", !state.cursor);
  refreshIcons(body);
}

async function loadProducts({ append = false } = {}) {
  const parameters = new URLSearchParams({ limit: "50" });
  if (state.query) parameters.set("q", state.query);
  if (append && state.cursor) parameters.set("cursor", state.cursor);
  try {
    const page = await apiJson(`/api/v1/products?${parameters}`);
    state.products = append ? [...state.products, ...page.items] : page.items;
    state.cursor = page.next_cursor;
    renderProducts();
  } catch (error) {
    showToast(`${t("errors.products")}: ${error.message}`, { tone: "danger" });
  }
}

function fillForm(product = null) {
  const form = document.querySelector("#product-form");
  form.reset();
  state.editing = product;
  document.querySelector("#product-dialog-title").textContent = product ? t("products.edit_title") : t("products.add_title");
  if (!product) return;
  const values = {
    name_en: product.name_en || product.name,
    name_ta: product.name_ta || "",
    sku: product.sku,
    barcode: product.barcode || "",
    uom: product.uom,
    cost_price: product.cost_price,
    selling_price: product.selling_price,
    mrp: product.mrp,
    tax_rate_id: product.tax_rate_id,
    category_id: product.category_id || "",
    low_stock_threshold: product.low_stock_threshold,
  };
  Object.entries(values).forEach(([name, value]) => {
    form.elements[name].value = value;
  });
  form.elements.is_tax_inclusive.checked = product.is_tax_inclusive;
  form.elements.is_inventory_tracked.checked = product.is_inventory_tracked;
  form.elements.is_weighed.checked = product.is_weighed;
}

function productPayload(form) {
  const text = (name) => form.elements[name].value.trim();
  const optionalId = (name) => (text(name) ? Number.parseInt(text(name), 10) : null);
  return {
    name: text("name_en"),
    name_en: text("name_en"),
    name_ta: text("name_ta") || null,
    sku: text("sku"),
    barcode: text("barcode") || null,
    uom: text("uom"),
    cost_price: text("cost_price"),
    selling_price: text("selling_price"),
    mrp: text("mrp"),
    tax_rate_id: optionalId("tax_rate_id"),
    category_id: optionalId("category_id"),
    low_stock_threshold: text("low_stock_threshold"),
    is_tax_inclusive: form.elements.is_tax_inclusive.checked,
    is_inventory_tracked: form.elements.is_inventory_tracked.checked,
    is_weighed: form.elements.is_weighed.checked,
    allow_negative_stock: false,
    is_active: true,
  };
}

async function saveProduct(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.querySelector("#product-form-error");
  error.textContent = "";
  setBusy(form, true);
  const payload = productPayload(form);
  const path = state.editing ? `/api/v1/products/${state.editing.id}` : "/api/v1/products";
  const method = state.editing ? "PUT" : "POST";
  if (state.editing) {
    delete payload.sku;
    delete payload.allow_negative_stock;
    delete payload.is_active;
  }
  try {
    await apiJson(path, { method, body: JSON.stringify(payload) });
    document.querySelector("#product-dialog").close();
    showToast(t(state.editing ? "products.updated" : "products.created"), { tone: "success" });
    await loadProducts();
  } catch (failure) {
    error.textContent = failure.message;
  } finally {
    setBusy(form, false);
  }
}

async function handleRowAction(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const product = state.products.find((item) => String(item.id) === button.dataset.productId);
  if (!product) return;
  if (button.dataset.action === "edit") {
    fillForm(product);
    openDialog("#product-dialog", button);
    return;
  }
  const confirmed = await confirmRisk({
    title: t("products.delete_title"),
    message: t("products.delete_body", { name: localizedName(product), stock: formatQuantity(product.on_hand) }),
    confirmLabel: t("common.delete"),
    trigger: button,
  });
  if (!confirmed) return;
  try {
    await apiJson(`/api/v1/products/${product.id}`, { method: "DELETE" });
    state.products = state.products.filter((item) => item.id !== product.id);
    renderProducts();
    showToast(t("products.deleted"), { tone: "success" });
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  }
}

whenAppReady(() => {
  loadProducts();
  const openCreate = (event) => {
    fillForm();
    openDialog("#product-dialog", event.currentTarget);
  };
  document.querySelector("#product-add").addEventListener("click", openCreate);
  document.querySelector("#product-empty-add").addEventListener("click", openCreate);
  document.querySelector("#product-refresh").addEventListener("click", () => loadProducts());
  document.querySelector("#products-more").addEventListener("click", () => loadProducts({ append: true }));
  document.querySelector("#product-rows").addEventListener("click", handleRowAction);
  document.querySelector("#product-form").addEventListener("submit", saveProduct);
  document.querySelector("#product-search").addEventListener("input", debounce((event) => {
    state.query = event.target.value.trim();
    loadProducts();
  }, 250));
  const barcode = new URLSearchParams(location.search).get("barcode");
  if (barcode) {
    fillForm();
    document.querySelector("#product-form").elements.barcode.value = barcode;
    openDialog("#product-dialog", document.querySelector("#product-add"));
  }
});

document.addEventListener("vgl:locale-changed", renderProducts);

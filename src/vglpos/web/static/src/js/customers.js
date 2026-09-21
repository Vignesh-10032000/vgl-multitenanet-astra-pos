import { ChevronDown, Save, Search, UserPlus, UsersRound } from "lucide";

import { whenAppReady } from "./app.js";
import { formatInteger, formatMoney, t } from "./i18n.js";
import { apiJson } from "./session.js";
import {
  clearChildren,
  createCell,
  debounce,
  openDialog,
  registerIcons,
  setBusy,
  showToast,
} from "./ui.js";

registerIcons({ ChevronDown, Save, Search, UserPlus, UsersRound });

const state = { cursor: null, query: "", customers: [] };

function renderCustomers() {
  const body = document.querySelector("#customer-rows");
  clearChildren(body);
  document.querySelector("#customers-empty").classList.toggle("is-hidden", state.customers.length > 0);
  state.customers.forEach((customer) => {
    const row = document.createElement("tr");
    row.append(createCell(customer.name, customer.email));
    row.append(createCell(customer.phone));
    row.append(createCell(customer.gstin || "—", customer.state_code));
    const orders = createCell(formatInteger(customer.total_orders));
    orders.classList.add("numeric");
    row.append(orders);
    const spent = createCell(formatMoney(customer.total_spent));
    spent.classList.add("numeric");
    row.append(spent);
    const balance = createCell(formatMoney(customer.outstanding_balance));
    balance.classList.add("numeric");
    row.append(balance);
    body.append(row);
  });
  document.querySelector("#customers-more").classList.toggle("is-hidden", !state.cursor);
}

async function loadCustomers({ append = false } = {}) {
  const parameters = new URLSearchParams({ limit: "50" });
  if (state.query) parameters.set("q", state.query);
  if (append && state.cursor) parameters.set("cursor", state.cursor);
  try {
    const page = await apiJson(`/api/v1/customers?${parameters}`);
    state.customers = append ? [...state.customers, ...page.items] : page.items;
    state.cursor = page.next_cursor;
    renderCustomers();
  } catch (error) {
    showToast(`${t("errors.customers")}: ${error.message}`, { tone: "danger" });
  }
}

async function saveCustomer(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.querySelector("#customer-form-error");
  error.textContent = "";
  setBusy(form, true);
  const value = (name) => form.elements[name].value.trim();
  const payload = {
    name: value("name"),
    phone: value("phone"),
    email: value("email") || null,
    gstin: value("gstin") || null,
    state_code: value("state_code"),
    credit_limit: value("credit_limit"),
    address: value("address") || null,
  };
  try {
    await apiJson("/api/v1/customers", { method: "POST", body: JSON.stringify(payload) });
    document.querySelector("#customer-dialog").close();
    form.reset();
    form.elements.state_code.value = "33";
    form.elements.credit_limit.value = "0.00";
    showToast(t("customers.created"), { tone: "success" });
    await loadCustomers();
  } catch (failure) {
    error.textContent = failure.message;
  } finally {
    setBusy(form, false);
  }
}

whenAppReady(() => {
  loadCustomers();
  const open = (event) => openDialog("#customer-dialog", event.currentTarget);
  document.querySelector("#customer-add").addEventListener("click", open);
  document.querySelector("#customer-empty-add").addEventListener("click", open);
  document.querySelector("#customer-form").addEventListener("submit", saveCustomer);
  document.querySelector("#customers-more").addEventListener("click", () => loadCustomers({ append: true }));
  document.querySelector("#customer-search").addEventListener("input", debounce((event) => {
    state.query = event.target.value.trim();
    loadCustomers();
  }, 250));
});

document.addEventListener("vgl:locale-changed", renderCustomers);

import {
  initializePos,
  refreshBilling,
  flushBillingDraft,
  isBillingSaving,
  selectBillingCustomer,
} from "../src/vglpos/web/static/src/js/pos.js";
import { uiLabels as labels } from "./labels.js";
import { translateWorkspace, workspaceText } from "./preferences.js";
import "./style.css";
import "./workspace-style.css";
import { workspaceIcons, icon } from "./workspace-icons.js";
import { posIcons } from "../src/vglpos/web/static/src/js/pos-icons.js";
import {
  registerIcons,
  refreshIcons,
} from "../src/vglpos/web/static/src/js/ui.js";
import { createAccessUI } from "./access-ui.js";
import { backupFolder } from "./backup-folder.js";
import { closeDialog } from "../src/vglpos/web/static/src/js/ui.js";
import { Capacitor } from "@capacitor/core";
import menu from "../resources/menu-transcription.json";
import defaults from "./store-defaults.json";
import { Ledger } from "./repository.js";
import { openDatabase } from "./drivers.js";
import { ImageStore } from "./assets.js";
import { installMenuPhotos, restoreMenuIllustrations } from "./menu-photo-install.js";
import { installBrandLogo } from "./brand-logo.js";
import menuPhotos from "./menu-photos.json";
import menuPhotoRefresh from "./menu-photo-refresh.json";
import menuPhotoRestore from "./menu-photo-restore.json";
import { paise, decimal, money, dayAt, operationId } from "./domain.js";
import {
  escapeHTML as e,
  menuLogo,
  receiptHTML,
  printSavedReceipt,
  saveFile,
} from "./documents.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const images = new ImageStore();
let ledger,
  settings,
  products = [],
  customers = [],
  currentSale = null,
  lastSaleId = null,
  pendingRestore = null;
let billingReady = false;
let reporting;
let accessUI, backups;
let workspaceReady, backgroundReady;
async function reloadLocalData() {
  // Native plugin connections survive a WebView reload; close this one first.
  await ledger.exclusive(() => ledger.db.close());
  location.reload();
}
async function backupNow() {
  if (!backups && backgroundReady) await backgroundReady;
  if (!backups) return;
  try {
    await backups.save();
  } catch (error) {
    console.error("Shared-folder backup failed; local ledger retained", error);
  }
}
async function findBackups(connect = false) {
  await backgroundReady;
  if (connect) await backups.connect();
  const target = accessUI?.locked()
    ? $("#access-recovery-status")
    : $("#persistent-backup-status");
  target.textContent = "Checking saved backups…";
  const { valid, rejected } = await backups.discover();
  target.textContent = `${valid.length} valid backup${valid.length === 1 ? "" : "s"} found${rejected.length ? ` · ${rejected.length} incomplete or invalid files ignored` : ""}.`;
  if (accessUI?.locked() && valid.length) {
    await accessUI.recover(valid[0]);
    return;
  }
  $("#backup-candidates").innerHTML = valid
    .map(
      (candidate, i) =>
        `<div class="backup-candidate"><div><strong>${e(candidate.name)}</strong><small>${candidate.billCount} bills · ${e(new Date(candidate.data.created_at).toLocaleString("en-IN"))}</small></div><button type="button" class="button button-secondary" data-recover-backup="${i}">Continue from backup</button></div>`,
    )
    .join("");
  $$("[data-recover-backup]").forEach((button) =>
    button.addEventListener("click", () =>
      accessUI.recover(valid[Number(button.dataset.recoverBackup)]),
    ),
  );
  if (connect && !valid.length && !accessUI?.locked()) await backupNow();
}
function toast(message) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  $("#toast-region").append(el);
  setTimeout(() => el.remove(), 6500);
}
function fail(error) {
  console.error("Restaurant operation failed", error);
  toast(error.message || String(error));
}
function dialog(id) {
  $(id).showModal();
}
function table(columns, rows) {
  return `<table><thead><tr>${columns.map((c) => `<th>${e(c)}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map((cells) => `<tr>${cells.map((v) => `<td>${v}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${columns.length}">No records</td></tr>`}</tbody></table>`;
}

async function renderRestaurantIdentity() {
  const identity = settings;
  const logo = identity.logo ? await images.read(identity.logo) : null;
  if (settings !== identity) return renderRestaurantIdentity();
  for (const selector of ["#store-name", "#access-brand-name"])
    if ($(selector).textContent !== settings.name) $(selector).textContent = settings.name;
  $("#nav-logo").hidden = !logo;
  if (logo && $("#nav-logo").getAttribute("src") !== logo) $("#nav-logo").src = logo;
  const fallback = !logo && settings.menu_logo ? menuLogo() : "";
  if ($("#nav-menu-logo").innerHTML !== fallback) $("#nav-menu-logo").innerHTML = fallback;
  const target = $("#access-brand-logo");
  if (logo) {
    if (target.querySelector(".access-custom-logo")?.getAttribute("src") !== logo)
      target.innerHTML = `<img class="access-custom-logo" src="${e(logo)}" alt="">`;
  } else if (target.innerHTML !== fallback) target.innerHTML = fallback;
  if (document.title !== settings.name) document.title = settings.name;
  try {
    const cached = JSON.stringify({ name: settings.name, logo });
    if (localStorage.getItem("restaurant.branding") !== cached)
      localStorage.setItem("restaurant.branding", cached);
  } catch (error) { console.warn("Branding cache unavailable", error); }
}

async function loadReference() {
  [products, customers, settings] = await Promise.all([
    ledger.products(),
    ledger.customers(),
    ledger.settings(),
  ]);
  const selected = $("#pos-customer").value;
  $("#pos-customer").innerHTML =
    '<option value="">Walk-in customer</option>' +
    customers
      .map(
        (c) =>
          `<option value="${e(c.id)}">${e(c.name)}${c.phone ? ` · ${e(c.phone)}` : ""}</option>`,
      )
      .join("");
  $("#pos-customer").value = selected;
  await renderRestaurantIdentity();
  const receiptKey =
    settings.receipt_mode === "training"
      ? "receiptTraining"
      : settings.receipt_mode === "bill_of_supply"
        ? "receiptSupply"
        : "receiptTax";
  $("#mode-label").dataset.i18n = `restaurant.${receiptKey}`;
  $("#mode-label").textContent = workspaceText(receiptKey);
  $("#mode-label").setAttribute("role", "status");
  $(".side-nav .brand").title = settings.name;
  if (billingReady) await refreshBilling();
  if (backups && !accessUI?.locked()) await backupNow();
}

async function reprint() {
  if (lastSaleId) return showReceipt(lastSaleId);
  const snapshot = await ledger.snapshot();
  const last = snapshot.sales.sort(
    (a, b) =>
      b.created_at.localeCompare(a.created_at) ||
      b.sequence_number - a.sequence_number,
  )[0];
  if (last) await showReceipt(last.id);
  else toast("No saved bills yet");
}
async function showReceipt(id) {
  currentSale = await ledger.sale(id);
  lastSaleId = id;
  $("#receipt-preview").innerHTML = await receiptHTML(currentSale, images);
  $("#print-status").textContent =
    "Saved locally. Print / reprint uses this saved bill; it does not create another sale.";
  if (!$("#receipt-dialog").open) dialog("#receipt-dialog");
}

async function renderProducts() {
  const search = $("#product-search").value.toLowerCase();
  const matches = products.filter((p) =>
    `${p.name} ${p.portion} ${p.category}`.toLowerCase().includes(search),
  );
  $("#product-list").innerHTML = table(
    [workspaceText("menuProduct"), labels.portion, workspaceText("category"), workspaceText("price"), labels.status, ""],
    matches.map((p) => [
      `<span class="food-cell"><span class="product-list-visual">${p.image ? `<img data-menu-photo="${e(p.id)}" alt="" loading="lazy" decoding="async">` : icon("utensils")}</span><strong>${e(p.name)}</strong></span>`,
      e(p.portion),
      e(p.category),
      money(p.price_paise),
      p.active ? workspaceText("activeStatus") : workspaceText("inactive"),
      `<button type="button" class="button button-secondary" data-edit-product="${e(p.id)}">${e(workspaceText("edit"))}</button>`,
    ]),
  );
  for (const img of $$("[data-menu-photo]")) {
    const p = matches.find((product) => product.id === img.dataset.menuPhoto);
    if (p?.image) img.src = await images.read(p.image);
  }
  refreshIcons($("#product-list"));
  $$("[data-edit-product]").forEach((b) =>
    b.addEventListener("click", () =>
      editProduct(products.find((p) => p.id === b.dataset.editProduct)),
    ),
  );
}
function editProduct(p = {}) {
  const f = $("#product-form");
  f.reset();
  for (const k of ["id", "name", "portion", "category"])
    f.elements[k].value = p[k] || "";
  f.elements.portion.value = p.portion || "Standard";
  f.elements.price.value = p.price_paise ? decimal(p.price_paise) : "";
  f.elements.active.checked = p.id ? Boolean(p.active) : true;
  $("#product-error").textContent = "";
  dialog("#product-dialog");
}
function renderCustomers() {
  const q = $("#customer-search").value.toLowerCase();
  $("#customer-list").innerHTML = table(
    [labels.name, labels.phone, labels.city, ""],
    customers
      .filter((c) => `${c.name} ${c.phone}`.toLowerCase().includes(q))
      .map((c) => [
        e(c.name),
        e(c.phone),
        e(c.city),
        `<button type="button" class="button button-secondary" data-edit-customer="${e(c.id)}">${e(workspaceText("edit"))}</button>`,
      ]),
  );
  $$("[data-edit-customer]").forEach((b) =>
    b.addEventListener("click", () =>
      editCustomer(customers.find((c) => c.id === b.dataset.editCustomer)),
    ),
  );
}
function editCustomer(c = {}) {
  const f = $("#customer-form");
  f.reset();
  for (const k of ["id", "name", "phone", "city"])
    f.elements[k].value = c[k] || "";
  $("#customer-error").textContent = "";
  $("#customer-title").textContent = c.id
    ? labels.editCustomer
    : labels.addCustomer;
  dialog("#customer-dialog");
}

function renderSettings() {
  const f = $("#settings-form");
  f.reset();
  for (const [key, value] of Object.entries(settings)) {
    const el = f.elements[key];
    if (el && el.type !== "file") {
      if (el.type === "checkbox") el.checked = Boolean(value);
      else el.value = value ?? "";
    }
  }
  f.elements.tax_percent.value = decimal(settings.tax_bps);
  f.elements.tax_inclusive.value = String(settings.tax_inclusive ?? true);
}
function openCorrection() {
  const f = $("#correction-form");
  f.reset();
  f.elements.amount.value = decimal(
    currentSale.total_paise -
      currentSale.adjustments.reduce((n, a) => n + a.amount_paise, 0),
  );
  f.elements.amount.readOnly = false;
  f.dataset.operation = operationId();
  const split = currentSale.payments.length > 1;
  $("#return-channels").hidden = !split;
  for (const name of ["cash_return", "upi_return"]) {
    f.elements[name].required = split;
    f.elements[name].value = split ? "" : "0.00";
  }
  $("#correction-error").textContent = "";
  dialog("#correction-dialog");
}
async function route() {
  if (document.body.dataset.locked === "true") return;
  const requested = location.hash.slice(1) || "billing";
  const page = [
    "billing",
    "dashboard",
    "products",
    "customers",
    "sales",
    "reports",
    "settings",
  ].includes(requested)
    ? requested
    : "billing";
  document.body.dataset.page = page === "billing" ? "pos" : page;
  $$("[data-view]").forEach((v) => {
    v.hidden = v.dataset.view !== page;
  });
  $$("[data-nav]").forEach((a) =>
    a.classList.toggle("is-active", a.dataset.nav === page),
  );
  $("#page-title").textContent = {
    billing: "Billing counter",
    dashboard: labels.dashboard,
    products: "Products",
    customers: "Customers",
    sales: labels.sales,
    reports: labels.reports,
    settings: "Settings",
  }[page];
  $("#last-receipt").hidden = page !== "billing";
  if (page === "products") await renderProducts();
  if (page === "customers") renderCustomers();
  if (page === "settings") renderSettings();
  if (["dashboard", "sales", "reports"].includes(page))
    await reporting.show(page);
  translateWorkspace();
}
function bind() {
  $$("[data-close]").forEach((b) =>
    b.addEventListener("click", () => {
      if (!isBillingSaving()) closeDialog(b.closest("dialog"));
    }),
  );
  $("#product-search").addEventListener("input", renderProducts);
  $("#customer-search").addEventListener("input", renderCustomers);
  $("#last-receipt").addEventListener("click", () => reprint().catch(fail));
  $("#add-product").addEventListener("click", () => editProduct());
  $("#add-customer").addEventListener("click", () => editCustomer());
  $("#add-billing-customer").addEventListener("click", () => editCustomer());
  $("#product-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const f = event.target;
    const submit =
      f.querySelector('[type="submit"]') ||
      f.querySelector(".dialog-actions .button-primary");
    submit.disabled = true;
    try {
      const input = Object.fromEntries(new FormData(f));
      const old = products.find((p) => p.id === input.id);
      let image = input.remove_image ? null : old?.image || null;
      if (input.photo.size) image = await images.select(input.photo);
      await ledger.saveProduct({
        ...input,
        price_paise: paise(input.price),
        image,
        active: f.elements.active.checked,
      });
      $("#product-dialog").close();
      await loadReference();
      await renderProducts();
      toast("Product saved locally");
    } catch (error) {
      $("#product-error").textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
  $("#customer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const f = event.target;
    const b = f.querySelector(".button-primary");
    b.disabled = true;
    try {
      const customer = await ledger.saveCustomer(
        Object.fromEntries(new FormData(f)),
      );
      $("#customer-dialog").close();
      await loadReference();
      renderCustomers();
      if (document.body.dataset.page === "pos")
        selectBillingCustomer(customer.id);
      toast("Customer saved locally");
    } catch (error) {
      $("#customer-error").textContent = error.message;
    } finally {
      b.disabled = false;
    }
  });
  $("#settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const f = event.target;
    const b = f.querySelector(".button-primary");
    b.disabled = true;
    try {
      const input = Object.fromEntries(new FormData(f));
      let logo = input.remove_logo ? null : settings.logo;
      if (input.logo.size) logo = await images.select(input.logo, 800);
      await ledger.saveSettings({
        ...settings,
        ...input,
        logo,
        menu_logo: f.elements.menu_logo.checked,
        tax_bps: paise(input.tax_percent),
        tax_inclusive: input.tax_inclusive === "true",
        tax_confirmed: f.elements.tax_confirmed.checked,
        upi_confirmed: f.elements.upi_confirmed.checked,
        round_rupee: f.elements.round_rupee.checked,
      });
      await loadReference();
      $("#settings-error").textContent = "";
      toast("Setup saved locally");
    } catch (error) {
      $("#settings-error").textContent = error.message;
    } finally {
      b.disabled = false;
    }
  });
  $("#print-receipt").addEventListener("click", async () => {
    const b = $("#print-receipt");
    b.disabled = true;
    let attempt;
    try {
      attempt = await ledger.printAttempt(currentSale.id);
      const result = await printSavedReceipt(currentSale, images);
      await ledger.printAttempt(
        currentSale.id,
        result.state,
        result.detail || "",
        attempt,
      );
      $("#print-status").textContent =
        result.state === "cancelled"
          ? "Print cancelled. Bill remains saved."
          : "Print submitted. Check the paper output; use reprint after a printer problem.";
    } catch (error) {
      if (attempt)
        try {
          await ledger.printAttempt(
            currentSale.id,
            "failed",
            String(error.message).slice(0, 500),
            attempt,
          );
        } catch (logError) {
          console.error("Print audit could not be updated", logError);
        }
      $("#print-status").textContent =
        `Bill remains saved. Printing failed: ${error.message}`;
    } finally {
      b.disabled = false;
    }
  });
  $("#correct-bill").addEventListener("click", openCorrection);
  $("#correction-form").elements.kind.addEventListener("change", () => {
    const f = $("#correction-form");
    if (f.elements.kind.value === "void")
      f.elements.amount.value = decimal(currentSale.total_paise);
    if (f.elements.kind.value === "void") {
      f.elements.cash_return.value = decimal(
        currentSale.payments
          .filter((p) => p.method === "cash")
          .reduce((n, p) => n + p.amount_paise, 0),
      );
      f.elements.upi_return.value = decimal(
        currentSale.payments
          .filter((p) => p.method === "upi")
          .reduce((n, p) => n + p.amount_paise, 0),
      );
    }
    f.elements.amount.readOnly = f.elements.kind.value === "void";
  });
  $("#correction-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const f = event.target;
    const b = f.querySelector(".button-primary");
    b.disabled = true;
    try {
      await ledger.adjust({
        sale_id: currentSale.id,
        operation_id: f.dataset.operation,
        kind: f.elements.kind.value,
        amount_paise: paise(f.elements.amount.value),
        reason: f.elements.reason.value,
        refunds:
          currentSale.payments.length > 1
            ? [
                {
                  method: "cash",
                  amount_paise: paise(f.elements.cash_return.value),
                },
                {
                  method: "upi",
                  amount_paise: paise(f.elements.upi_return.value),
                },
              ].filter((p) => p.amount_paise > 0)
            : undefined,
      });
      await backupNow();
      $("#correction-dialog").close();
      await showReceipt(currentSale.id);
      await reporting.refresh();
    } catch (error) {
      $("#correction-error").textContent = error.message;
    } finally {
      b.disabled = false;
    }
  });
  $("#backup-button").addEventListener("click", async () => {
    const b = $("#backup-button");
    b.disabled = true;
    try {
      await flushBillingDraft();
      const { createBackup } = await import("./backup.js");
      const content = await createBackup(ledger, images);
      await saveFile(
        `restaurant-backup-${dayAt()}.json`,
        "application/json",
        content,
      );
      $("#backup-status").textContent = Capacitor.isNativePlatform()
        ? "Backup saved to chosen location."
        : "Backup download requested. Check the saved file.";
    } catch (error) {
      $("#backup-status").textContent = error.message;
    } finally {
      b.disabled = false;
    }
  });
  $("#choose-backup-folder").addEventListener("click", () =>
    findBackups(true).catch(fail),
  );
  $("#scan-backups").addEventListener("click", () => findBackups().catch(fail));
  $("#restore-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 100000000) throw new Error("Backup exceeds 100 MB limit");
      $("#backup-status").textContent = "Validating backup…";
      const source = await file.text();
      const { inspectBackup } = await import("./backup.js");
      const data = await inspectBackup(source, () => openDatabase({ validation: true }));
      pendingRestore = source;
      $("#restore-summary").textContent =
        `Validated: ${data.tables.sales.length} bills, ${data.tables.products.length} products, ${Object.keys(data.files).length} images. Created ${data.created_at}.`;
      $("#restore-confirm").value = "";
      $("#restore-button").disabled = true;
      dialog("#restore-dialog");
      $("#backup-status").textContent = "Backup validation passed.";
    } catch (error) {
      pendingRestore = null;
      $("#backup-status").textContent = `Restore rejected: ${error.message}`;
    } finally {
      event.target.value = "";
    }
  });
  $("#restore-confirm").addEventListener(
    "input",
    () =>
      ($("#restore-button").disabled =
        $("#restore-confirm").value !== "RESTORE"),
  );
  $("#restore-button").addEventListener("click", async () => {
    if (!pendingRestore || $("#restore-confirm").value !== "RESTORE") return;
    const b = $("#restore-button");
    b.disabled = true;
    try {
      await flushBillingDraft();
      const { restoreBackup } = await import("./backup.js");
      await restoreBackup(pendingRestore, ledger, images, () =>
        openDatabase({ validation: true }),
      );
      const owner = await ledger.localSetting("owner-access");
      if (owner) sessionStorage.setItem("owner-access", owner.verifier);
      pendingRestore = null;
      $("#restore-dialog").close();
      toast("Backup restored. Reopening local data…");
      await reloadLocalData();
    } catch (error) {
      $("#backup-status").textContent =
        `Restore failed; current ledger retained: ${error.message}`;
      b.disabled = false;
    }
  });
  window.addEventListener("hashchange", () => route().catch(fail));
}
async function initializeWorkspace() {
  window.restaurantStartupMark?.("5-workspace:start");
  await loadReference();
  const { createReporting } = await import("./reporting-ui.js");
  reporting = createReporting({
    ledger, showReceipt,
    correctSale: async id => { await showReceipt(id); openCorrection(); },
    notify: toast, fail, storeName: () => settings.name,
  });
  await initializePos({ ledger, images, showReceipt: async id => {
    await backupNow();
    return showReceipt(id);
  }, reprint });
  billingReady = true;
  $("#menu-photo-credits").innerHTML = menuPhotoRefresh.assets.map(asset =>
    `<li><strong>${e(asset.slug.replaceAll("-", " "))}</strong> — ${e(asset.source.author)}. <a href="${e(asset.source.page_url)}" target="_blank" rel="noopener noreferrer">Original photograph</a> · <a href="${e(asset.source.license_url)}" target="_blank" rel="noopener noreferrer">${e(asset.source.license)}</a>. Resized and JPEG encoded; no subject crop.</li>`
  ).join("");
  $$('[data-dialog-close]').forEach(button => button.addEventListener("click", () => {
    if (!isBillingSaving()) closeDialog(button.closest("dialog"));
  }));
  $("#payment-dialog").addEventListener("cancel", event => {
    if (isBillingSaving()) event.preventDefault();
  });
  $("#storage-status").textContent = Capacitor.isNativePlatform() ? "Local SQLite ready" : "Browser preview · SQLite";
  bind();
  document.addEventListener("restaurant:language-changed", () => {
    const page = document.body.dataset.page;
    if (page === "products") renderProducts().catch(fail);
    if (page === "customers") renderCustomers();
    reporting.refresh().catch(fail);
  });
  translateWorkspace();
  refreshIcons();
  window.restaurantStartupMark?.("5-workspace:end");
}

async function initializeBackground() {
  let changed = false, assetError = false;
  $("#access-startup-status").textContent = workspaceText("backgroundPreparing");
  window.restaurantStartupMark?.("2-logo:start");
  try { changed = await installBrandLogo({ ledger, images }); }
  catch (error) { assetError = true; console.warn("Optional logo install failed", error); }
  window.restaurantStartupMark?.("2-logo:end");
  window.restaurantStartupMark?.("3-branding:start");
  settings = await ledger.settings();
  try { await renderRestaurantIdentity(); }
  catch (error) { assetError = true; console.warn("Optional identity image failed", error); }
  window.restaurantStartupMark?.("3-branding:end");
  window.restaurantStartupMark?.("4-photos:start");
  try {
    changed = Boolean(await installMenuPhotos({ ledger, images, manifest: menuPhotos })) || changed;
    changed = Boolean(await restoreMenuIllustrations({ ledger, images, manifest: menuPhotoRestore })) || changed;
  } catch (error) { assetError = true; console.warn("Optional menu photos failed", error); }
  window.restaurantStartupMark?.("4-photos:end");
  await workspaceReady;
  if (changed) await refreshBilling();
  $("#access-startup-status").textContent = assetError ? workspaceText("backgroundFailed") : "";
  window.restaurantStartupMark?.("6-backups:start");
  const { PersistentBackups } = await import("./backup-service.js");
  backups = new PersistentBackups({ ledger, images, transport: backupFolder(), makeDatabase: () => openDatabase({ validation: true }),
    status: message => {
      $("#persistent-backup-status").textContent = message;
      $("#backup-health").textContent = message.startsWith("Backup saved") ? "Shared backup saved"
        : message.startsWith("Connected") ? "Backups connected"
          : message.startsWith("Saving") ? "Saving backup…" : "Set up / check backups";
      $("#backup-health").title = message;
    },
  });
  await backups.initialize();
  $("#access-recover").disabled = false;
  if (changed && backups.connected) await backupNow();
  window.restaurantStartupMark?.("6-backups:end");
  if (backups.connected && !(await ledger.snapshot()).sales.length && accessUI.locked())
    // Do not await findBackups here: it waits for this background promise.
    queueMicrotask(() => findBackups().catch(fail));
}

export async function start() {
  window.restaurantStartupMark?.("1-core:start");
  registerIcons({ ...posIcons, ...workspaceIcons });
  document.body.dataset.native = String(Capacitor.isNativePlatform());
  ledger = new Ledger(await openDatabase());
  try { await ledger.initialize(menu.items, defaults); }
  catch (error) {
    try { await ledger.db.close(); } catch (closeError) { console.warn("Failed connection cleanup", closeError); }
    throw error;
  }
  window.restaurantStartupMark?.("1-core:end");
  window.restaurantStartupMark?.("7-access:start");
  accessUI = await createAccessUI({
    ledger,
    unlocked: async () => {
      workspaceReady ||= initializeWorkspace();
      await workspaceReady;
      await route();
    },
    recover: () => findBackups(true),
    // Schedule the existing complete backup without holding the sign-in form.
    backedUp: () => { void backgroundReady?.then(backupNow).catch(fail); },
    beforeRecovery: async () => { await workspaceReady; await flushBillingDraft(); },
    reload: reloadLocalData,
  });
  $("#access-form").setAttribute("aria-busy", "false");
  $("#access-submit").disabled = false;
  window.restaurantStartupMark?.("7-access:end");
  window.restaurantStartupMark?.("login-interactive");
  // Yield a painted, interactive form before optional startup work.
  backgroundReady = new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    .then(initializeBackground);
  backgroundReady.catch(error => {
    console.error("Optional startup work failed", error);
    $("#access-startup-status").textContent = workspaceText("backgroundFailed");
  });
  workspaceReady ||= new Promise(resolve => requestAnimationFrame(resolve)).then(initializeWorkspace);
  workspaceReady.catch(error => {
    $("#access-error").textContent = workspaceText("workspaceFailed");
    console.error("Workspace initialization failed", error);
  });
  document.dispatchEvent(new Event("restaurant:access-ready"));
  void Promise.allSettled([workspaceReady, backgroundReady]).then(() => performance.mark("restaurant:ready"));
}

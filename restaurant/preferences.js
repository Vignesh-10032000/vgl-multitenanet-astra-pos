import { installCatalogue, loadLocale, getLocale, t, translateDocument } from "../src/vglpos/web/static/src/js/i18n.js";
import english from "../src/vglpos/web/static/i18n/en.json";
import tamil from "../src/vglpos/web/static/i18n/ta.json";
import { uiLabels } from "./labels.js";
import { refreshIcons } from "../src/vglpos/web/static/src/js/ui.js";

const words = {
  workspace: ["Restaurant workspace", "உணவகப் பணியிடம்"],
  name: ["Name", "பெயர்"],
  counter: ["Restaurant counter", "உணவகக் கவுன்டர்"],
  billing: ["Billing counter", "பில்லிங் கவுன்டர்"],
  products: ["Products", "பொருட்கள்"],
  customers: ["Customers", "வாடிக்கையாளர்கள்"],
  settings: ["Settings", "அமைப்புகள்"],
  lock: ["Lock", "பூட்டு"],
  reprint: ["Reprint last", "கடைசி பில்லை அச்சிடு"],
  menuProducts: ["Menu products", "உணவுப் பொருட்கள்"],
  addProduct: ["Add product", "பொருள் சேர்"],
  saveProduct: ["Save product", "பொருளைச் சேமி"],
  menuProduct: ["Menu product", "உணவுப் பொருள்"],
  localBilling: ["Local billing", "உள்ளூர் பில்லிங்"],
  selectItem: ["Select a menu item to begin.", "தொடங்க உணவுப் பொருளைத் தேர்ந்தெடுக்கவும்."],
  tryName: ["Try another name or portion.", "வேறு பெயர் அல்லது அளவைத் தேடவும்."],
  portion: ["Portion / variant", "அளவு / வகை"],
  category: ["Category", "பிரிவு"],
  price: ["Selling price ₹", "விற்பனை விலை ₹"],
  photo: ["Photo (stored locally)", "படம் (சாதனத்தில் சேமிக்கப்படும்)"],
  removePhoto: ["Remove current photo", "தற்போதைய படத்தை நீக்கு"],
  active: ["Active on billing menu", "பில்லிங் பட்டியலில் காட்டு"],
  edit: ["Edit", "திருத்து"],
  activeStatus: ["Active", "செயலில்"],
  inactive: ["Inactive", "செயலற்றது"],
  walkIn: ["Walk-in customer", "நேரடி வாடிக்கையாளர்"],
  searchMenu: ["Search menu or portion", "உணவு அல்லது அளவைத் தேடு"],
  searchProduct: ["Search name, portion or category", "பெயர், அளவு அல்லது பிரிவு தேடு"],
  searchCustomer: ["Search name or phone", "பெயர் அல்லது தொலைபேசி தேடு"],
  upiNotice: ["Confirm receipt of payment yourself. Selecting GPay does not verify a bank settlement.", "பணம் வந்ததை நீங்களே உறுதிசெய்யவும். GPay தேர்வு செய்வது வங்கியில் பணம் வந்ததை உறுதிசெய்யாது."],
  setup: ["Restaurant setup", "உணவக அமைப்பு"],
  restaurantName: ["Restaurant name", "உணவகப் பெயர்"],
  address: ["Address", "முகவரி"],
  phone: ["Phone", "தொலைபேசி"],
  cashier: ["Cashier", "காசாளர்"],
  series: ["Bill series (1–4 letters/numbers)", "பில் வரிசை (1–4 எழுத்துகள்/எண்கள்)"],
  receiptMode: ["Receipt type", "ரசீது வகை"],
  gstin: ["Current GSTIN", "தற்போதைய GSTIN"],
  gst: ["GST % (tax invoice only)", "GST % (வரி ரசீது மட்டும்)"],
  priceBasis: ["Menu price basis", "உணவுப் பட்டியல் விலை முறை"],
  pricesExclusive: ["Menu prices + GST", "பட்டியல் விலை + GST"],
  pricesInclusive: ["Menu prices include GST", "பட்டியல் விலையில் GST உள்ளது"],
  addGst: ["Add GST on top of menu prices", "பட்டியல் விலைக்கு மேல் GST சேர்"],
  includeGst: ["Menu prices already include GST", "பட்டியல் விலையில் ஏற்கனவே GST உள்ளது"],
  taxConfirmed: ["Current receipt/tax status confirmed with accountant", "தற்போதைய ரசீது/வரி நிலை கணக்காளரிடம் உறுதி செய்யப்பட்டது"],
  rounding: ["Round final total to nearest rupee", "இறுதித் தொகையை அருகிலுள்ள ரூபாயாக்கு"],
  upiId: ["Merchant UPI ID", "வணிக UPI ID"],
  payee: ["Merchant payee name", "பணம் பெறும் வணிகர் பெயர்"],
  payeeConfirmed: ["I verified this merchant UPI payee", "இந்த வணிக UPI பெறுநரை உறுதிசெய்தேன்"],
  font: ["Receipt typeface", "ரசீது எழுத்துரு"],
  logo: ["Restaurant logo (local image)", "உணவகச் சின்னம் (உள்ளூர் படம்)"],
  menuLogo: ["Use Tamil logo from the supplied menu", "கொடுக்கப்பட்ட உணவுப் பட்டியலின் தமிழ் சின்னத்தைப் பயன்படுத்து"],
  removeLogo: ["Remove current logo", "தற்போதைய சின்னத்தை நீக்கு"],
  footer: ["Receipt footer", "ரசீதின் அடிக்குறிப்பு"],
  saveSetup: ["Save setup", "அமைப்பைச் சேமி"],
  chooseBackup: ["Choose backup folder", "காப்புக் கோப்புறையைத் தேர்வு செய்"],
  findBackups: ["Find backups", "காப்புகளைத் தேடு"],
  saveBackup: ["Save complete backup", "முழுக் காப்பைச் சேமி"],
};

export function workspaceText(key) {
  return t(`restaurant.${key}`);
}

/** Mark only known interface text, never menu names, owner settings or saved receipts. */
function mark(selector, key) {
  document.querySelectorAll(selector).forEach(element => {
    if (element.hasAttribute("data-i18n")) return;
    const text = [...element.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    if (!text) return;
    const span = document.createElement("span");
    span.dataset.i18n = `restaurant.${key}`;
    span.textContent = text.textContent.trim();
    text.replaceWith(span);
  });
}

export function translateWorkspace() {
  translateDocument();
  document.querySelectorAll("[data-label]").forEach(element => {
    const key = element.dataset.label;
    if (Object.hasOwn(uiLabels, key)) {
      element.textContent = element.id === "customer-title" && document.querySelector('#customer-form [name="id"]').value
        ? uiLabels.editCustomer : uiLabels[key];
    }
  });
  for (const key of ["name", "phone", "city"])
    document.querySelector(`#customer-${key}`).placeholder = uiLabels[`${key}Placeholder`];
  const page = document.body.dataset.page;
  const title = document.querySelector("#page-title");
  title.textContent = page === "pos" ? workspaceText("billing") : uiLabels[page] || workspaceText(page);
  const walkIn = document.querySelector('#pos-customer option[value=""]');
  if (walkIn) walkIn.textContent = workspaceText("walkIn");
  updateControls();
}

function saved(key, fallback) {
  try { return localStorage.getItem(key) || fallback; }
  catch (error) { console.warn("Display preference unavailable", error); return fallback; }
}

function saveTheme(theme) {
  try { localStorage.setItem("vglpos.theme", theme); }
  catch (error) { console.warn("Theme could not be saved", error); }
}

function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const button = document.querySelector("#theme-toggle");
  button.setAttribute("aria-pressed", String(dark));
  const description = getLocale() === "ta"
    ? dark ? "ஒளிர் முறைக்கு மாறு" : "இருள் முறைக்கு மாறு"
    : dark ? "Use light mode" : "Use dark mode";
  button.setAttribute("aria-label", description);
  button.title = description;
  document.querySelector("#theme-icon").innerHTML = `<i data-lucide="${dark ? "sun" : "moon-star"}" aria-hidden="true"></i>`;
  refreshIcons(button);
}

function updateControls() {
  const button = document.querySelector("#locale-toggle");
  const tamil = getLocale() === "ta";
  const description = tamil ? "Switch to English" : "தமிழுக்கு மாறு / Switch to Tamil";
  button.setAttribute("aria-label", description);
  button.title = description;
  document.querySelector("#locale-label").textContent = tamil ? "English" : "தமிழ்";
  document.querySelector("#locale-label").lang = tamil ? "en" : "ta";
  applyTheme(document.documentElement.dataset.theme);
}

/** Both dictionaries and fonts ship in the APK; toggles require no network or ledger writes. */
export async function initializePreferences(onLanguageChanged) {
  for (const [selector, key] of [
    [".topbar .eyebrow", "workspace"], [".brand-copy small", "counter"],
    ["#lock-workspace span", "lock"], ["#last-receipt", "reprint"],
    ['[data-view="products"] h2', "menuProducts"], ["#add-product", "addProduct"],
    ["#product-title", "menuProduct"], ['#product-form button.button-primary', "saveProduct"],
    ["#scanner-status span", "localBilling"], ["#cart-empty p", "selectItem"],
    ["#pos-products-empty p", "tryName"],
    ["#upi-notice", "upiNotice"], ['[data-view="settings"] > h2', "setup"],
    ['#settings-form button.button-primary', "saveSetup"],
    ["#choose-backup-folder", "chooseBackup"], ["#scan-backups", "findBackups"], ["#backup-button", "saveBackup"],
    ['#settings-form [name="tax_inclusive"] option[value="false"]', "addGst"],
    ['#settings-form [name="tax_inclusive"] option[value="true"]', "includeGst"],
  ]) mark(selector, key);
  const nav = { billing: "nav.pos", dashboard: "nav.dashboard", products: "nav.products", customers: "nav.customers", sales: "nav.sales", reports: "nav.reports", settings: "nav.settings" };
  for (const [page, key] of Object.entries(nav))
    document.querySelector(`[data-nav="${page}"] span`).dataset.i18n = key;
  for (const [selector, key] of [["#pos-search", "searchMenu"], ["#product-search", "searchProduct"], ["#customer-search", "searchCustomer"]])
    document.querySelector(selector).dataset.i18nPlaceholder = `restaurant.${key}`;
  const fields = { name: "name", portion: "portion", category: "category", price: "price", photo: "photo", remove_image: "removePhoto", active: "active" };
  for (const [field, key] of Object.entries(fields)) {
    const selector = `#product-form [name="${field}"]`;
    const label = document.querySelector(selector).closest("label");
    // Use a stable selector only while marking the original static form text.
    label.dataset.preferenceField = field;
    mark(`[data-preference-field="${field}"]`, key);
  }
  const settingsFields = { name: "restaurantName", phone: "phone", address: "address", cashier: "cashier", series: "series", receipt_mode: "receiptMode", gstin: "gstin", tax_percent: "gst", tax_inclusive: "priceBasis", tax_confirmed: "taxConfirmed", round_rupee: "rounding", upi_id: "upiId", upi_payee: "payee", upi_confirmed: "payeeConfirmed", receipt_font: "font", logo: "logo", menu_logo: "menuLogo", remove_logo: "removeLogo", footer: "footer" };
  for (const [field, key] of Object.entries(settingsFields)) {
    const label = document.querySelector(`#settings-form [name="${field}"]`).closest("label");
    label.dataset.settingsPreference = field;
    mark(`[data-settings-preference="${field}"]`, key);
  }
  for (const [selector, key] of [
    ['[data-view="customers"] h2', "customer"], ["#add-customer", "addCustomer"],
    ['#customer-form button.button-primary', "saveCustomer"],
    ['#customer-form button[data-close]', "cancel"], ['#product-form button[data-close]', "cancel"],
    ["#hold-bill", "hold"], ["#recall-bill", "recall"], ["#add-billing-customer span", "addCustomer"],
  ]) {
    const element = document.querySelector(selector);
    if (element) element.dataset.label = key;
  }
  for (const [locale, base, index] of [["ta", tamil, 1], ["en", english, 0]])
    installCatalogue(locale, { ...base, ...Object.fromEntries(Object.entries(words).map(([key, values]) => [`restaurant.${key}`, values[index]])),
      "pos.empty_cart_hint": index ? "தொடங்க உணவுப் பொருளைத் தேர்ந்தெடுக்கவும்." : "Select a menu item to begin.",
      "pos.no_products_hint": index ? "வேறு பெயர் அல்லது அளவைத் தேடவும்." : "Try another menu name or portion.",
    });
  applyTheme(saved("vglpos.theme", "light"));
  await loadLocale(saved("vglpos.locale", "en"));
  updateControls();
  document.querySelector("#theme-toggle").addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    saveTheme(theme);
    applyTheme(theme);
  });
  document.querySelector("#locale-toggle").addEventListener("click", async () => {
    const button = document.querySelector("#locale-toggle");
    button.disabled = true;
    try {
      await loadLocale(getLocale() === "en" ? "ta" : "en");
      updateControls();
      await onLanguageChanged();
      translateWorkspace();
    } catch (error) {
      console.error("Language change failed", error);
    } finally { button.disabled = false; }
  });
}

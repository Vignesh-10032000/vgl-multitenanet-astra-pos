const SUPPORTED_LOCALES = new Set(["en", "ta"]);
const catalogues = new Map();
let activeLocale = "en";

function normalizedLocale(locale) {
  const candidate = String(locale || "").toLowerCase().split("-")[0];
  return SUPPORTED_LOCALES.has(candidate) ? candidate : "en";
}

export function getLocale() {
  return activeLocale;
}

export function intlLocale(locale = activeLocale) {
  return normalizedLocale(locale) === "ta" ? "ta-IN" : "en-IN";
}

export async function loadLocale(locale) {
  const normalized = normalizedLocale(locale);
  if (!catalogues.has(normalized)) {
    const response = await fetch(`/static/i18n/${normalized}.json`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Unable to load locale ${normalized}.`);
    }
    catalogues.set(normalized, await response.json());
  }
  activeLocale = normalized;
  localStorage.setItem("vglpos.locale", normalized);
  document.documentElement.lang = normalized;
  translateDocument();
  document.dispatchEvent(new CustomEvent("vgl:locale-changed", { detail: { locale: normalized } }));
  return normalized;
}

export async function initializeI18n() {
  const saved = localStorage.getItem("vglpos.locale");
  const browser = navigator.language;
  return loadLocale(saved || browser);
}

export function t(key, params = {}) {
  const catalogue = catalogues.get(activeLocale) || {};
  const english = catalogues.get("en") || {};
  const template = catalogue[key] || english[key] || key;
  return Object.entries(params).reduce(
    (message, [name, value]) => message.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

export function translateDocument(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
  });
  const localeLabel = document.querySelector("#locale-label");
  if (localeLabel) localeLabel.textContent = activeLocale === "en" ? "தமிழ்" : "EN";
}

function decimalParts(value, scale = 2) {
  const match = String(value ?? "0").trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return { negative: false, integer: 0n, fraction: "0".repeat(scale) };
  return {
    negative: match[1] === "-",
    integer: BigInt(match[2]),
    fraction: (match[3] || "").padEnd(scale, "0").slice(0, scale),
  };
}

export function formatMoney(value, locale = activeLocale) {
  const { negative, integer, fraction } = decimalParts(value, 2);
  const grouped = new Intl.NumberFormat(intlLocale(locale), {
    maximumFractionDigits: 0,
    useGrouping: true,
  }).format(integer);
  return `${negative ? "-" : ""}₹${grouped}.${fraction}`;
}

export function formatQuantity(value, locale = activeLocale) {
  const { negative, integer, fraction } = decimalParts(value, 3);
  const grouped = new Intl.NumberFormat(intlLocale(locale), {
    maximumFractionDigits: 0,
    useGrouping: true,
  }).format(integer);
  const trimmed = fraction.replace(/0+$/, "");
  return `${negative ? "-" : ""}${grouped}${trimmed ? `.${trimmed}` : ""}`;
}

export function formatInteger(value, locale = activeLocale) {
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 0 }).format(
    BigInt(String(value || 0)),
  );
}

export function formatDate(value, options = { dateStyle: "medium" }, locale = activeLocale) {
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat(intlLocale(locale), options).format(date);
}

export function localizedName(record, locale = activeLocale) {
  const preferred = locale === "ta" ? record.name_ta : record.name_en;
  return preferred || record.name_en || record.name_ta || record.name || record.sku || "—";
}

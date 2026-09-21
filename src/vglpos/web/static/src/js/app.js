import "../css/main.css";

import { getLocale, initializeI18n, loadLocale, t } from "./i18n.js";
import { getSession, logout, requireSession } from "./session.js";
import { initializeDialogs, openDialog, refreshIcons, showToast } from "./ui.js";

function applyTheme(theme) {
  const normalized = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = normalized;
  localStorage.setItem("vglpos.theme", normalized);
  document.dispatchEvent(new CustomEvent("vgl:theme-changed", { detail: { theme: normalized } }));
}

function applyPermissions(session) {
  const permissions = new Set(session?.user?.permissions || []);
  document.querySelectorAll("[data-permission]").forEach((element) => {
    element.classList.toggle("is-hidden", !permissions.has(element.dataset.permission));
  });
  document.querySelectorAll("[data-permission-all]").forEach((element) => {
    const required = element.dataset.permissionAll.split(",");
    element.classList.toggle("is-hidden", !required.every((code) => permissions.has(code)));
  });
}

function populateUser(session) {
  const name = session?.user?.full_name || "User";
  const roles = session?.user?.roles || [];
  const nameElement = document.querySelector("#user-name");
  const roleElement = document.querySelector("#user-role");
  const avatar = document.querySelector("#user-avatar");
  if (nameElement) nameElement.textContent = name;
  if (roleElement) roleElement.textContent = roles.join(", ") || "—";
  if (avatar) avatar.textContent = name.trim().slice(0, 1).toUpperCase() || "U";
}

function initializeNavigation() {
  const page = document.body.dataset.page;
  document.querySelector(`[data-nav="${page}"]`)?.classList.add("is-active");
}

function initializeConnectivity() {
  const dot = document.querySelector(".status-dot");
  const label = dot?.nextElementSibling;
  const render = () => {
    if (!dot || !label) return;
    dot.dataset.offline = String(!navigator.onLine);
    label.textContent = navigator.onLine ? t("status.online") : t("status.offline");
  };
  addEventListener("online", render);
  addEventListener("offline", render);
  render();
}

async function initialize() {
  applyTheme(localStorage.getItem("vglpos.theme") || "light");
  try {
    await initializeI18n();
  } catch {
    showToast("Language resources could not be loaded.", { tone: "warning" });
  }
  initializeDialogs();
  refreshIcons();
  initializeNavigation();
  initializeConnectivity();

  let session = getSession();
  if (document.body.dataset.authRequired === "true") session = requireSession();
  if (session) {
    populateUser(session);
    applyPermissions(session);
  }

  document.querySelector("#theme-toggle")?.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
  document.querySelector("#locale-toggle")?.addEventListener("click", async () => {
    await loadLocale(getLocale() === "en" ? "ta" : "en");
  });
  document.querySelector("#logout-button")?.addEventListener("click", logout);
  document.addEventListener("vgl:session-expired", () => openDialog("#session-expired-dialog"));
  document.dispatchEvent(new CustomEvent("vgl:app-ready", { detail: { session } }));
  return session;
}

const appReady = initialize();

function whenAppReady(callback) {
  appReady.then(callback);
}

export { applyTheme, whenAppReady };

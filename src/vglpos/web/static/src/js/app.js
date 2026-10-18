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
    element.classList.toggle("permission-denied", !permissions.has(element.dataset.permission));
  });
  document.querySelectorAll("[data-permission-all]").forEach((element) => {
    const required = element.dataset.permissionAll.split(",");
    element.classList.toggle("permission-denied", !required.every((code) => permissions.has(code)));
  });
}

function populateUser(session) {
  const name = session?.user?.full_name || "User";
  const roles = session?.user?.roles || [];
  const nameElement = document.querySelector("#user-name");
  const roleElement = document.querySelector("#user-role");
  const avatar = document.querySelector("#user-avatar");
  if (nameElement) nameElement.textContent = name;
  if (roleElement) roleElement.textContent = roles.map((role) => role.replaceAll("_", " ")).join(", ") || "—";
  if (avatar) avatar.textContent = name.trim().slice(0, 1).toUpperCase() || "U";
}

function initializeNavigation() {
  const page = document.body.dataset.page;
  const active = document.querySelector(`[data-nav="${page}"]`);
  active?.classList.add("is-active");
  if (active && matchMedia("(max-width: 720px)").matches) {
    requestAnimationFrame(() => {
      const nav = active.parentElement;
      nav.scrollLeft = active.offsetLeft - (nav.clientWidth - active.clientWidth) / 2;
    });
  }
}

function initializeConnectivity() {
  const dot = document.querySelector("#connectivity-status .status-dot");
  const label = document.querySelector("#connectivity-label");
  const badge = document.querySelector("#sync-queue-count");
  const render = (detail = {}) => {
    if (!dot || !label) return;
    const online = detail.online ?? navigator.onLine;
    const queued = detail.total || 0;
    dot.dataset.offline = String(!online);
    dot.dataset.syncing = String(Boolean(detail.syncing));
    if (detail.syncing) {
      label.textContent = t("status.syncing", {
        current: detail.syncing,
        total: detail.syncTotal,
      });
    } else if (!online) {
      label.textContent = queued
        ? t("status.offline_queued", { count: queued })
        : t("status.offline");
    } else {
      label.textContent = queued
        ? t("status.online_queued", { count: queued })
        : t("status.online");
    }
    if (badge) {
      badge.textContent = String(queued);
      badge.classList.toggle("is-hidden", queued === 0);
    }
  };
  render();
  document.addEventListener("vgl:sync-status", (event) => render(event.detail));
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
    import("./offline.js")
      .then(({ initializeOffline }) => initializeOffline(session))
      .catch((error) => {
        showToast(error.message, { tone: "warning", duration: 8000 });
      });
  }

  document.querySelector("#theme-toggle")?.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
  document.querySelector("#locale-toggle")?.addEventListener("click", async () => {
    await loadLocale(getLocale() === "en" ? "ta" : "en");
  });
  document.querySelector("#logout-button")?.addEventListener("click", logout);
  document.addEventListener("vgl:session-expired", () => openDialog("#session-expired-dialog"));
  document.addEventListener("vgl:offline-error", (event) => {
    showToast(event.detail.message, { tone: "warning", duration: 8000 });
  });
  document.dispatchEvent(new CustomEvent("vgl:app-ready", { detail: { session } }));
  return session;
}

const appReady = initialize();

function whenAppReady(callback) {
  appReady.then(callback);
}

export { applyTheme, whenAppReady };

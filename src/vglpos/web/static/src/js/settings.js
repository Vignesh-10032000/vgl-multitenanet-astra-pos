import { LockKeyhole, MonitorCog, Moon, Save, ShieldCheck, Store, Sun } from "lucide";

import { getLocale, loadLocale, t } from "./i18n.js";
import { apiJson, logout } from "./session.js";
import { registerIcons, showToast } from "./ui.js";
import { applyTheme, whenAppReady } from "./app.js";

registerIcons({ LockKeyhole, MonitorCog, Moon, Save, ShieldCheck, Store, Sun });

function selectSegment(group, value, attribute) {
  group.querySelectorAll(`[${attribute}]`).forEach((button) => {
    button.classList.toggle("is-active", button.getAttribute(attribute) === value);
  });
}

function showTab(name) {
  document.querySelectorAll("[data-tab-target]").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tabTarget === name);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("is-hidden", panel.dataset.tabPanel !== name);
  });
}

function loadWorkstationSettings() {
  const theme = localStorage.getItem("vglpos.theme") || "light";
  const paper = localStorage.getItem("vglpos.paper") || "80";
  const sound = localStorage.getItem("vglpos.scannerSounds") !== "false";
  selectSegment(document.querySelector("#workstation-settings"), getLocale(), "data-locale-value");
  selectSegment(document.querySelector("#workstation-settings"), theme, "data-theme-value");
  selectSegment(document.querySelector("#workstation-settings"), paper, "data-paper-value");
  document.querySelector("#scanner-sounds").checked = sound;
}

async function loadStoreProfile() {
  try {
    const profile = await apiJson("/api/v1/settings/store-profile");
    const form = document.querySelector("#store-settings");
    form.elements.name.value = profile.name;
    form.elements.legal_name.value = profile.legal_name;
    form.elements.gstin.value = profile.gstin || "";
    form.elements.phone.value = profile.phone;
    form.elements.address_line1.value = profile.address_line1;
    form.elements.address_line2.value = profile.address_line2 || "";
    form.elements.city.value = profile.city;
    form.elements.state.value = profile.state;
    form.elements.postal_code.value = profile.postal_code;
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  }
}

async function saveStoreProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const value = (name) => form.elements[name].value.trim();
  const error = document.querySelector("#store-form-error");
  error.textContent = "";
  try {
    await apiJson("/api/v1/settings/store-profile", {
      method: "PUT",
      body: JSON.stringify({
        name: value("name"),
        legal_name: value("legal_name"),
        gstin: value("gstin") || null,
        phone: value("phone"),
        address_line1: value("address_line1"),
        address_line2: value("address_line2") || null,
        city: value("city"),
        state: value("state"),
        postal_code: value("postal_code"),
      }),
    });
    showToast(t("settings.saved"), { tone: "success" });
  } catch (failure) {
    error.textContent = failure.message;
  }
}

async function lockCounter() {
  try {
    await apiJson("/api/v1/auth/screen-lock", { method: "POST", body: "{}" });
    location.replace("/login?locked=1");
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  }
}

whenAppReady(() => {
  loadWorkstationSettings();
  loadStoreProfile();
  document.querySelectorAll("[data-tab-target]").forEach((tab) => {
    tab.addEventListener("click", () => showTab(tab.dataset.tabTarget));
  });
  document.querySelectorAll("[data-locale-value]").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadLocale(button.dataset.localeValue);
      loadWorkstationSettings();
    });
  });
  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.addEventListener("click", () => {
      applyTheme(button.dataset.themeValue);
      loadWorkstationSettings();
    });
  });
  document.querySelectorAll("[data-paper-value]").forEach((button) => {
    button.addEventListener("click", () => {
      localStorage.setItem("vglpos.paper", button.dataset.paperValue);
      loadWorkstationSettings();
    });
  });
  document.querySelector("#workstation-settings").addEventListener("submit", (event) => {
    event.preventDefault();
    localStorage.setItem("vglpos.scannerSounds", String(document.querySelector("#scanner-sounds").checked));
    showToast(t("settings.saved"), { tone: "success" });
  });
  document.querySelector("#store-settings").addEventListener("submit", saveStoreProfile);
  document.querySelector("#lock-counter").addEventListener("click", lockCounter);
  document.querySelector("#settings-logout").addEventListener("click", logout);
});

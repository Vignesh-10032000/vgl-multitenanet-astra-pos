import { LockKeyhole, MonitorCog, Moon, Save, ShieldCheck, Store, Sun, Users } from "lucide";
import { initializeAccessSettings } from "./settings-access.js";

import { getLocale, loadLocale, t } from "./i18n.js";
import { apiJson, logout } from "./session.js";
import { registerIcons, showToast } from "./ui.js";
import { applyTheme, whenAppReady } from "./app.js";

registerIcons({ LockKeyhole, MonitorCog, Moon, Save, ShieldCheck, Store, Sun, Users });

function renderLogo(profile) {
  const image = document.querySelector("#store-logo-preview");
  image.hidden = !profile.logo_data_uri;
  if (profile.logo_data_uri) image.src = profile.logo_data_uri;
  else image.removeAttribute("src");
  document.querySelector("#remove-store-logo").disabled = !profile.logo_data_uri;
}

async function saveLogo(imageBase64) {
  const error = document.querySelector("#logo-error");
  error.textContent = "";
  document.querySelector("#store-logo-file").disabled = true;
  document.querySelector("#remove-store-logo").disabled = true;
  try {
    renderLogo(await apiJson("/api/v1/settings/store-logo", { method: "PUT", body: JSON.stringify({ image_base64: imageBase64 }) }));
    showToast(t("settings.saved"), { tone: "success" });
  } catch (failure) {
    error.textContent = failure.message;
    document.querySelector("#remove-store-logo").disabled = document.querySelector("#store-logo-preview").hidden;
  } finally { document.querySelector("#store-logo-file").disabled = false; }
}

function uploadLogo(event) {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 512000 || !["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    document.querySelector("#logo-error").textContent = t("settings.logo_hint");
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => { saveLogo(String(reader.result).split(",")[1]); event.target.value = ""; };
  reader.onerror = () => { document.querySelector("#logo-error").textContent = t("settings.logo_read_error"); };
  reader.readAsDataURL(file);
}

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
    renderLogo(profile);
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
  initializeAccessSettings();
  document.querySelector("#store-logo-file").addEventListener("change", uploadLogo);
  document.querySelector("#remove-store-logo").addEventListener("click", () => saveLogo(null));
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

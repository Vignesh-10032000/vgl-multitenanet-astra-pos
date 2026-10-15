import { ArrowRight, Eye, EyeOff, Sparkles } from "lucide";

import { whenAppReady } from "./app.js";
import { getLocale, loadLocale, t } from "./i18n.js";
import { getSession, saveSession } from "./session.js";
import { refreshIcons, registerIcons, setBusy } from "./ui.js";

registerIcons({ ArrowRight, Eye, EyeOff, Sparkles });

function optionalInteger(form, name) {
  const value = form.elements[name].value.trim();
  return value ? Number.parseInt(value, 10) : null;
}

function redirectAfterLogin() {
  const next = new URLSearchParams(location.search).get("next");
  location.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/pos");
}

async function requestLogin(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || t("login.failed"));
  saveSession(result);
  redirectAfterLogin();
}

async function submitLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.querySelector("#login-error");
  error.textContent = "";
  setBusy(form, true);
  const payload = {
    company_code: form.elements.company_code.value.trim(),
    username: form.elements.username.value.trim(),
    password: form.elements.password.value,
    branch_id: optionalInteger(form, "branch_id"),
    terminal_id: optionalInteger(form, "terminal_id"),
    mfa_code: form.elements.mfa_code.value.trim() || null,
  };
  try {
    await requestLogin("/api/v1/auth/login", payload);
  } catch (failure) {
    if (/mfa|authentication code/i.test(failure.message || "")) {
      document.querySelector("#mfa-field").classList.remove("is-hidden");
      form.elements.mfa_code.focus();
    }
    error.textContent = failure.message || t("login.failed");
  } finally {
    setBusy(form, false);
  }
}

async function submitDemoLogin() {
  const container = document.querySelector(".demo-access");
  const error = document.querySelector("#login-error");
  error.textContent = "";
  setBusy(container, true);
  try {
    await requestLogin("/api/v1/auth/demo-login", {});
  } catch (failure) {
    error.textContent = failure.message || t("login.demo_failed");
  } finally {
    setBusy(container, false);
  }
}

whenAppReady(() => {
  if (getSession()) location.replace("/pos");
  const form = document.querySelector("#login-form");
  form.addEventListener("submit", submitLogin);
  document.querySelector("#demo-login").addEventListener("click", submitDemoLogin);
  document.querySelector("#password-toggle").addEventListener("click", (event) => {
    const password = form.elements.password;
    password.type = password.type === "password" ? "text" : "password";
    event.currentTarget.querySelector("svg")?.remove();
    event.currentTarget.querySelector("i")?.remove();
    const icon = document.createElement("i");
    icon.dataset.lucide = password.type === "password" ? "eye" : "eye-off";
    event.currentTarget.prepend(icon);
    refreshIcons(event.currentTarget);
  });
  document.querySelector("#login-locale").addEventListener("click", async (event) => {
    await loadLocale(getLocale() === "en" ? "ta" : "en");
    event.currentTarget.querySelector("span").textContent = getLocale() === "en" ? "தமிழ்" : "EN";
  });
});

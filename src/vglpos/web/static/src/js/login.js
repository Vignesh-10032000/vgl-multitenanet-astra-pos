import { ArrowRight, Eye, EyeOff } from "lucide";

import { whenAppReady } from "./app.js";
import { getLocale, loadLocale, t } from "./i18n.js";
import { getSession, saveSession } from "./session.js";
import { refreshIcons, registerIcons, setBusy } from "./ui.js";

registerIcons({ ArrowRight, Eye, EyeOff });

function optionalInteger(form, name) {
  const value = form.elements[name].value.trim();
  return value ? Number.parseInt(value, 10) : null;
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
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      if (/mfa|authentication code/i.test(result.detail || "")) {
        document.querySelector("#mfa-field").classList.remove("is-hidden");
        form.elements.mfa_code.focus();
      }
      throw new Error(result.detail || t("login.failed"));
    }
    saveSession(result);
    const next = new URLSearchParams(location.search).get("next");
    location.replace(next?.startsWith("/") && !next.startsWith("//") ? next : "/pos");
  } catch (failure) {
    error.textContent = failure.message || t("login.failed");
  } finally {
    setBusy(form, false);
  }
}

whenAppReady(() => {
  if (getSession()) location.replace("/pos");
  const form = document.querySelector("#login-form");
  form.addEventListener("submit", submitLogin);
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

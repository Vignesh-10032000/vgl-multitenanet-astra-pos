import { ArrowRight, ArrowUpRight, CloudOff, ExternalLink, Eye, EyeOff, Keyboard, Mail, MessageCircle, PauseCircle, Phone, Scale, Sparkles, WalletCards } from "lucide";

import "../css/login.css";

import { whenAppReady } from "./app.js";
import { getLocale, loadLocale, t } from "./i18n.js";
import { getSession, saveSession } from "./session.js";
import { refreshIcons, registerIcons, setBusy } from "./ui.js";

registerIcons({ ArrowRight, ArrowUpRight, CloudOff, ExternalLink, Eye, EyeOff, Keyboard, Mail, MessageCircle, PauseCircle, Phone, Scale, Sparkles, WalletCards });

function optionalInteger(form, name) {
  const value = form.elements[name].value.trim();
  return value ? Number.parseInt(value, 10) : null;
}

function redirectAfterLogin(loginRole = "staff") {
  const next = new URLSearchParams(location.search).get("next");
  const safePath = next?.startsWith("/") && !next.startsWith("//") && !next.includes("\\");
  const target = safePath ? new URL(next, location.origin) : null;
  location.replace(target?.origin === location.origin
    ? `${target.pathname}${target.search}${target.hash}`
    : loginRole === "staff" ? "/pos" : "/");
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
    signal: AbortSignal.timeout(20000),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const failure = new Error(result.detail || t("login.failed"));
    failure.status = response.status;
    failure.requestId = result.request_id || response.headers.get("X-Request-Id");
    throw failure;
  }
  if (!result.access_token || !result.refresh_token || !result.user) {
    throw new Error(t("login.failed"));
  }
  saveSession(result);
  redirectAfterLogin(payload.login_role);
}

function showLoginError(element, failure, demo = false) {
  let message = failure.message || t(demo ? "login.demo_failed" : "login.failed");
  if (failure.status >= 500) {
    message = t(demo ? "login.demo_unavailable" : "login.service_unavailable");
  } else if (failure.status === 429) {
    message = t("login.rate_limited");
  } else if (demo && failure.status === 404) {
    message = t("login.demo_failed");
  } else if (failure.name === "TimeoutError" || failure.name === "TypeError") {
    message = t("login.connection_failed");
  }
  element.replaceChildren(document.createTextNode(message));
  if (failure.requestId) {
    const reference = document.createElement("small");
    reference.textContent = t("login.error_reference", { reference: failure.requestId });
    element.append(reference);
  }
}

async function submitLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (form.getAttribute("aria-busy") === "true") return;
  const error = document.querySelector("#login-error");
  error.textContent = "";
  form.elements.company_code.value = form.elements.company_code.value.trim();
  form.elements.username.value = form.elements.username.value.trim();
  if (!form.reportValidity()) return;
  setBusy(form, true);
  const payload = {
    company_code: form.elements.company_code.value.trim(),
    username: form.elements.username.value.trim(),
    password: form.elements.password.value,
    branch_id: optionalInteger(form, "branch_id"),
    terminal_id: optionalInteger(form, "terminal_id"),
    mfa_code: form.elements.mfa_code.value.trim() || null,
    login_role: form.elements.login_role.value,
  };
  try {
    await requestLogin("/api/v1/auth/login", payload);
  } catch (failure) {
    if (/mfa|authentication code/i.test(failure.message || "")) {
      document.querySelector("#mfa-field").classList.remove("is-hidden");
      form.elements.mfa_code.required = true;
      form.elements.mfa_code.focus();
    }
    showLoginError(error, failure);
  } finally {
    setBusy(form, false);
  }
}

async function submitDemoLogin() {
  const container = document.querySelector(".demo-access");
  if (container.getAttribute("aria-busy") === "true") return;
  const error = document.querySelector("#demo-error");
  error.textContent = "";
  setBusy(container, true);
  try {
    await requestLogin("/api/v1/auth/demo-login", {});
  } catch (failure) {
    showLoginError(error, failure, true);
  } finally {
    setBusy(container, false);
  }
}

whenAppReady(() => {
  if (getSession()) redirectAfterLogin();
  const form = document.querySelector("#login-form");
  form.addEventListener("submit", submitLogin);
  const syncRole = () => {
    const label = document.querySelector("#login-submit-label");
    label.dataset.i18n = `login.submit_${form.elements.login_role.value}`;
    label.textContent = t(label.dataset.i18n);
  };
  form.querySelectorAll('[name="login_role"]').forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelector("#login-error").textContent = "";
      syncRole();
    });
  });
  syncRole();
  const demoButton = document.querySelector("#demo-login");
  demoButton.addEventListener("click", submitDemoLogin);
  demoButton.disabled = false;
  const localeButton = document.querySelector("#login-locale");
  const passwordToggle = document.querySelector("#password-toggle");
  const syncControls = () => {
    localeButton.querySelector("span").textContent = getLocale() === "en" ? "தமிழ்" : "EN";
    const label = t(form.elements.password.type === "password" ? "login.show_password" : "login.hide_password");
    passwordToggle.setAttribute("aria-label", label);
    passwordToggle.title = label;
  };
  syncControls();
  passwordToggle.addEventListener("click", (event) => {
    const password = form.elements.password;
    password.type = password.type === "password" ? "text" : "password";
    syncControls();
    event.currentTarget.querySelector("svg")?.remove();
    event.currentTarget.querySelector("i")?.remove();
    const icon = document.createElement("i");
    icon.dataset.lucide = password.type === "password" ? "eye" : "eye-off";
    event.currentTarget.prepend(icon);
    refreshIcons(event.currentTarget);
  });
  localeButton.addEventListener("click", async () => {
    try {
      await loadLocale(getLocale() === "en" ? "ta" : "en");
      syncControls();
    } catch {
      document.querySelector("#login-error").textContent = t("login.language_failed");
    }
  });
});

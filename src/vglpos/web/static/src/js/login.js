import { getSession, saveSession } from "./session.js";

const form = document.querySelector("#form");
const status = document.querySelector("#status");
const submit = form.querySelector('[type="submit"]');
const demoButton = document.querySelector("#demo-login");

function redirectAfterLogin(user = {}) {
  const next = new URLSearchParams(location.search).get("next");
  const safePath = next?.startsWith("/") && !next.startsWith("//") && !next.includes("\\");
  const target = safePath ? new URL(next, location.origin) : null;
  const roles = (user.roles || []).map((role) => role.toUpperCase());
  location.replace(target?.origin === location.origin
    ? `${target.pathname}${target.search}${target.hash}`
    : roles.includes("ADMIN") || roles.includes("SUPER_ADMIN") ? "/" : "/pos");
}

function showError(message) {
  status.classList.add("err");
  status.textContent = message;
}

demoButton.addEventListener("click", async (event) => {
  event.preventDefault();
  if (demoButton.getAttribute("aria-busy") === "true" || form.getAttribute("aria-busy") === "true") return;
  status.classList.remove("err");
  status.textContent = "";
  demoButton.setAttribute("aria-busy", "true");
  demoButton.setAttribute("aria-disabled", "true");
  submit.disabled = true;
  try {
    const response = await fetch("/api/v1/auth/demo-login", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: "{}",
      signal: AbortSignal.timeout(20000),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.access_token || !result.refresh_token || !result.user) {
      const error = new Error("Unable to open the demo. Please try again.");
      error.status = response.status;
      error.requestId = result.request_id || response.headers.get("X-Request-Id");
      throw error;
    }
    saveSession(result);
    location.replace("/pos");
  } catch (error) {
    showError(error.status === 404 ? "The demo is not enabled on this server."
      : error.status === 429 ? "Too many demo requests. Please wait and try again."
        : error.status >= 500 ? "The demo is temporarily unavailable. Please try again."
          : error.name === "TimeoutError" || error.name === "TypeError"
            ? "Unable to connect. Check your connection and try again."
            : error.message);
    if (error.requestId) status.append(` Support reference: ${error.requestId}`);
  } finally {
    demoButton.setAttribute("aria-busy", "false");
    demoButton.removeAttribute("aria-disabled");
    submit.disabled = false;
  }
});

function optionalId(id) {
  const input = document.getElementById(id);
  const value = input.value.trim();
  if (!value) return null;
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number <= 0) {
    input.setCustomValidity("Enter a positive whole number.");
    input.reportValidity();
    throw new Error(`${id === "branch" ? "Branch" : "Terminal"} ID must be a positive whole number.`);
  }
  input.setCustomValidity("");
  return number;
}

for (const id of ["branch", "terminal"]) {
  document.getElementById(id).addEventListener("input", (event) => {
    event.currentTarget.setCustomValidity("");
  });
}

function showMfaField() {
  let field = document.getElementById("mfa-code");
  if (!field) {
    const label = document.createElement("label");
    label.htmlFor = "mfa-code";
    label.append("6-digit authentication code");
    field = document.createElement("input");
    field.id = "mfa-code";
    field.name = "mfa_code";
    field.inputMode = "numeric";
    field.pattern = "[0-9]{6}";
    field.maxLength = 6;
    field.autocomplete = "one-time-code";
    field.required = true;
    label.append(field);
    form.insertBefore(label, submit);
  }
  field.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (form.getAttribute("aria-busy") === "true" || demoButton.getAttribute("aria-busy") === "true") return;
  status.classList.remove("err");
  status.textContent = "";

  const company = document.getElementById("company");
  const username = document.getElementById("user");
  const password = document.getElementById("pass");
  company.value = company.value.trim();
  username.value = username.value.trim();
  if (!form.reportValidity()) return;

  let branchId;
  let terminalId;
  try {
    branchId = optionalId("branch");
    terminalId = optionalId("terminal");
  } catch (error) {
    showError(error.message);
    return;
  }

  form.setAttribute("aria-busy", "true");
  submit.disabled = true;
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        company_code: company.value,
        username: username.value,
        password: password.value,
        branch_id: branchId,
        terminal_id: terminalId,
        mfa_code: document.getElementById("mfa-code")?.value.trim() || null,
      }),
      signal: AbortSignal.timeout(20000),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(result.detail || "Sign in failed. Please try again.");
      error.status = response.status;
      throw error;
    }
    if (!result.access_token || !result.refresh_token || !result.user) {
      throw new Error("Sign in failed. Please try again.");
    }
    saveSession(result);
    redirectAfterLogin(result.user);
  } catch (error) {
    if (/mfa|authentication code/i.test(error.message || "")) showMfaField();
    showError(error.status === 429 ? "Too many sign-in attempts. Please wait and try again."
      : error.name === "TimeoutError" || error.name === "TypeError"
        ? "Unable to connect. Check your connection and try again."
        : error.message);
  } finally {
    form.setAttribute("aria-busy", "false");
    submit.disabled = false;
  }
});

if (getSession()) redirectAfterLogin(getSession().user);

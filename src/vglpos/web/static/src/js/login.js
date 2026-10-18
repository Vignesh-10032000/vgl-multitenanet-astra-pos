import { getSession, saveSession } from "./session.js";

const form = document.querySelector("#form");
const status = document.querySelector("#status");
const submit = form.querySelector('[type="submit"]');

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
  if (form.getAttribute("aria-busy") === "true") return;
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

import { OwnerAccess } from "./access.js";
import { workspaceText } from "./preferences.js";

export async function createAccessUI({
  ledger,
  unlocked,
  recover,
  backedUp,
  beforeRecovery,
  reload,
}) {
  const access = new OwnerAccess(ledger);
  const screen = document.querySelector("#access-screen"),
    form = document.querySelector("#access-form");
  let recovery = null,
    busy = false;
  let firstShow = true;
  let submitKey = "signIn";
  const password = form.elements.password;
  const toggle = document.querySelector("#access-password-toggle");
  function updateToggle() {
    const visible = password.type === "text";
    toggle.setAttribute("aria-label", workspaceText(visible ? "hidePassword" : "showPassword"));
    toggle.setAttribute("aria-pressed", String(visible));
    toggle.innerHTML = visible
      ? '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.5 5.3A11 11 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.2 4.1M6.1 6.1A20 20 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.3-1.3"/></svg>'
      : '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  }
  toggle.addEventListener("click", () => {
    const { selectionStart, selectionEnd, selectionDirection } = password;
    password.type = password.type === "password" ? "text" : "password";
    password.focus({ preventScroll: true });
    password.setSelectionRange(selectionStart, selectionEnd, selectionDirection);
    updateToggle();
  });
  document.addEventListener("restaurant:language-changed", updateToggle);
  updateToggle();
  function text(selector, key) {
    const element = document.querySelector(selector);
    element.dataset.i18n = `restaurant.${key}`;
    element.textContent = workspaceText(key);
  }
  async function show() {
    document.body.dataset.locked = "true";
    screen.hidden = false;
    const account = recovery
      ? await access.recoveryAccount(recovery.data)
      : await access.account();
    text("#access-title", recovery ? "recoverTitle" : account ? "welcome" : "setupTitle");
    document.querySelector("#access-description").textContent = recovery
      ? `${recovery.billCount} saved bills · ${new Date(recovery.data.created_at).toLocaleString("en-IN")}. Sign in to replace this device's current ledger with this backup.`
      : account
        ? workspaceText("signInHelp")
        : workspaceText("setupHelp");
    document.querySelector("#access-confirm-row").hidden = Boolean(account);
    form.elements.confirm.required = !account;
    form.elements.password.autocomplete = account
      ? "current-password"
      : "new-password";
    if (!firstShow) {
      form.elements.username.value = "";
      form.elements.password.value = "";
      form.elements.confirm.value = "";
    }
    firstShow = false;
    password.type = "password";
    updateToggle();
    submitKey = account ? recovery ? "signInRecover" : "signIn" : "createAccount";
    text("#access-submit", submitKey);
    if (!recovery) {
      document.querySelector("#access-description").dataset.i18n = `restaurant.${account ? "signInHelp" : "setupHelp"}`;
    } else delete document.querySelector("#access-description").dataset.i18n;
    document.querySelector("#access-error").textContent = "";
    delete document.querySelector("#access-error").dataset.i18n;
    form.hidden = false;
  }
  async function enter() {
    document.body.dataset.locked = "false";
    try { await unlocked(); screen.hidden = true; }
    catch (error) { document.body.dataset.locked = "true"; throw error; }
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const button = document.querySelector("#access-submit");
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    text("#access-submit", "signingIn");
    document.querySelector("#access-error").textContent = "";
    delete document.querySelector("#access-error").dataset.i18n;
    try {
      const username = form.elements.username.value,
        password = form.elements.password.value;
      const account = recovery
        ? await access.recoveryAccount(recovery.data)
        : await access.account();
      if (!account && password !== form.elements.confirm.value)
        throw new Error("Passwords do not match");
      if (recovery) {
        const candidate = recovery;
        await access.recover(
          {
            ...candidate,
            restore: async () => {
              await beforeRecovery();
              return candidate.restore();
            },
          },
          username,
          password,
        );
        await reload();
        return;
      }
      if (account) await access.login(username, password);
      else {
        await access.setup(username, password);
        await backedUp();
      }
      await enter();
    } catch (error) {
      const key = {
        "Username or password is incorrect": "incorrectLogin",
        "Backup username or password is incorrect": "incorrectBackupLogin",
        "Passwords do not match": "passwordMismatch",
        "Too many attempts. Wait 30 seconds and try again.": "loginWait",
      }[error.message];
      const target = document.querySelector("#access-error");
      if (key) { target.dataset.i18n = `restaurant.${key}`; target.textContent = workspaceText(key); }
      else { delete target.dataset.i18n; target.textContent = error.message; }
    } finally {
      button.disabled = false;
      busy = false;
      form.setAttribute("aria-busy", "false");
      text("#access-submit", submitKey);
    }
  });
  document.querySelector("#lock-workspace").addEventListener("click", () => {
    if (document.querySelector("dialog[open]")) return;
    access.lock();
    recovery = null;
    show();
  });
  document.querySelector("#access-recover").addEventListener("click", () =>
    recover().catch((error) => {
      document.querySelector("#access-error").textContent = error.message;
    }),
  );
  if (await access.unlocked()) await enter();
  else await show();
  return {
    access,
    recover: async (candidate) => {
      recovery = candidate;
      await show();
    },
    locked: () => document.body.dataset.locked === "true",
  };
}

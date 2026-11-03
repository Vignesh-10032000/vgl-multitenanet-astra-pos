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
      form.elements.username.value = account?.username || "";
      form.elements.password.value = "";
      form.elements.confirm.value = "";
    }
    firstShow = false;
    text("#access-submit", account ? recovery ? "signInRecover" : "signIn" : "createAccount");
    document.querySelector("#access-error").textContent = "";
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
    document.querySelector("#access-error").textContent = "";
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
      document.querySelector("#access-error").textContent = error.message;
    } finally {
      button.disabled = false;
      busy = false;
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

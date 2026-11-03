import { OwnerAccess } from "./access.js";

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
  async function show() {
    document.body.dataset.locked = "true";
    screen.hidden = false;
    const account = recovery
      ? await access.recoveryAccount(recovery.data)
      : await access.account();
    document.querySelector("#access-title").textContent = recovery
      ? "Continue from your backup"
      : account
        ? "Welcome back"
        : "Set up your owner account";
    document.querySelector("#access-description").textContent = recovery
      ? `${recovery.billCount} saved bills · ${new Date(recovery.data.created_at).toLocaleString("en-IN")}. Sign in to replace this device's current ledger with this backup.`
      : account
        ? "Sign in to open your restaurant workspace."
        : "Create a username and password for this offline restaurant.";
    document.querySelector("#access-confirm-row").hidden = Boolean(account);
    form.elements.confirm.required = !account;
    form.elements.password.autocomplete = account
      ? "current-password"
      : "new-password";
    form.elements.username.value = account?.username || "";
    form.elements.password.value = "";
    form.elements.confirm.value = "";
    document.querySelector("#access-submit").textContent = account
      ? recovery
        ? "Sign in & recover"
        : "Sign in"
      : "Create account & continue";
    document.querySelector("#access-error").textContent = "";
    form.hidden = false;
  }
  async function enter() {
    document.body.dataset.locked = "false";
    screen.hidden = true;
    await unlocked();
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

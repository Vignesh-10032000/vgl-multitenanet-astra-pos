import { apiJson, clearSession, getSession } from "./session.js";
import { t } from "./i18n.js";
import { closeDialog, createCell, openDialog, setBusy, showToast } from "./ui.js";

let directory = null;
let editingId = null;

function roleLabel(value) {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function loadSecurity() {
  const user = await apiJson("/api/v1/auth/me");
  document.querySelector("#security-role").textContent = user.roles.map(roleLabel).join(" · ");
  document.querySelector("#mfa-status").textContent = t(user.mfa_enabled ? "settings.mfa_on" : "settings.mfa_off");
  document.querySelector("#mfa-setup-form").hidden = user.mfa_enabled;
  document.querySelector("#mfa-disable-form").hidden = !user.mfa_enabled;
}

async function securityAction(event, action) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('[type="submit"]');
  const error = document.querySelector("#security-error");
  error.textContent = "";
  setBusy(button, true);
  try {
    const values = Object.fromEntries(new FormData(form));
    if (values.mfa_code === "") delete values.mfa_code;
    const response = await apiJson(`/api/v1/auth/${action}`, { method: "POST", body: JSON.stringify(values) });
    form.reset();
    if (action === "mfa/setup") {
      document.querySelector("#mfa-secret").value = new URL(response.provisioning_uri).searchParams.get("secret");
      document.querySelector("#mfa-enable-form").hidden = false;
      document.querySelector('#mfa-enable-form [name="code"]').focus();
    } else if (action === "logout-all") {
      clearSession();
      location.replace("/login");
    } else {
      document.querySelector("#mfa-secret").value = "";
      document.querySelector("#mfa-enable-form").hidden = true;
      await loadSecurity();
      showToast(t("settings.saved"), { tone: "success" });
    }
  } catch (failure) { error.textContent = failure.message; }
  finally { setBusy(button, false); }
}

async function loadTeam() {
  directory = await apiJson("/api/v1/settings/team");
  const body = document.querySelector("#team-rows");
  body.replaceChildren();
  const currentId = getSession().user.id;
  directory.members.forEach((member) => {
    const row = document.createElement("tr");
    row.append(createCell(member.full_name, `${member.username} · ${member.email}`));
    row.append(createCell(member.roles.map(roleLabel).join(", ")));
    row.append(createCell(t(member.is_active ? "settings.active" : "settings.disabled")));
    row.append(createCell(t(member.mfa_enabled ? "settings.mfa_on" : "settings.mfa_off")));
    const cell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-secondary";
    button.textContent = t("common.edit");
    const canManageAdmins = directory.assignable_roles.includes("SUPER_ADMIN");
    button.disabled = member.id === currentId || (!canManageAdmins && member.roles.some((role) => ["OWNER", "SUPER_ADMIN", "ADMIN"].includes(role)));
    button.addEventListener("click", () => openMember(member));
    cell.append(button);
    row.append(cell);
    body.append(row);
  });
}

function openMember(member = null) {
  if (!directory) return;
  const form = document.querySelector("#team-form");
  form.reset();
  editingId = member?.id || null;
  document.querySelector("#team-error").textContent = "";
  const select = form.elements.role;
  select.replaceChildren();
  directory.assignable_roles.forEach((role) => {
    const option = document.createElement("option");
    option.value = role;
    option.textContent = roleLabel(role);
    select.append(option);
  });
  for (const key of ["username", "email", "full_name"]) form.elements[key].value = member?.[key] || "";
  select.value = member?.roles.find((role) => directory.assignable_roles.includes(role)) || "CASHIER";
  form.elements.is_active.value = String(member?.is_active ?? true);
  form.elements.password.required = !member;
  openDialog("#team-dialog", document.querySelector("#team-new"));
}

async function saveMember(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('[type="submit"]');
  const error = document.querySelector("#team-error");
  error.textContent = "";
  const data = Object.fromEntries(new FormData(form));
  data.is_active = data.is_active === "true";
  for (const key of ["password", "pin", "actor_mfa_code"]) if (!data[key]) data[key] = null;
  setBusy(button, true);
  try {
    await apiJson(`/api/v1/settings/team${editingId ? `/${editingId}` : ""}`, { method: editingId ? "PUT" : "POST", body: JSON.stringify(data) });
    form.reset();
    closeDialog("#team-dialog");
    await loadTeam();
    showToast(t("settings.saved"), { tone: "success" });
  } catch (failure) { error.textContent = failure.message; }
  finally { setBusy(button, false); }
}

export function initializeAccessSettings() {
  loadSecurity().catch((error) => { document.querySelector("#security-error").textContent = error.message; });
  if (getSession()?.user.permissions.includes("user.manage")) {
    loadTeam().catch((error) => { document.querySelector("#security-error").textContent = error.message; });
  }
  for (const [id, action] of [["mfa-setup-form", "mfa/setup"], ["mfa-enable-form", "mfa/enable"], ["mfa-disable-form", "mfa/disable"], ["logout-all-form", "logout-all"]]) {
    document.querySelector(`#${id}`).addEventListener("submit", (event) => securityAction(event, action));
  }
  document.querySelector("#team-new").addEventListener("click", () => openMember());
  document.querySelector("#team-form").addEventListener("submit", saveMember);
  document.querySelector("#team-dialog").addEventListener("close", () => document.querySelector("#team-form").reset());
}

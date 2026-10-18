import {
  AlertTriangle,
  ChartNoAxesCombined,
  Check,
  CircleAlert,
  CloudUpload,
  Info,
  Languages,
  LayoutDashboard,
  LogOut,
  PackageSearch,
  ReceiptText,
  ScanLine,
  Settings,
  ShieldCheck,
  SunMoon,
  Users,
  X,
  createIcons,
} from "lucide";

const iconSet = {
  AlertTriangle,
  ChartNoAxesCombined,
  Check,
  CircleAlert,
  CloudUpload,
  Info,
  Languages,
  LayoutDashboard,
  LogOut,
  PackageSearch,
  ReceiptText,
  ScanLine,
  Settings,
  ShieldCheck,
  SunMoon,
  Users,
  X,
};

let returnFocus = null;

export function registerIcons(icons) {
  Object.assign(iconSet, icons);
  refreshIcons();
}

export function refreshIcons(root = document) {
  createIcons({ icons: iconSet, attrs: { "aria-hidden": "true" }, root });
}

export function clearChildren(element) {
  while (element.firstChild) element.removeChild(element.firstChild);
}

function toastIcon(tone) {
  if (tone === "success") return "check";
  if (tone === "danger") return "circle-alert";
  if (tone === "warning") return "alert-triangle";
  return "info";
}

export function showToast(message, options = {}) {
  const { tone = "info", duration = 5000, actionLabel = null, onAction = null } = options;
  const region = document.querySelector("#toast-region");
  if (!region) return null;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.dataset.tone = tone;
  toast.setAttribute("role", tone === "danger" ? "alert" : "status");

  const icon = document.createElement("i");
  icon.dataset.lucide = toastIcon(tone);
  const copy = document.createElement("p");
  copy.textContent = message;
  toast.append(icon, copy);
  if (actionLabel && onAction) {
    const action = document.createElement("button");
    action.type = "button";
    action.className = "text-button";
    action.textContent = actionLabel;
    action.addEventListener("click", () => {
      onAction();
      toast.remove();
    });
    toast.append(action);
  }
  region.append(toast);
  refreshIcons(toast);
  const timer = window.setTimeout(() => toast.remove(), duration);
  toast.addEventListener("mouseenter", () => window.clearTimeout(timer), { once: true });
  return toast;
}

function focusableElements(dialog) {
  return [...dialog.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")].filter(
    (element) => !element.closest(".is-hidden"),
  );
}

export function openDialog(dialog, trigger = document.activeElement) {
  const target = typeof dialog === "string" ? document.querySelector(dialog) : dialog;
  if (!target) return;
  returnFocus = trigger instanceof HTMLElement ? trigger : null;
  target.showModal();
  const focusable = focusableElements(target);
  focusable[0]?.focus();
}

export function closeDialog(dialog) {
  const target = typeof dialog === "string" ? document.querySelector(dialog) : dialog;
  if (!target?.open) return;
  target.close();
  returnFocus?.focus();
  returnFocus = null;
}

function trapFocus(event) {
  const dialog = event.currentTarget;
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    closeDialog(dialog);
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = focusableElements(dialog);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function initializeDialogs() {
  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.addEventListener("keydown", trapFocus);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog(dialog);
    });
  });
  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-dialog-close]");
    if (close) closeDialog(close.closest("dialog"));
    const open = event.target.closest("[data-dialog-open]");
    if (open) openDialog(open.dataset.dialogOpen, open);
  });
}

export function createCell(primary, secondary = null) {
  const cell = document.createElement("td");
  const main = document.createElement("span");
  main.className = "cell-primary";
  main.textContent = primary;
  cell.append(main);
  if (secondary) {
    const detail = document.createElement("span");
    detail.className = "cell-secondary";
    detail.textContent = secondary;
    cell.append(detail);
  }
  return cell;
}

export function createBadge(label, tone = "") {
  const badge = document.createElement("span");
  badge.className = `badge${tone ? ` badge-${tone}` : ""}`;
  badge.textContent = label;
  return badge;
}

export function debounce(callback, delay) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => callback(...args), delay);
  };
}

export function setBusy(element, busy) {
  element.setAttribute("aria-busy", String(Boolean(busy)));
  element.querySelectorAll("button, input, select").forEach((control) => {
    if (busy) control.setAttribute("disabled", "");
    else control.removeAttribute("disabled");
  });
}

export async function confirmRisk({ title, message, confirmLabel, tone = "danger", trigger }) {
  let dialog = document.querySelector("#risk-confirm-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "risk-confirm-dialog";
    dialog.className = "dialog dialog-small";
    const header = document.createElement("div");
    header.className = "dialog-header";
    const heading = document.createElement("h2");
    heading.id = "risk-confirm-title";
    header.append(heading);
    const body = document.createElement("div");
    body.className = "dialog-body";
    const copy = document.createElement("p");
    copy.id = "risk-confirm-message";
    body.append(copy);
    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button button-secondary";
    cancel.dataset.confirmCancel = "";
    cancel.textContent = "Cancel";
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.dataset.confirmAccept = "";
    actions.append(cancel, confirm);
    dialog.append(header, body, actions);
    document.body.append(dialog);
    dialog.addEventListener("keydown", trapFocus);
  }
  dialog.querySelector("#risk-confirm-title").textContent = title;
  dialog.querySelector("#risk-confirm-message").textContent = message;
  const accept = dialog.querySelector("[data-confirm-accept]");
  accept.className = `button button-${tone}`;
  accept.textContent = confirmLabel;
  openDialog(dialog, trigger);
  return new Promise((resolve) => {
    const finish = (result) => {
      closeDialog(dialog);
      resolve(result);
    };
    dialog.querySelector("[data-confirm-cancel]").addEventListener("click", () => finish(false), { once: true });
    accept.addEventListener("click", () => finish(true), { once: true });
    dialog.addEventListener("cancel", () => finish(false), { once: true });
  });
}

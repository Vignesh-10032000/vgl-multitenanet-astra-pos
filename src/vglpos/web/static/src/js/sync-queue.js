import { CloudCheck, RefreshCw, RotateCw } from "lucide";

import { whenAppReady } from "./app.js";
import { formatDate, formatMoney, t } from "./i18n.js";
import { getOutboxEntries, retryOutboxEntry } from "./offline.js";
import { clearChildren, registerIcons, setBusy, showToast } from "./ui.js";

registerIcons({ CloudCheck, RefreshCw, RotateCw });

function statusText(entry) {
  if (entry.status === "failed") return t("queue.failed");
  if (entry.status === "retry") return t("queue.retrying");
  return t("queue.pending");
}

function queueCard(entry) {
  const article = document.createElement("article");
  article.className = "queue-card";
  article.dataset.status = entry.status;

  const heading = document.createElement("div");
  const invoice = document.createElement("a");
  invoice.href = `/receipt/offline/${entry.uuid}`;
  invoice.textContent = entry.provisional_number;
  const date = document.createElement("small");
  date.textContent = formatDate(entry.created_at, { dateStyle: "medium", timeStyle: "short" });
  heading.append(invoice, date);

  const status = document.createElement("strong");
  status.className = "queue-status";
  status.textContent = statusText(entry);

  const facts = document.createElement("dl");
  const total = document.createElement("div");
  total.innerHTML = `<dt>${t("queue.total")}</dt>`;
  const totalValue = document.createElement("dd");
  totalValue.textContent = formatMoney(entry.quote.net_amount);
  total.append(totalValue);
  const attempts = document.createElement("div");
  attempts.innerHTML = `<dt>${t("queue.attempts")}</dt>`;
  const attemptsValue = document.createElement("dd");
  attemptsValue.textContent = String(entry.attempts);
  attempts.append(attemptsValue);
  facts.append(total, attempts);

  const error = document.createElement("p");
  error.className = "queue-error";
  error.textContent = entry.detail || "";
  error.hidden = !entry.detail;

  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "button button-secondary";
  retry.dataset.retryUuid = entry.uuid;
  const icon = document.createElement("i");
  icon.dataset.lucide = "rotate-cw";
  const label = document.createElement("span");
  label.textContent = t("queue.retry");
  retry.append(icon, label);
  article.append(heading, status, facts, error, retry);
  return article;
}

async function renderQueue() {
  const list = document.querySelector("#queue-list");
  const empty = document.querySelector("#queue-empty");
  list.setAttribute("aria-busy", "true");
  const entries = await getOutboxEntries();
  clearChildren(list);
  entries.forEach((entry) => list.append(queueCard(entry)));
  list.classList.toggle("is-hidden", entries.length === 0);
  empty.classList.toggle("is-hidden", entries.length !== 0);
  list.setAttribute("aria-busy", "false");
  registerIcons({ CloudCheck, RefreshCw, RotateCw });
}

whenAppReady(() => {
  renderQueue().catch((error) => showToast(error.message, { tone: "danger" }));
  document.querySelector("#refresh-queue").addEventListener("click", renderQueue);
  document.querySelector("#queue-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-retry-uuid]");
    if (!button) return;
    setBusy(button, true);
    try {
      await retryOutboxEntry(button.dataset.retryUuid);
      await renderQueue();
    } catch (error) {
      showToast(error.message, { tone: "danger" });
    } finally {
      setBusy(button, false);
    }
  });
  document.addEventListener("vgl:sync-status", renderQueue);
});

document.addEventListener("vgl:locale-changed", renderQueue);

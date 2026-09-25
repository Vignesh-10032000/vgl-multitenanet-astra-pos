import { Clock3, ListChecks, RefreshCw, RotateCcw, ShieldCheck, TriangleAlert } from "lucide";

import { whenAppReady } from "./app.js";
import { apiJson } from "./session.js";
import { clearChildren, closeDialog, createCell, openDialog, registerIcons, setBusy, showToast } from "./ui.js";

registerIcons({ Clock3, ListChecks, RefreshCw, RotateCcw, ShieldCheck, TriangleAlert });

let cancellationRecordId = null;

function actionButton(record) {
  const container = document.createElement("div");
  if (["DEAD", "RETRY", "CANCEL_RETRY"].includes(record.status)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-secondary button-small";
    button.dataset.retryId = record.id;
    button.textContent = "Retry";
    container.append(button);
  }
  if (record.status === "GENERATED") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-danger button-small";
    button.dataset.cancelId = record.id;
    button.textContent = "Cancel IRN";
    container.append(button);
  }
  return container;
}

function renderInvoices(records) {
  const body = document.querySelector("#einvoice-rows");
  clearChildren(body);
  records.forEach((record) => {
    const row = document.createElement("tr");
    row.append(createCell(`#${record.sale_id}`));
    row.append(createCell(record.status));
    row.append(createCell(record.irn || record.error_text || "—", record.error_code || ""));
    row.append(createCell(`${record.attempt_count}/${record.max_attempts}`));
    row.append(createCell(new Date(record.created_at).toLocaleString()));
    const action = document.createElement("td");
    action.append(actionButton(record));
    row.append(action);
    body.append(row);
  });
  if (!records.length) {
    const row = document.createElement("tr");
    const cell = createCell("No e-invoice records.");
    cell.colSpan = 6;
    row.append(cell);
    body.append(row);
  }
}

function renderReconciliation(items) {
  const body = document.querySelector("#reconciliation-rows");
  clearChildren(body);
  items.forEach((issue) => {
    const row = document.createElement("tr");
    row.append(createCell(issue.invoice_number, `Sale #${issue.sale_id}`));
    row.append(createCell(issue.business_date));
    row.append(createCell(issue.issue));
    row.append(createCell(issue.status || "—"));
    row.append(createCell(issue.error_text || "—"));
    body.append(row);
  });
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = createCell("No reconciliation gaps.");
    cell.colSpan = 5;
    row.append(cell);
    body.append(row);
  }
}

async function loadCompliance() {
  const status = document.querySelector("#einvoice-status").value;
  try {
    const [records, alerts, reconciliation] = await Promise.all([
      apiJson(`/api/v1/compliance/e-invoices${status ? `?status=${encodeURIComponent(status)}` : ""}`),
      apiJson("/api/v1/compliance/alerts"),
      apiJson("/api/v1/compliance/reconciliation"),
    ]);
    renderInvoices(records.items);
    renderReconciliation(reconciliation.items);
    document.querySelector("#compliance-pending").textContent = alerts.pending_count;
    document.querySelector("#compliance-dead").textContent = alerts.dead_letter_count;
    document.querySelector("#compliance-gaps").textContent = reconciliation.items.length;
  } catch (error) {
    showToast(`Compliance: ${error.message}`, { tone: "danger" });
  }
}

async function handleAction(event) {
  const retryId = event.target.closest("[data-retry-id]")?.dataset.retryId;
  const cancelId = event.target.closest("[data-cancel-id]")?.dataset.cancelId;
  try {
    if (retryId) {
      await apiJson(`/api/v1/compliance/e-invoices/${retryId}/retry`, { method: "POST", body: "{}" });
    } else if (cancelId) {
      cancellationRecordId = cancelId;
      const form = document.querySelector("#irn-cancel-form");
      form.reset();
      document.querySelector("#irn-cancel-error").textContent = "";
      openDialog("#irn-cancel-dialog", event.target.closest("[data-cancel-id]"));
      return;
    } else {
      return;
    }
    await loadCompliance();
  } catch (error) {
    showToast(error.message, { tone: "danger" });
  }
}

async function cancelIrn(event) {
  event.preventDefault();
  if (!cancellationRecordId) return;
  const form = event.currentTarget;
  const error = document.querySelector("#irn-cancel-error");
  error.textContent = "";
  setBusy(form, true);
  try {
    await apiJson(`/api/v1/compliance/e-invoices/${cancellationRecordId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: form.elements.reason.value.trim() }),
    });
    cancellationRecordId = null;
    closeDialog("#irn-cancel-dialog");
    await loadCompliance();
  } catch (failure) {
    error.textContent = failure.message;
  } finally {
    setBusy(form, false);
  }
}

whenAppReady(() => {
  loadCompliance();
  document.querySelector("#compliance-refresh").addEventListener("click", loadCompliance);
  document.querySelector("#einvoice-status").addEventListener("change", loadCompliance);
  document.querySelector("#einvoice-rows").addEventListener("click", handleAction);
  document.querySelector("#irn-cancel-form").addEventListener("submit", cancelIrn);
});

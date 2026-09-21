import { apiJson, getSession } from "./session.js";
import {
  adjustCachedStock,
  applyCatalogDelta,
  clearReferenceData,
  deleteOutbox,
  enqueueOutbox,
  getMeta,
  listCachedCustomers,
  listCachedProducts,
  listOutbox,
  outboxSummary,
  putOutbox,
  replaceCachedCustomers,
  setMeta,
} from "./offline-db.js";

const POLL_INTERVAL_MS = 30_000;
const BATCH_SIZE = 100;
const CONTEXT_KEY = "active-context";
const FACTS_KEY = "offline-facts";
const SIGNING_KEY = "terminal-signing-key";
const CATALOG_SYNC_KEY = "catalog-synced-at";
const SEQUENCE_KEY = "provisional-sequence";
let drainPromise = null;
let pollTimer = null;

function contextFrom(session) {
  const user = session?.user;
  if (!user?.company_id || !user?.branch_id || !user?.terminal_id) {
    throw new Error("Select a branch and terminal before enabling offline billing.");
  }
  return `${user.company_id}:${user.branch_id}:${user.terminal_id}`;
}

function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function decodeBase64Url(value) {
  const padded = `${value}${"=".repeat((4 - (value.length % 4)) % 4)}`;
  const binary = atob(padded.replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(binary, (character) => character.codePointAt(0));
}

function encodeBase64Url(value) {
  let binary = "";
  new Uint8Array(value).forEach((byte) => { binary += String.fromCodePoint(byte); });
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function importSigningKey(encoded) {
  return crypto.subtle.importKey(
    "raw",
    decodeBase64Url(encoded),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function signatureFor(uuid, payload) {
  const key = await getMeta(SIGNING_KEY);
  if (!key) throw new Error("This terminal must reconnect once before offline billing.");
  const message = new TextEncoder().encode(`${uuid}.${canonicalJson(payload)}`);
  return encodeBase64Url(await crypto.subtle.sign("HMAC", key, message));
}

async function prepareContext(session) {
  const context = contextFrom(session);
  const active = await getMeta(CONTEXT_KEY);
  if (active && active !== context) {
    const summary = await outboxSummary();
    if (summary.total) {
      throw new Error("Sync this terminal's queued bills before changing counter context.");
    }
    await clearReferenceData();
    await setMeta(CATALOG_SYNC_KEY, null);
  }
  await setMeta(CONTEXT_KEY, context);
}

async function provisionTerminal() {
  const facts = await apiJson("/api/v1/sync/bootstrap");
  const key = await importSigningKey(facts.signing_key);
  await setMeta(SIGNING_KEY, key);
  await setMeta(FACTS_KEY, {
    terminal_code: facts.terminal_code,
    supplier_state: facts.supplier_state,
    outbox_limit: facts.outbox_limit,
  });
  return facts;
}

export async function syncReferenceData() {
  if (!navigator.onLine) return;
  let since = await getMeta(CATALOG_SYNC_KEY);
  let delta;
  do {
    const parameters = new URLSearchParams({ limit: "50000" });
    if (since) parameters.set("since", since);
    delta = await apiJson(`/api/v1/products/catalog?${parameters}`);
    await applyCatalogDelta(delta.items);
    since = delta.synced_at;
    await setMeta(CATALOG_SYNC_KEY, since);
  } while (delta.truncated);

  const [customers, profile] = await Promise.all([
    apiJson("/api/v1/customers?limit=200"),
    apiJson("/api/v1/settings/store-profile"),
  ]);
  await replaceCachedCustomers(customers.items);
  await setMeta("store-profile", profile);
  document.dispatchEvent(new CustomEvent("vgl:reference-synced"));
}

export async function getOfflineFacts() {
  return getMeta(FACTS_KEY);
}

export async function cachedReferenceData() {
  const [products, customers] = await Promise.all([
    listCachedProducts(),
    listCachedCustomers(),
  ]);
  return { products, customers };
}

export async function nextProvisionalNumber() {
  const facts = await getOfflineFacts();
  if (!facts?.terminal_code) {
    throw new Error("This terminal must connect once before creating offline bills.");
  }
  const sequence = (await getMeta(SEQUENCE_KEY) || 0) + 1;
  await setMeta(SEQUENCE_KEY, sequence);
  return `${facts.terminal_code}-OFF-${String(sequence).padStart(6, "0")}`;
}

export async function queueOfflineSale({ payload, quote, provisionalNumber, cart }) {
  const uuid = payload.offline_uuid;
  const entry = {
    uuid,
    payload,
    signature: await signatureFor(uuid, payload),
    quote,
    cart,
    provisional_number: provisionalNumber,
    created_at: new Date().toISOString(),
    next_attempt_at: new Date().toISOString(),
    attempts: 0,
    status: "pending",
    error_type: null,
    detail: null,
  };
  const created = await enqueueOutbox(entry);
  if (created) await adjustCachedStock(payload.lines);
  await setMeta(`receipt.${uuid}`, entry);
  await requestBackgroundSync();
  await publishStatus();
  return entry;
}

function retryDelay(attempts) {
  return Math.min(300_000, 1000 * (2 ** Math.min(attempts, 8)));
}

async function processResult(entry, result) {
  if (result.status === "synced") {
    await setMeta(`receipt.${entry.uuid}`, {
      ...entry,
      status: "synced",
      sale: result.sale,
      synced_at: new Date().toISOString(),
    });
    await deleteOutbox(entry.uuid);
    document.dispatchEvent(new CustomEvent("vgl:sale-synced", { detail: result.sale }));
    return;
  }
  const attempts = entry.attempts + 1;
  await putOutbox({
    ...entry,
    attempts,
    status: result.status,
    error_type: result.error_type,
    detail: result.detail,
    next_attempt_at: new Date(Date.now() + retryDelay(attempts)).toISOString(),
  });
}

async function performDrain() {
  if (!navigator.onLine || !getSession()) return;
  const now = new Date().toISOString();
  const entries = (await listOutbox()).filter((entry) => (
    entry.status !== "failed" && entry.next_attempt_at <= now
  ));
  if (!entries.length) {
    await publishStatus();
    return;
  }
  for (let offset = 0; offset < entries.length; offset += BATCH_SIZE) {
    const batch = entries.slice(offset, offset + BATCH_SIZE);
    await publishStatus({ syncing: offset + 1, syncTotal: entries.length });
    try {
      const response = await apiJson("/api/v1/sync/batch", {
        method: "POST",
        body: JSON.stringify({
          operations: batch.map((entry) => ({
            uuid: entry.uuid,
            sale: entry.payload,
            signature: entry.signature,
          })),
        }),
      });
      const byUuid = new Map(response.results.map((result) => [result.uuid, result]));
      for (const entry of batch) {
        const result = byUuid.get(entry.uuid);
        if (!result) {
          await processResult(entry, {
            status: "retry",
            error_type: "missing-sync-result",
            detail: "The server omitted this operation from its response.",
          });
        } else {
          await processResult(entry, result);
        }
      }
    } catch (error) {
      for (const entry of batch) {
        await processResult(entry, {
          status: "retry",
          error_type: "sync-unavailable",
          detail: error.message,
        });
      }
      break;
    }
  }
  await publishStatus();
}

export async function drainOutbox() {
  drainPromise ||= performDrain().finally(() => { drainPromise = null; });
  return drainPromise;
}

export async function retryOutboxEntry(uuid) {
  const entry = (await listOutbox()).find((candidate) => candidate.uuid === uuid);
  if (!entry) return;
  await putOutbox({ ...entry, status: "retry", next_attempt_at: new Date().toISOString() });
  await drainOutbox();
}

export async function getOutboxEntries() {
  return listOutbox();
}

export async function getOfflineReceipt(uuid) {
  return getMeta(`receipt.${uuid}`);
}

export async function getCachedStoreProfile() {
  return getMeta("store-profile");
}

export async function publishStatus(extra = {}) {
  const summary = await outboxSummary();
  document.dispatchEvent(new CustomEvent("vgl:sync-status", {
    detail: { online: navigator.onLine, ...summary, ...extra },
  }));
  return summary;
}

async function requestBackgroundSync() {
  try {
    const registration = await navigator.serviceWorker?.getRegistration();
    if (registration && "sync" in registration) {
      await registration.sync.register("vglpos-outbox");
    }
  } catch {
    // Browsers may expose but administratively disable Background Sync. The
    // online event and 30-second foreground poll remain the required fallback.
  }
}

function showUpdatePrompt(registration) {
  const prompt = document.querySelector("#app-update-prompt");
  if (!prompt || !registration.waiting) return;
  prompt.hidden = false;
  prompt.querySelector("button")?.addEventListener("click", () => {
    registration.waiting?.postMessage({ type: "SKIP_WAITING" });
  }, { once: true });
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  const hadController = Boolean(navigator.serviceWorker.controller);
  const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  if (registration.waiting) showUpdatePrompt(registration);
  registration.addEventListener("updatefound", () => {
    const worker = registration.installing;
    worker?.addEventListener("statechange", () => {
      if (worker.state === "installed" && navigator.serviceWorker.controller) {
        showUpdatePrompt(registration);
      }
    });
  });
  let refreshing = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (refreshing || !hadController) return;
    refreshing = true;
    location.reload();
  });
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type === "DRAIN_OUTBOX") drainOutbox();
  });
}

export async function initializeOffline(session) {
  await prepareContext(session);
  try {
    await registerServiceWorker();
  } catch (error) {
    document.dispatchEvent(new CustomEvent("vgl:offline-error", { detail: error }));
  }
  await publishStatus();
  if (navigator.onLine) {
    try {
      await provisionTerminal();
      await syncReferenceData();
      await drainOutbox();
    } catch (error) {
      document.dispatchEvent(new CustomEvent("vgl:offline-error", { detail: error }));
    }
  }
  addEventListener("online", async () => {
    await publishStatus();
    try {
      await provisionTerminal();
      await syncReferenceData();
      await drainOutbox();
    } catch (error) {
      document.dispatchEvent(new CustomEvent("vgl:offline-error", { detail: error }));
    }
  });
  addEventListener("offline", publishStatus);
  pollTimer ||= window.setInterval(() => {
    if (navigator.onLine) drainOutbox();
  }, POLL_INTERVAL_MS);
}

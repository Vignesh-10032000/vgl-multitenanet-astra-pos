const DB_NAME = "vglpos-offline";
const DB_VERSION = 1;
export const OUTBOX_LIMIT = 500;

const STORES = Object.freeze({
  products: "products",
  customers: "customers",
  cart: "cart",
  outbox: "outbox",
  meta: "meta",
});

let databasePromise;

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.addEventListener("success", () => resolve(request.result), { once: true });
    request.addEventListener("error", () => reject(request.error), { once: true });
  });
}

function transactionComplete(transaction) {
  return new Promise((resolve, reject) => {
    transaction.addEventListener("complete", resolve, { once: true });
    transaction.addEventListener("abort", () => reject(transaction.error), { once: true });
    transaction.addEventListener("error", () => reject(transaction.error), { once: true });
  });
}

function openDatabase() {
  databasePromise ||= new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.addEventListener("upgradeneeded", () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORES.products)) {
        database.createObjectStore(STORES.products, { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains(STORES.customers)) {
        database.createObjectStore(STORES.customers, { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains(STORES.cart)) {
        database.createObjectStore(STORES.cart);
      }
      if (!database.objectStoreNames.contains(STORES.outbox)) {
        const outbox = database.createObjectStore(STORES.outbox, { keyPath: "uuid" });
        outbox.createIndex("status", "status");
        outbox.createIndex("created_at", "created_at");
      }
      if (!database.objectStoreNames.contains(STORES.meta)) {
        database.createObjectStore(STORES.meta);
      }
    });
    request.addEventListener("success", () => resolve(request.result), { once: true });
    request.addEventListener("error", () => reject(request.error), { once: true });
    request.addEventListener("blocked", () => reject(new Error("Offline database upgrade blocked.")), {
      once: true,
    });
  });
  return databasePromise;
}

async function getValue(storeName, key) {
  const database = await openDatabase();
  const transaction = database.transaction(storeName, "readonly");
  return requestResult(transaction.objectStore(storeName).get(key));
}

async function putValue(storeName, value, key) {
  const database = await openDatabase();
  const transaction = database.transaction(storeName, "readwrite");
  const store = transaction.objectStore(storeName);
  if (key === undefined) store.put(value);
  else store.put(value, key);
  await transactionComplete(transaction);
}

async function deleteValue(storeName, key) {
  const database = await openDatabase();
  const transaction = database.transaction(storeName, "readwrite");
  transaction.objectStore(storeName).delete(key);
  await transactionComplete(transaction);
}

async function getAll(storeName) {
  const database = await openDatabase();
  const transaction = database.transaction(storeName, "readonly");
  return requestResult(transaction.objectStore(storeName).getAll());
}

export function assertOutboxCapacity(count) {
  if (!Number.isSafeInteger(count) || count < 0) throw new Error("Invalid outbox count.");
  if (count >= OUTBOX_LIMIT) {
    const error = new Error("Offline bill limit reached. Reconnect before creating another bill.");
    error.name = "OutboxFullError";
    throw error;
  }
}

export async function applyCatalogDelta(items) {
  const database = await openDatabase();
  const transaction = database.transaction(STORES.products, "readwrite");
  const store = transaction.objectStore(STORES.products);
  items.forEach((product) => {
    if (product.deleted_at || !product.is_active) store.delete(product.id);
    else store.put(product);
  });
  await transactionComplete(transaction);
}

export async function listCachedProducts() {
  const products = await getAll(STORES.products);
  return products.sort((left, right) => left.id - right.id);
}

export async function findCachedProductByBarcode(barcode) {
  const products = await listCachedProducts();
  return products.find((product) => product.barcode === barcode) || null;
}

export async function replaceCachedCustomers(customers) {
  const database = await openDatabase();
  const transaction = database.transaction(STORES.customers, "readwrite");
  const store = transaction.objectStore(STORES.customers);
  store.clear();
  customers.forEach((customer) => store.put(customer));
  await transactionComplete(transaction);
}

export async function clearReferenceData() {
  const database = await openDatabase();
  const transaction = database.transaction([STORES.products, STORES.customers], "readwrite");
  transaction.objectStore(STORES.products).clear();
  transaction.objectStore(STORES.customers).clear();
  await transactionComplete(transaction);
}

export async function adjustCachedStock(lines) {
  const database = await openDatabase();
  const transaction = database.transaction(STORES.products, "readwrite");
  const store = transaction.objectStore(STORES.products);
  for (const line of lines) {
    const product = await requestResult(store.get(line.product_id));
    if (!product?.is_inventory_tracked) continue;
    const current = decimalToMilli(product.on_hand);
    const sold = decimalToMilli(line.quantity);
    product.on_hand = milliToDecimal(current - sold);
    product.stock_unverified = true;
    store.put(product);
  }
  await transactionComplete(transaction);
}

export async function listCachedCustomers() {
  const customers = await getAll(STORES.customers);
  return customers.sort((left, right) => left.name.localeCompare(right.name));
}

export async function saveCart(key, value) {
  await putValue(STORES.cart, value, key);
}

export async function loadCart(key) {
  return getValue(STORES.cart, key);
}

export async function deleteCart(key) {
  await deleteValue(STORES.cart, key);
}

export async function enqueueOutbox(entry) {
  const database = await openDatabase();
  const transaction = database.transaction(STORES.outbox, "readwrite");
  const store = transaction.objectStore(STORES.outbox);
  const existing = await requestResult(store.get(entry.uuid));
  const created = !existing;
  if (!existing) {
    const count = await requestResult(store.count());
    assertOutboxCapacity(count);
  }
  store.put(entry);
  await transactionComplete(transaction);
  return created;
}

export async function listOutbox() {
  const entries = await getAll(STORES.outbox);
  return entries.sort((left, right) => left.created_at.localeCompare(right.created_at));
}

export async function putOutbox(entry) {
  await putValue(STORES.outbox, entry);
}

export async function deleteOutbox(uuid) {
  await deleteValue(STORES.outbox, uuid);
}

export async function outboxSummary() {
  const entries = await listOutbox();
  return {
    total: entries.length,
    pending: entries.filter((entry) => entry.status === "pending" || entry.status === "retry").length,
    failed: entries.filter((entry) => entry.status === "failed").length,
    syncing: entries.filter((entry) => entry.status === "syncing").length,
  };
}

export async function getMeta(key) {
  return getValue(STORES.meta, key);
}

export async function setMeta(key, value) {
  await putValue(STORES.meta, value, key);
}

export async function deleteMeta(key) {
  await deleteValue(STORES.meta, key);
}

function decimalToMilli(value) {
  const match = String(value ?? "0").trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) throw new Error("Cached quantity is invalid.");
  const fraction = (match[3] || "").padEnd(3, "0").slice(0, 3);
  const absolute = BigInt(match[2]) * 1000n + BigInt(fraction || "0");
  return match[1] === "-" ? -absolute : absolute;
}

function milliToDecimal(value) {
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  return `${negative ? "-" : ""}${absolute / 1000n}.${String(absolute % 1000n).padStart(3, "0")}`;
}

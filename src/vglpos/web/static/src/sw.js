const CACHE_VERSION = "vglpos-phase6-v1";
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const DATA_CACHE = `${CACHE_VERSION}-data`;
const ALLOWED_CACHES = new Set([SHELL_CACHE, DATA_CACHE]);

async function shellAssets() {
  const response = await fetch("/pwa-assets.json", { cache: "no-store" });
  if (!response.ok) throw new Error("App shell manifest could not be loaded.");
  const payload = await response.json();
  return payload.assets;
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await cache.addAll(await shellAssets());
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => !ALLOWED_CACHES.has(name)).map((name) => (
      caches.delete(name)
    )));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});

async function privateCacheKey(request) {
  const authorization = request.headers.get("Authorization") || "anonymous";
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(authorization));
  const token = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  const url = new URL(request.url);
  url.searchParams.set("__session", token);
  return new Request(url, { method: "GET" });
}

async function networkFirstData(request) {
  const cache = await caches.open(DATA_CACHE);
  const cacheKey = await privateCacheKey(request);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(cacheKey, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(cacheKey);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirstShell(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request, { ignoreSearch: request.mode === "navigate" });
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const url = new URL(request.url);
    if (request.mode === "navigate" && url.pathname.startsWith("/receipt/offline/")) {
      const receipt = await cache.match("/receipt/offline/00000000-0000-0000-0000-000000000000");
      if (receipt) return receipt;
    }
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/v1/")) {
    event.respondWith(networkFirstData(request));
    return;
  }
  event.respondWith(cacheFirstShell(request));
});

self.addEventListener("sync", (event) => {
  if (event.tag !== "vglpos-outbox") return;
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    clients.forEach((client) => client.postMessage({ type: "DRAIN_OUTBOX" }));
  })());
});

import test from "node:test";
import assert from "node:assert/strict";
import { apiFetch, saveSession, getSession, clearSession } from "../../src/vglpos/web/static/src/js/session.js";

test("SEC-08 concurrent expired requests share a single refresh token rotation", async () => {
  const originalFetch = globalThis.fetch;
  const originalStorage = globalThis.sessionStorage;
  const values = new Map();
  globalThis.sessionStorage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
  saveSession({ access_token: "old-access", refresh_token: "old-refresh" });
  let refreshCount = 0;
  globalThis.fetch = async (url, options) => {
    if (url === "/api/v1/auth/refresh") {
      refreshCount++;
      await new Promise((resolve) => setTimeout(resolve, 15));
      return Response.json({ access_token: "new-access", refresh_token: "new-refresh" });
    }
    return options.headers.get("Authorization") === "Bearer new-access" ? Response.json({ ok: true }) : new Response("", { status: 401 });
  };
  try {
    const results = await Promise.all([apiFetch("/one"), apiFetch("/two"), apiFetch("/three")]);
    assert.equal(refreshCount, 1);
    assert.ok(results.every((response) => response.ok));
    assert.equal(getSession().access_token, "new-access");
  } finally { globalThis.fetch = originalFetch; globalThis.sessionStorage = originalStorage; }
});

test("SEC-10 a refresh finishing after sign-out cannot restore the session", async () => {
  const originalFetch = globalThis.fetch;
  const originalStorage = globalThis.sessionStorage;
  const originalDocument = globalThis.document;
  const values = new Map();
  globalThis.sessionStorage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
  globalThis.document = new EventTarget();
  saveSession({ access_token: "old-access", refresh_token: "old-refresh" });
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  let started;
  const refreshStarted = new Promise((resolve) => { started = resolve; });
  globalThis.fetch = async (url) => {
    if (url === "/api/v1/auth/refresh") {
      started();
      await pending;
      return Response.json({ access_token: "new-access", refresh_token: "new-refresh" });
    }
    return new Response("", { status: 401 });
  };
  try {
    const call = apiFetch("/one");
    await refreshStarted;
    clearSession();
    release();
    await assert.rejects(call, (error) => error.status === 401);
    assert.equal(getSession(), null);
  } finally { globalThis.fetch = originalFetch; globalThis.sessionStorage = originalStorage; globalThis.document = originalDocument; }
});

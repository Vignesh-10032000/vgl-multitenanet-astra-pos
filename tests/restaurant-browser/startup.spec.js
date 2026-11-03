import { test, expect } from "@playwright/test";
import { unlockFixture } from "./access-helper.js";

test("STARTUP-UI-01 form paints before DB, early submission waits and optional photos never disable login", async ({ page }) => {
  let release;
  const stalled = new Promise(resolve => { release = resolve; });
  await page.route(/sql-wasm.*\.wasm$/, async route => { await stalled; await route.continue(); });
  await page.goto("/?startupProfile=1");
  await expect(page.locator("#access-form")).toBeVisible();
  await expect(page.locator("#access-submit")).toBeDisabled();
  await page.locator("#access-username").fill("test-owner");
  await page.locator("#access-password").fill("Fixture-only-owner-482!");
  await page.locator("#access-password-toggle").click();
  await expect(page.locator("#access-password")).toHaveAttribute("type", "text");
  await page.locator("#access-form").evaluate(form => form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  release();
  await expect(page.locator("#access-confirm-row")).toBeVisible();
  await expect(page.locator("#access-submit")).toBeEnabled();
  await expect(page.locator("#access-password")).toHaveValue("Fixture-only-owner-482!");
  await expect(page.locator("#access-password")).toHaveAttribute("type", "text");
  await page.waitForFunction(() => performance.getEntriesByName("restaurant:ready").length);
  const marks = await page.evaluate(() => Object.fromEntries(performance.getEntriesByType("mark").map(mark => [mark.name, mark.startTime])));
  expect(marks["restaurant:login-first-paint"]).toBeLessThan(marks["restaurant:1-core:start"]);
  expect(marks["restaurant:login-interactive"]).toBeLessThan(marks["restaurant:4-photos:start"]);
  expect(marks["restaurant:login-interactive"]).toBeLessThan(marks["restaurant:6-backups:start"]);
  await unlockFixture(page);
  await expect(page.locator(".product-tile img")).toHaveCount(36);
});

test("STARTUP-UI-02 DB failure offers retry without clearing saved data", async ({ page }) => {
  await page.route(/sql-wasm.*\.wasm$/, route => route.abort());
  await page.goto("/");
  await expect(page.locator("#access-retry")).toBeVisible();
  await expect(page.locator("#access-title")).toHaveText("Could not open local data");
  await expect(page.locator("#access-submit")).toBeDisabled();
  await page.unroute(/sql-wasm.*\.wasm$/);
  await page.locator("#access-retry").click();
  await expect(page.locator("#access-submit")).toBeEnabled();
  await unlockFixture(page);
});

test("STARTUP-UI-03 first-run image work is nonblocking and cached owner branding wins on restart", async ({ page }) => {
  let release;
  const stalled = new Promise(resolve => { release = resolve; });
  await page.route("**/menu-photos/v1/*.jpg", async route => { await stalled; await route.continue(); });
  await page.goto("/?startupProfile=1");
  await expect(page.locator("#access-submit")).toBeEnabled();
  await expect(page.locator("#access-startup-status")).toContainText("background");
  await unlockFixture(page);
  await page.locator('[data-nav="settings"]').click();
  await page.locator('#settings-form [name="name"]').fill("Fixture counter");
  await page.locator('#settings-form [name="remove_logo"]').check();
  await page.locator('#settings-form .button-primary').click();
  await expect(page.locator("#store-name")).toHaveText("Fixture counter");
  release();
  await page.waitForFunction(() => performance.getEntriesByName("restaurant:ready").length);
  await page.locator("#lock-workspace").click();
  await page.reload();
  await expect(page.locator("#access-brand-name")).toHaveText("Fixture counter");
  await expect(page.locator("#access-brand-logo img")).toHaveCount(0);
  expect(await page.title()).toBe("Fixture counter");
});

test("STARTUP-UI-04 a slow complete first-run folder backup never holds sign-in", async ({ page }) => {
  let releaseDatabase;
  const databaseGate = new Promise(resolve => { releaseDatabase = resolve; });
  await page.route(/sql-wasm.*\.wasm$/, async route => { await databaseGate; await route.continue(); });
  await page.goto("/");
  await page.evaluate(async () => {
    // Disposable origin-private directory emulates the selected folder provider.
    // It does not exercise Android SAF permissions or uninstall survival.
    const folder = await (await navigator.storage.getDirectory()).getDirectoryHandle("backup-fixture", { create: true });
    await new Promise((resolve,reject) => {
      const request = indexedDB.open("keyval-store",1);
      request.onupgradeneeded = () => request.result.createObjectStore("keyval");
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db=request.result, tx=db.transaction("keyval","readwrite");
        tx.objectStore("keyval").put(folder,"restaurant-shared-backup-folder");
        tx.oncomplete=() => { db.close(); resolve(); }; tx.onerror=() => reject(tx.error);
      };
    });
    const writable = FileSystemFileHandle.prototype.createWritable;
    const gate = new Promise(resolve => { window.releaseBackupWrite = resolve; });
    FileSystemFileHandle.prototype.createWritable = async function (...args) { await gate; return writable.apply(this,args); };
  });
  releaseDatabase();
  await unlockFixture(page);
  await expect(page.locator("#access-screen")).toBeHidden();
  await expect(page.locator("#persistent-backup-status")).toContainText("Saving a complete backup");
  await page.evaluate(() => window.releaseBackupWrite());
  await expect(page.locator("#persistent-backup-status")).toContainText("Backup saved");
  let payload;
  await expect.poll(async () => {
    payload = await page.evaluate(async () => {
    const folder = await (await navigator.storage.getDirectory()).getDirectoryHandle("backup-fixture");
    for await (const handle of folder.values()) {
      const source = await (await handle.getFile()).text();
      try {
        const data = JSON.parse(JSON.parse(source).payload);
        // A pre-setup photo snapshot is retained; account creation appends another.
        if (data.tables.drafts.some(row => row.id === "local:owner-access")) return data;
      } catch { /* another queued document may still be writing */ }
    }
    return null;
    });
    return Boolean(payload);
  }).toBe(true);
  expect(Object.keys(payload.files)).toHaveLength(23);
  expect(payload.tables.products.filter(product => product.image)).toHaveLength(36);
  expect(payload.tables.drafts.some(row => row.id === "local:bundled-menu-photos-v1")).toBe(true);
  expect(payload.tables.drafts.some(row => row.id === "local:owner-access")).toBe(true);
});

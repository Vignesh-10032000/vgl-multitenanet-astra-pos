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
  await page.locator("#access-form").evaluate(form => form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  release();
  await expect(page.locator("#access-confirm-row")).toBeVisible();
  await expect(page.locator("#access-submit")).toBeEnabled();
  await expect(page.locator("#access-password")).toHaveValue("Fixture-only-owner-482!");
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

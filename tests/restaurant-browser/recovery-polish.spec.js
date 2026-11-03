import { test, expect } from "@playwright/test";
import { setup, order, MemoryImages, currentDefaults } from "../restaurant/helpers.js";
import { createAccount } from "../../restaurant/access.js";
import { createBackup } from "../../restaurant/backup.js";

test("RECOVERY-POLISH-01 existing-backup link reconnects, authenticates and restores a disposable folder snapshot", async ({ page }) => {
  const { db, ledger } = await setup({ settings: currentDefaults });
  let source;
  try {
    await ledger.saveLocalSetting("owner-access", await createAccount("recovery-owner", "Recovery-only-password-22!"), true);
    await ledger.checkout(order());
    source = await createBackup(ledger, new MemoryImages());
  } finally { await db.close(); }
  await page.goto("/");
  await expect(page.locator("#access-recover")).toBeEnabled();
  await page.evaluate(async source => {
    const folder = await (await navigator.storage.getDirectory()).getDirectoryHandle("recovery-fixture", { create: true });
    const file = await folder.getFileHandle("restaurant-backup-recovery-fixture.json", { create: true });
    const stream = await file.createWritable(); await stream.write(source); await stream.close();
    window.showDirectoryPicker = async () => folder;
  }, source);
  await page.locator("#access-recover").click();
  await expect(page.locator("#access-title")).toHaveText("Continue from your backup");
  await expect(page.locator("#access-username")).toHaveValue("");
  await page.locator("#access-username").fill("recovery-owner");
  await page.locator("#access-password").fill("wrong-password");
  await page.locator("#access-submit").click();
  await expect(page.locator("#access-error")).toHaveText("Backup username or password is incorrect");
  await expect(page.locator(".app-shell")).toBeHidden();
  await page.locator("#access-password").fill("Recovery-only-password-22!");
  const reload=page.waitForEvent("load");
  await page.locator("#access-submit").click(); await reload;
  await expect(page.locator("#access-screen")).toBeHidden();
  await page.locator("#last-receipt").click();
  await expect(page.locator("#receipt-preview .net")).toHaveText("TOTAL₹178.50");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(1);
});

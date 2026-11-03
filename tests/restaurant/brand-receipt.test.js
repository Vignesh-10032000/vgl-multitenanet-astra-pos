import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createBackup, restoreBackup } from "../../restaurant/backup.js";
import { installBrandLogo, BRAND_LOGO_KEY } from "../../restaurant/brand-logo.js";
import { receiptHTML } from "../../restaurant/documents.js";
import { setup, order, MemoryImages, database } from "./helpers.js";

const jpeg = `data:image/jpeg;base64,${readFileSync(new URL("../../restaurant/public/branding/v2/arafa-logo.jpg", import.meta.url)).toString("base64")}`;
const install = (ledger, images) => installBrandLogo({ ledger, images, readImage: async () => jpeg });

test("BRAND-01 one-time logo update preserves GST, saved identities, explicit removal and complete restore", async () => {
  const { ledger, db } = await setup();
  const target = await setup();
  const images = new MemoryImages(), restoredImages = new MemoryImages();
  try {
    const old = await ledger.checkout(order());
    const prior = await ledger.settings();
    assert.equal(await install(ledger, images), true);
    const current = await ledger.settings();
    assert.deepEqual({ ...current, logo: prior.logo, menu_logo: prior.menu_logo }, prior);
    assert.equal(current.menu_logo, false);
    assert.equal(await images.read(current.logo), jpeg);
    assert.deepEqual(await ledger.sale(old.id), old);
    const next = await ledger.checkout(order());
    assert.equal(next.identity.logo, current.logo);
    assert.equal(next.total_paise, old.total_paise);
    const backup = await createBackup(ledger, images);
    await restoreBackup(backup, target.ledger, restoredImages, async () => database());
    assert.deepEqual(await target.ledger.snapshot(), await ledger.snapshot());
    assert.equal(await restoredImages.read(current.logo), jpeg);
    await ledger.saveSettings({ ...current, logo: null, menu_logo: false });
    assert.equal(await installBrandLogo({ ledger, images, readImage: () => { throw new Error("Must not fetch again"); } }), false);
    assert.equal((await ledger.settings()).logo, null);
    assert.ok(await ledger.localSetting(BRAND_LOGO_KEY));
  } finally { await db.close(); await target.db.close(); }
});

test("BRAND-02 existing uploaded logo or explicit no-logo setting wins", async () => {
  for (const custom of [true, false]) {
    const { ledger, db } = await setup();
    const images = new MemoryImages();
    try {
      const settings = await ledger.settings();
      await ledger.saveSettings({ ...settings, logo: custom ? await images.put(jpeg) : null, menu_logo: false });
      const prior = await ledger.settings();
      assert.equal(await installBrandLogo({ ledger, images, readImage: () => { throw new Error("Unwanted replacement"); } }), false);
      assert.deepEqual(await ledger.settings(), prior);
    } finally { await db.close(); }
  }
});

test("BRAND-03 file failure retries and settings plus marker commit atomically", async () => {
  const { ledger, db } = await setup();
  const images = new MemoryImages();
  try {
    const prior = await ledger.snapshot();
    await assert.rejects(installBrandLogo({ ledger, images, readImage: () => { throw new Error("File unavailable"); } }), /File unavailable/);
    assert.deepEqual(await ledger.snapshot(), prior);
    await db.exec("CREATE TRIGGER brand_fail BEFORE INSERT ON drafts WHEN NEW.id='local:owner-brand-logo-v2' BEGIN SELECT RAISE(ABORT,'brand marker failure'); END;");
    await assert.rejects(install(ledger, images), /brand marker failure/);
    assert.deepEqual(await ledger.snapshot(), prior);
    await db.exec("DROP TRIGGER brand_fail");
    assert.equal(await install(ledger, images), true);
  } finally { await db.close(); }
});

test("RECEIPT-01 reference hierarchy uses saved exact discount, GST and round-off without changing a bill", async () => {
  const { ledger, db } = await setup({ now: () => "2026-09-30T18:30:00.000Z" });
  const images = new MemoryImages();
  try {
    await install(ledger, images);
    await ledger.saveSettings({ ...await ledger.settings(), round_rupee: true });
    const sale = await ledger.checkout(order({ discount_paise: 51, tendered_paise: 16900 }));
    const before = JSON.stringify(sale);
    const html = await receiptHTML(sale, images);
    assert.match(html, /<strong>Bill: AR\/2627\/000001<\/strong>/);
    assert.match(html, /1\/10\/2026, 12:00:00 am/);
    assert.match(html, /<th>ITEM<\/th>/);
    assert.match(html.replace(/<[^>]*>/g, ""), /Discount: ₹0\.51CGST 2\.5%: ₹4\.03SGST 2\.5%: ₹4\.04Round off: ₹-0\.49/);
    assert.match(html, /<span>TOTAL<\/span><span>₹169\.00<\/span>/);
    assert.doesNotMatch(html, /Cashier:|Gross \(selling price\)|NET AMOUNT|Items:|Taxable value:/);
    assert.equal(JSON.stringify(sale), before);
    assert.deepEqual(await ledger.sale(sale.id), sale);
  } finally { await db.close(); }
});

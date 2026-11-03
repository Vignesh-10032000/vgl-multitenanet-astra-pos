import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { installMenuPhotos, refreshMenuPhotos, MENU_PHOTO_KEY, MENU_PHOTO_REFRESH_KEY } from "../../restaurant/menu-photo-install.js";
import { createBackup, restoreBackup } from "../../restaurant/backup.js";
import { setup, database, MemoryImages, order } from "./helpers.js";
const legacy = JSON.parse(readFileSync(new URL("../../restaurant/menu-photos.json", import.meta.url)));
const manifest = JSON.parse(readFileSync(new URL("../../restaurant/menu-photo-refresh.json", import.meta.url)));
const readPhoto = async asset => `data:image/jpeg;base64,${readFileSync(new URL(`../../restaurant/public/${asset.src.slice(2)}`, import.meta.url)).toString("base64")}`;
async function fixture() {
  const result = await setup();
  result.images = new MemoryImages();
  await installMenuPhotos({ ...result, manifest: legacy, readPhoto });
  return result;
}

test("PHOTO-REFRESH-01 upgrades known illustrations once, preserving uploads, removals, renames, prices and sales", async () => {
  const { ledger, db, images } = await fixture();
  try {
    const sale = await ledger.checkout(order());
    const products = await ledger.products();
    const custom = await images.put("data:image/jpeg;base64,AQID");
    await ledger.saveProduct({ ...products.find(p => p.id === "menu-001"), image: custom });
    await ledger.saveProduct({ ...products.find(p => p.id === "menu-002"), image: null });
    await ledger.saveProduct({ ...products.find(p => p.id === "menu-003"), name: "Owner's special" });
    const before = await ledger.products();
    const settings = await ledger.settings();
    const v1 = await ledger.localSetting(MENU_PHOTO_KEY);
    assert.equal(await refreshMenuPhotos({ ledger, images, manifest, readPhoto }), 18);
    const after = await ledger.products();
    const withoutImages = rows => rows.map(row => { const copy = { ...row }; delete copy.image; return copy; });
    assert.deepEqual(withoutImages(after), withoutImages(before));
    for (const id of ["menu-001", "menu-002", "menu-003"])
      assert.deepEqual(after.find(p => p.id === id), before.find(p => p.id === id));
    assert.deepEqual(await ledger.sale(sale.id), sale);
    assert.deepEqual(await ledger.settings(), settings);
    assert.deepEqual(await ledger.localSetting(MENU_PHOTO_KEY), v1);
    assert.ok(await ledger.localSetting(MENU_PHOTO_REFRESH_KEY));
    const removed = after.find(p => p.id === "menu-021");
    await ledger.saveProduct({ ...removed, image: null });
    assert.equal(await refreshMenuPhotos({ ledger, images, manifest, readPhoto: () => assert.fail("Warm start must not reload") }), 0);
    assert.equal((await ledger.products()).find(p => p.id === removed.id).image, null);
  } finally { await db.close(); }
});

test("PHOTO-REFRESH-02 failed file preparation and transaction keep v1 references and markers intact", async () => {
  const { ledger, db, images } = await fixture();
  try {
    const before = await ledger.snapshot();
    let reads = 0;
    await assert.rejects(refreshMenuPhotos({ ledger, images, manifest, readPhoto: async asset => {
      if (++reads === 3) throw new Error("Interrupted asset");
      return readPhoto(asset);
    } }), /Interrupted asset/);
    assert.deepEqual(await ledger.snapshot(), before);
    await db.exec("CREATE TRIGGER photo_refresh_fail BEFORE INSERT ON drafts WHEN NEW.id='local:bundled-menu-photos-v2' BEGIN SELECT RAISE(ABORT,'refresh marker failure'); END;");
    await assert.rejects(refreshMenuPhotos({ ledger, images, manifest, readPhoto }), /refresh marker failure/);
    assert.deepEqual(await ledger.snapshot(), before);
    await db.exec("DROP TRIGGER photo_refresh_fail");
    assert.equal(await refreshMenuPhotos({ ledger, images, manifest, readPhoto }), 21);
  } finally { await db.close(); }
});

test("PHOTO-REFRESH-03 owner edits during preparation win the final atomic recheck", async () => {
  const { ledger, db, images } = await fixture();
  try {
    const custom = await images.put("data:image/jpeg;base64,BAUG");
    assert.equal(await refreshMenuPhotos({ ledger, images, manifest, readPhoto: async asset => {
      if (asset.slug === "chicken-biryani") {
        const products = await ledger.products();
        await ledger.saveProduct({ ...products.find(p => p.id === "menu-001"), image: custom });
        await ledger.saveProduct({ ...products.find(p => p.id === "menu-029"), image: null });
      }
      return readPhoto(asset);
    } }), 19);
    const products = await ledger.products();
    assert.equal(products.find(p => p.id === "menu-001").image, custom);
    assert.equal(products.find(p => p.id === "menu-029").image, null);
  } finally { await db.close(); }
});

test("PHOTO-REFRESH-04 complete restore includes web photographs and preserves both one-time markers", async () => {
  const source = await fixture(), target = await setup(), restored = new MemoryImages();
  try {
    await refreshMenuPhotos({ ...source, manifest, readPhoto });
    const backup = await createBackup(source.ledger, source.images);
    await restoreBackup(backup, target.ledger, restored, () => database());
    assert.deepEqual(await target.ledger.snapshot(), await source.ledger.snapshot());
    for (const product of await target.ledger.products())
      assert.equal(await restored.read(product.image), await source.images.read(product.image));
    assert.equal(await refreshMenuPhotos({ ...target, images: restored, manifest, readPhoto: () => assert.fail("Restored marker must skip") }), 0);
    assert.ok(await target.ledger.localSetting(MENU_PHOTO_KEY));
  } finally { await source.db.close(); await target.db.close(); }
});

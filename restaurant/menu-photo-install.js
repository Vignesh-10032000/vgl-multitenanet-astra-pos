export const MENU_PHOTO_KEY = "bundled-menu-photos-v1";
export const MENU_PHOTO_REFRESH_KEY = "bundled-menu-photos-v2";
export const MENU_PHOTO_RESTORE_KEY = "bundled-menu-photos-v3-illustrations";

async function readBundledPhoto(asset) {
  if (!/^\.\/menu-photos\/v[12]\/[a-z0-9-]+\.jpg$/.test(asset.src))
    throw new Error("Invalid bundled menu photo");
  const response = await fetch(new URL(asset.src, document.baseURI));
  if (!response.ok) throw new Error("Could not read bundled menu photo");
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length !== asset.bytes || bytes.length > 49152 || bytes[0] !== 255 || bytes[1] !== 216)
    throw new Error("Bundled menu photo is incomplete");
  const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map(value => value.toString(16).padStart(2, "0")).join("");
  if (hash !== asset.sha256) throw new Error("Bundled menu photo checksum differs");
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 16384)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  return `data:image/jpeg;base64,${btoa(binary)}`;
}

/** One-time bundled menu update: files first, product references atomically. */
export async function installMenuPhotos({ledger, images, manifest, readPhoto = readBundledPhoto}) {
  if (await ledger.localSetting(MENU_PHOTO_KEY)) return 0;
  const products = await ledger.products();
  const changes = [];
  // Sequential reads bound temporary memory on the TVS and deduplicate portion variants.
  for (const asset of manifest.assets) {
    const matches = asset.products.filter(expected => products.some(product =>
      product.id === expected.id && product.name === expected.name &&
      product.portion === expected.portion && !product.image));
    if (!matches.length) continue;
    const image = await images.put(await readPhoto(asset));
    for (const expected of matches) changes.push({...expected, image});
  }
  return ledger.installProductPhotos(MENU_PHOTO_KEY, changes);
}

/** Replace only the known v1 illustration, never an upload, removal or renamed dish. */
export async function refreshMenuPhotos({ledger, images, manifest, readPhoto = readBundledPhoto, key = MENU_PHOTO_REFRESH_KEY}) {
  if (await ledger.localSetting(key)) return 0;
  const products = await ledger.products();
  const changes = [];
  for (const asset of manifest.assets) {
    const matches = asset.products.filter(expected => products.some(product =>
      product.id === expected.id && product.name === expected.name &&
      product.portion === expected.portion && expected.previous_image &&
      product.image === expected.previous_image));
    if (!matches.length) continue;
    const image = await images.put(await readPhoto(asset));
    for (const expected of matches) changes.push({...expected, image});
  }
  return ledger.installProductPhotos(key, changes);
}

/** Owner-approved return to originals; existing v1/v2 markers remain untouched. */
export function restoreMenuIllustrations(options) {
  return refreshMenuPhotos({ ...options, key: MENU_PHOTO_RESTORE_KEY });
}

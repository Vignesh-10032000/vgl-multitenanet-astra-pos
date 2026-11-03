export const BRAND_LOGO_KEY = "owner-brand-logo-v2";
const asset = {
  src: "./branding/v2/arafa-logo.jpg",
  bytes: 54216,
  sha256: "d664af6e5761f468b61e4dbaab29be568719cfcd6e5918cded7e279d9b144d0a",
};

async function readLogo() {
  const response = await fetch(new URL(asset.src, document.baseURI));
  if (!response.ok) throw new Error("Could not read the bundled restaurant logo");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map(value => value.toString(16).padStart(2, "0")).join("");
  if (bytes.length !== asset.bytes || hash !== asset.sha256)
    throw new Error("Bundled restaurant logo is incomplete");
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 16384)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  return `data:image/jpeg;base64,${btoa(binary)}`;
}

/** Install the owner's replacement once; retain uploads, removals and saved identities. */
export async function installBrandLogo({ ledger, images, readImage = readLogo }) {
  if (await ledger.localSetting(BRAND_LOGO_KEY)) return false;
  const settings = await ledger.settings();
  const image = !settings.logo && settings.menu_logo
    ? await images.put(await readImage()) : null;
  return ledger.installBrandLogo(BRAND_LOGO_KEY, image);
}

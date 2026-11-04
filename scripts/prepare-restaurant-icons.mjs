import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

// Code-native equivalent of the owner's cloche/receipt reference. Share geometry
// across browser and Android resources; no uploaded logo is edited or regenerated.
const root = resolve(import.meta.dirname, "..");
const res = resolve(root, "android/app/src/main/res");
const publicRoot = resolve(root, "restaurant/public");
const source = resolve(root, "resources/branding/2026-11-02");
const dome = "M30,55C30,41.75 40.75,31 54,31C67.25,31 78,41.75 78,55Q78,56 77,56H31Q30,56 30,55Z";
const highlight = "M31,55C31,42.3 41.3,32 54,32C45,35 39,44 38,55Z";
const knob = "M50,31V28A4,4 0,1 1,58,28V31Z";
const tray = "M27,59H81A3,3 0,0 1,81,65H27A3,3 0,0 1,27,59Z";
const receipt = "M41,68H67V82Q67,84 65,84L62,81L58,84L54,81L50,84L46,81L43,84Q41,84 41,82Z";
const lines = "M47,72H61A1,1 0,0 1,61,74H47A1,1 0,0 1,47,72ZM47,77H55A1,1 0,0 1,55,79H47A1,1 0,0 1,47,77Z";
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="108" viewBox="0 0 108 108"><defs><linearGradient id="blue" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#09CFEB"/><stop offset=".45" stop-color="#007DFF"/><stop offset="1" stop-color="#0637AE"/></linearGradient><linearGradient id="white" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FFFFFF"/><stop offset="1" stop-color="#DFECFF"/></linearGradient></defs><rect width="108" height="108" rx="23" fill="url(#blue)"/><path d="M0,22Q0,0 23,0H49L0,49Z" fill="#7AF2FF" opacity=".12"/><path d="M108,68V85Q108,108 85,108H56Z" fill="#00D8F4" opacity=".18"/><g fill="url(#white)"><path d="${dome}"/><path d="${knob}"/><path d="${tray}"/><path d="${receipt}"/></g><path d="${highlight}" fill="white"/><path d="${lines}" fill="#0951CC"/></svg>`;
const vector = paths => `<vector xmlns:android="http://schemas.android.com/apk/res/android" xmlns:aapt="http://schemas.android.com/aapt" android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">\n${paths}\n</vector>\n`;
const gradientPath = path => `<path android:pathData="${path}"><aapt:attr name="android:fillColor"><gradient android:startX="0" android:startY="0" android:endX="108" android:endY="108" android:type="linear"><item android:offset="0" android:color="#09CFEB"/><item android:offset="0.45" android:color="#007DFF"/><item android:offset="1" android:color="#0637AE"/></gradient></aapt:attr></path>`;
const foreground = `<path android:fillColor="#F8FBFF" android:pathData="${dome}${knob}${tray}${receipt}"/><path android:fillColor="#FFFFFF" android:pathData="${highlight}"/><path android:fillColor="#0951CC" android:pathData="${lines}"/>`;
const rounded = "M23,0H85Q108,0 108,23V85Q108,108 85,108H23Q0,108 0,85V23Q0,0 23,0Z";
const adaptive = monochrome => `<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android"><background android:drawable="@drawable/restaurant_icon_background"/><foreground android:drawable="@drawable/restaurant_icon_foreground"/>${monochrome ? '<monochrome android:drawable="@drawable/restaurant_icon_monochrome"/>' : ""}</adaptive-icon>\n`;
mkdirSync(source, { recursive: true });
writeFileSync(resolve(source, "restaurant-pos-icon.svg"), svg);
writeFileSync(resolve(publicRoot, "favicon.svg"), svg);
writeFileSync(resolve(res, "drawable/ic_restaurant.xml"), vector(`${gradientPath(rounded)}\n${foreground}`));
writeFileSync(resolve(res, "drawable/restaurant_icon_background.xml"), vector(gradientPath("M0,0H108V108H0Z")));
writeFileSync(resolve(res, "drawable/restaurant_icon_foreground.xml"), vector(foreground));
writeFileSync(resolve(res, "drawable/restaurant_icon_monochrome.xml"), vector(`<path android:fillColor="#FFFFFF" android:fillType="evenOdd" android:pathData="${dome}${knob}${tray}${receipt}${lines}"/>`));
for (const [folder, themed] of [["mipmap-anydpi-v26", false], ["mipmap-anydpi-v33", true]]) {
  mkdirSync(resolve(res, folder), { recursive: true });
  for (const name of ["ic_launcher.xml", "ic_launcher_round.xml"])
    writeFileSync(resolve(res, folder, name), adaptive(themed));
}
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  for (const [density, size] of Object.entries({ mdpi: 48, hdpi: 72, xhdpi: 96, xxhdpi: 144, xxxhdpi: 192, preview: 512 })) {
    const pngs = await page.evaluate(async ({ svg, size }) => {
      const image = new Image();
      image.src = `data:image/svg+xml;base64,${btoa(svg)}`;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0, size, size);
      const regular = canvas.toDataURL();
      context.clearRect(0, 0, size, size);
      context.beginPath(); context.arc(size / 2, size / 2, size / 2, 0, 2 * Math.PI); context.clip();
      context.drawImage(image, 0, 0, size, size);
      return { regular, round: canvas.toDataURL() };
    }, { svg, size });
    if (density === "preview") {
      writeFileSync(resolve(source, "restaurant-pos-icon-preview.png"), Buffer.from(pngs.regular.split(",")[1], "base64"));
      continue;
    }
    for (const [name, data] of [["ic_launcher.png", pngs.regular], ["ic_launcher_round.png", pngs.round]])
      writeFileSync(resolve(res, `mipmap-${density}`, name), Buffer.from(data.split(",")[1], "base64"));
  }
} finally { await browser.close(); }
if (!readFileSync(resolve(publicRoot, "favicon.svg"), "utf8").includes(receipt)) throw new Error("Incomplete restaurant icon");
console.log("Generated restaurant icon: SVG, Android vectors/adaptive layers and five legacy PNG densities.");

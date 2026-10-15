import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const dist = path.join(root, "src/vglpos/web/static/dist");
const fonts = path.join(root, "src/vglpos/web/static/fonts");

async function manifest() {
  return JSON.parse(await readFile(path.join(dist, "manifest.json"), "utf8"));
}

function collectEntryFiles(entries, source, files = new Set()) {
  const entry = entries[source];
  assert.ok(entry, `missing Vite manifest entry ${source}`);
  files.add(entry.file);
  for (const stylesheet of entry.css || []) files.add(stylesheet);
  for (const dependency of entry.imports || []) collectEntryFiles(entries, dependency, files);
  return files;
}

async function bytes(files, extension) {
  let total = 0;
  for (const file of files) {
    if (path.extname(file) === extension) total += (await stat(path.join(dist, file))).size;
  }
  return total;
}

test("Vite emits hashed production assets within the POS budgets", async () => {
  const entries = await manifest();
  const files = new Set([
    ...collectEntryFiles(entries, "js/app.js"),
    ...collectEntryFiles(entries, "js/pos.js"),
  ]);
  files.add(entries["style.css"].file);
  const jsBytes = await bytes(files, ".js");
  const cssBytes = await bytes(files, ".css");
  const fontFiles = (await readdir(fonts)).filter((file) => file.endsWith(".woff2"));
  const fontBytes = await Promise.all(fontFiles.map((file) => stat(path.join(fonts, file))))
    .then((items) => items.reduce((total, item) => total + item.size, 0));

  assert.ok(jsBytes < 45_000, `POS JavaScript is ${jsBytes} bytes`);
  assert.ok(cssBytes > 0, "POS CSS is missing from the Vite manifest");
  assert.ok(cssBytes < 45_000, `POS CSS is ${cssBytes} bytes`);
  assert.ok(fontBytes < 90_000, `fonts are ${fontBytes} bytes`);
  assert.ok(jsBytes + cssBytes + fontBytes < 200_000, "POS static assets exceed 200 KB");

  for (const source of ["js/app.js", "js/pos.js"]) {
    assert.match(entries[source].file, /-[A-Za-z0-9_-]{8}\.js$/);
  }
});

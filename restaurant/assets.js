import { Capacitor } from "@capacitor/core";
import { get, set } from "idb-keyval";
import { validateImagePath } from "./repository.js";
import { ImageReadCache } from "./image-read-cache.js";

export async function digest(value) {
  return [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  ]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Immutable, content-addressed local files keep old receipt logos available after edits. */
export class ImageStore {
  cache = new ImageReadCache();
  async read(path) {
    validateImagePath(path);
    if (!path) return null;
    return this.cache.read(path, async () => {
      let data;
      if (Capacitor.isNativePlatform()) {
        const { Filesystem, Directory } = await import("@capacitor/filesystem");
        data = `data:image/jpeg;base64,${(await Filesystem.readFile({ path, directory: Directory.Data })).data}`;
      } else data = await get(`restaurant:${path}`);
      if (!data)
        throw new Error("Local image is missing; restore a complete backup");
      return data;
    });
  }
  async put(data) {
    if (
      !/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(data) ||
      data.length > 1200000
    )
      throw new Error("Invalid image (maximum 900 KB)");
    const path = `images/${await digest(data)}.jpg`;
    if (Capacitor.isNativePlatform()) {
      const { Filesystem, Directory } = await import("@capacitor/filesystem");
      await Filesystem.writeFile({
        path,
        directory: Directory.Data,
        recursive: true,
        data: data.split(",")[1],
      });
    } else await set(`restaurant:${path}`, data);
    this.cache.remember(path, data);
    return path;
  }
  async select(file, max = 640) {
    if (
      !file ||
      !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
      file.size > 15000000
    )
      throw new Error("Choose a JPG, PNG or WebP under 15 MB");
    const url = URL.createObjectURL(file);
    const image = new Image();
    try {
      image.src = url;
      await image.decode();
      const scale = Math.min(1, max / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      return this.put(canvas.toDataURL("image/jpeg", 0.85));
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

export function referencedImages(tables) {
  const paths = new Set();
  for (const p of tables.products) if (p.image) paths.add(p.image);
  const settings = JSON.parse(tables.settings[0].value);
  if (settings.logo) paths.add(settings.logo);
  for (const sale of tables.sales) {
    const s = JSON.parse(sale.identity);
    if (s.logo) paths.add(s.logo);
  }
  return [...paths];
}

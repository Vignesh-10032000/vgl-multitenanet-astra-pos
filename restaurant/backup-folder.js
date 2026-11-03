import { Capacitor, registerPlugin } from "@capacitor/core";
import { get, set } from "idb-keyval";
const native = registerPlugin("RestaurantBackup");

export function backupFolder() {
  if (Capacitor.isNativePlatform())
    return {
      status: () => native.folderStatus(),
      choose: () => native.chooseFolder(),
      list: async () => (await native.listBackups()).files,
      read: async (uri) => (await native.readBackup({ uri })).source,
      write: (name, source) => native.writeBackup({ name, source }),
    };
  let handle;
  const folder = async () => {
    handle ||= await get("restaurant-shared-backup-folder");
    if (
      !handle ||
      (await handle.queryPermission({ mode: "readwrite" })) !== "granted"
    )
      throw new Error("Reconnect your shared backup folder");
    return handle;
  };
  return {
    async status() {
      try {
        const directory = await folder();
        return { connected: true, name: directory.name };
      } catch {
        return { connected: false };
      }
    },
    async choose() {
      if (!window.showDirectoryPicker)
        throw new Error(
          "Folder access needs the Android app or desktop Chrome/Edge. You can still save and restore backup files below.",
        );
      handle = await window.showDirectoryPicker({
        id: "restaurant-backups",
        mode: "readwrite",
        startIn: "documents",
      });
      await set("restaurant-shared-backup-folder", handle);
    },
    async list() {
      const rows = [];
      for await (const [name, entry] of (await folder()).entries())
        if (
          entry.kind === "file" &&
          name.startsWith("restaurant-backup-") &&
          name.endsWith(".json")
        ) {
          const file = await entry.getFile();
          rows.push({
            name,
            uri: name,
            modified: file.lastModified,
            size: file.size,
          });
        }
      return rows;
    },
    async read(name) {
      if (!/^restaurant-backup-[^/\\]+\.json$/.test(name))
        throw new Error("Invalid backup file");
      const file = await (await (await folder()).getFileHandle(name)).getFile();
      if (file.size > 100000000) throw new Error("Backup exceeds 100 MB limit");
      return file.text();
    },
    async write(name, source) {
      const file = await (await folder()).getFileHandle(name, { create: true });
      const stream = await file.createWritable();
      try {
        await stream.write(source);
        await stream.close();
      } catch (error) {
        await stream.abort().catch(() => {});
        throw error;
      }
      return { state: "saved", uri: name };
    },
  };
}

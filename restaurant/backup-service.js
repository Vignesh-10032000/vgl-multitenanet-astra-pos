import { createBackup, inspectBackup, restoreBackup } from "./backup.js";
import { operationId } from "./domain.js";

/** Append-only shared-folder snapshots; finding a backup never replaces a live ledger. */
export class PersistentBackups {
  #tail = Promise.resolve();
  constructor({ ledger, images, transport, makeDatabase, status = () => {} }) {
    Object.assign(this, { ledger, images, transport, makeDatabase, status });
    this.connected = false;
  }
  async initialize() {
    const state = await this.transport.status();
    this.connected = state.connected;
    this.status(
      state.connected
        ? `Connected to ${state.name}. Automatic backups are enabled.`
        : "Choose a shared folder for backups that remain after uninstall.",
    );
    return state;
  }
  async connect() {
    await this.transport.choose();
    return this.initialize();
  }
  save() {
    const work = this.#tail.then(async () => {
      if (!this.connected) return { state: "not_configured" };
      this.status("Saving a complete backup to your shared folder…");
      const source = await createBackup(this.ledger, this.images);
      const name = `restaurant-backup-${new Date().toISOString().replaceAll(":", "-")}-${operationId()}.json`;
      const saved = await this.transport.write(name, source);
      // Provider success is checked by reading and validating the completed document.
      const read = await this.transport.read(saved.uri);
      await inspectBackup(read, this.makeDatabase);
      if (read !== source)
        throw new Error("The saved backup does not match the ledger snapshot");
      this.status(
        `Backup saved · ${new Date().toLocaleTimeString("en-IN")} · ${name}`,
      );
      return saved;
    });
    this.#tail = work.catch(() => {});
    return work.catch((error) => {
      this.status(
        `Backup needs attention: ${error.message}. The bill remains saved in this app.`,
      );
      throw error;
    });
  }
  async discover() {
    if (!this.connected)
      throw new Error("Reconnect your shared backup folder first");
    const files = (await this.transport.list()).sort(
      (a, b) => b.modified - a.modified,
    );
    const valid = [],
      rejected = [];
    // Inspect the most recent 20; older files remain untouched in the folder.
    for (const file of files.slice(0, 20)) {
      try {
        const source = await this.transport.read(file.uri);
        const data = await inspectBackup(source, this.makeDatabase);
        const checksum = JSON.parse(source).sha256;
        valid.push({
          ...file,
          billCount: data.tables.sales.length,
          data: {
            created_at: data.created_at,
            tables: {
              drafts: data.tables.drafts.filter(
                (row) => row.id === "local:owner-access",
              ),
            },
          },
          restore: async () => {
            const current = await this.transport.read(file.uri);
            if (JSON.parse(current).sha256 !== checksum)
              throw new Error(
                "Backup changed. Scan the folder again before recovering.",
              );
            return restoreBackup(
              current,
              this.ledger,
              this.images,
              this.makeDatabase,
            );
          },
        });
      } catch (error) {
        rejected.push({ name: file.name, reason: error.message });
      }
    }
    valid.sort((a, b) => b.data.created_at.localeCompare(a.data.created_at));
    return { valid, rejected };
  }
}

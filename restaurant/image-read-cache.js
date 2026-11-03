/** Bound retained data URLs and share reads of identical immutable image paths. */
export class ImageReadCache {
  constructor(maxBytes = 8 * 1024 * 1024) {
    if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) throw new Error("Invalid image cache budget");
    this.maxBytes = maxBytes;
    this.bytes = 0;
    this.entries = new Map();
    this.pending = new Map();
  }
  remember(path, data) {
    if (typeof data !== "string" || !data) throw new Error("Local image is missing");
    const previous = this.entries.get(path);
    if (previous !== undefined) {
      this.bytes -= previous.length * 2;
      this.entries.delete(path);
    }
    const size = data.length * 2;
    // An oversized image is still returned to its caller, without retaining a
    // second long-lived copy here. Budget counts conservative UTF-16 payload bytes.
    if (size > this.maxBytes) return;
    while (this.bytes + size > this.maxBytes) {
      const oldest = this.entries.keys().next().value;
      this.bytes -= this.entries.get(oldest).length * 2;
      this.entries.delete(oldest);
    }
    this.entries.set(path, data);
    this.bytes += size;
  }
  async read(path, load) {
    if (this.entries.has(path)) {
      const data = this.entries.get(path);
      this.entries.delete(path);
      this.entries.set(path, data);
      return data;
    }
    if (this.pending.has(path)) return this.pending.get(path);
    const work = Promise.resolve().then(load).then(data => {
      this.remember(path, data);
      return data;
    }).finally(() => this.pending.delete(path));
    this.pending.set(path, work);
    return work;
  }
}

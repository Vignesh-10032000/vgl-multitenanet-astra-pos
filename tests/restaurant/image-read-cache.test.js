import test from "node:test";
import assert from "node:assert/strict";
import { ImageReadCache } from "../../restaurant/image-read-cache.js";

test("IMAGE-CACHE-01 concurrent portion variants share one read and retain exact bytes", async () => {
  const cache = new ImageReadCache();
  let finish, reads = 0;
  const load = () => { reads++; return new Promise(resolve => { finish = resolve; }); };
  const requests = Array.from({ length: 36 }, () => cache.read("same-original.jpg", load));
  await Promise.resolve();
  assert.equal(reads, 1);
  finish("data:image/jpeg;base64,original-bytes");
  assert.deepEqual(await Promise.all(requests), Array(36).fill("data:image/jpeg;base64,original-bytes"));
  assert.equal(await cache.read("same-original.jpg", load), "data:image/jpeg;base64,original-bytes");
  assert.equal(reads, 1);
  assert.equal(cache.pending.size, 0);
});

test("IMAGE-CACHE-02 failed or missing local reads remain retryable without stale cache entries", async () => {
  const cache = new ImageReadCache();
  let reads = 0;
  const failed = () => { reads++; throw new Error("Disconnected storage"); };
  await assert.rejects(Promise.all([cache.read("dish", failed), cache.read("dish", failed)]), /Disconnected storage/);
  assert.equal(reads, 1);
  assert.equal(cache.pending.size, 0);
  await assert.rejects(cache.read("dish", () => null), /missing/);
  assert.equal(await cache.read("dish", () => "restored image"), "restored image");
});

test("IMAGE-CACHE-03 retained payload is bounded and least-recently-used entries can be read again", async () => {
  const cache = new ImageReadCache(12);
  await cache.read("one", () => "aaa");
  await cache.read("two", () => "bbb");
  await cache.read("one", () => { throw new Error("Unexpected read"); });
  await cache.read("three", () => "ccc");
  assert.equal(cache.bytes, 12);
  assert.equal(cache.entries.has("one"), true);
  assert.equal(cache.entries.has("two"), false);
  assert.equal(await cache.read("two", () => "bbb"), "bbb");
  assert.ok(cache.bytes <= cache.maxBytes);
  cache.remember("two", "b");
  assert.equal(cache.bytes, 8);
});

test("IMAGE-CACHE-04 oversized images are usable without permanently exceeding the cache budget", async () => {
  const cache = new ImageReadCache(4);
  let reads = 0;
  const load = () => { reads++; return "large original image"; };
  assert.equal(await cache.read("large", load), "large original image");
  assert.equal(cache.bytes, 0);
  assert.equal(await cache.read("large", load), "large original image");
  assert.equal(reads, 2);
  assert.throws(() => new ImageReadCache(0));
});

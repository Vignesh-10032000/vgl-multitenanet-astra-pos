import assert from "node:assert/strict";
import test from "node:test";

import { assertOutboxCapacity, OUTBOX_LIMIT } from "../../src/vglpos/web/static/src/js/offline-db.js";

test("offline outbox blocks the 501st bill without dropping existing entries", () => {
  assert.equal(OUTBOX_LIMIT, 500);
  assert.doesNotThrow(() => assertOutboxCapacity(499));
  assert.throws(
    () => assertOutboxCapacity(500),
    (error) => error.name === "OutboxFullError" && /Reconnect/.test(error.message),
  );
});

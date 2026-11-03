import test from "node:test";
import assert from "node:assert/strict";
import {
  OwnerAccess,
  createAccount,
  verifyAccount,
  ACCESS_KEY,
} from "../../restaurant/access.js";
import {
  analyticsSummary,
  trendSeries,
  rollingDates,
} from "../../restaurant/analytics.js";
import { PersistentBackups } from "../../restaurant/backup-service.js";
import { setup, order, database, MemoryImages } from "./helpers.js";
import {
  createBackup,
  restoreBackup,
  inspectBackup,
} from "../../restaurant/backup.js";

const session = () => {
  const map = new Map();
  return {
    getItem: (k) => map.get(k),
    setItem: (k, v) => map.set(k, v),
    removeItem: (k) => map.delete(k),
  };
};

test("ACCESS-03 legacy recovery authenticates the current owner before replacing sales", async () => {
  const { ledger, db } = await setup();
  const fresh = await setup();
  try {
    await ledger.checkout(order());
    const source = await createBackup(ledger, new MemoryImages());
    const data = await inspectBackup(source, () => database());
    await ledger.checkout(order());
    const access = new OwnerAccess(ledger, session());
    const owner = await access.setup("owner", "A-local-test-password!");
    const candidate = {
      data,
      restore: () =>
        restoreBackup(source, ledger, new MemoryImages(), () => database()),
    };
    await assert.rejects(
      access.recover(candidate, "owner", "wrong"),
      /incorrect/,
    );
    assert.equal((await ledger.snapshot()).sales.length, 2);
    await access.recover(candidate, "owner", "A-local-test-password!");
    assert.equal((await ledger.snapshot()).sales.length, 1);
    assert.deepEqual(await ledger.localSetting(ACCESS_KEY), owner);
    assert.equal(await access.unlocked(), true);
    const firstInstall = new OwnerAccess(fresh.ledger, session());
    const legacy = {
      data,
      restore: () =>
        restoreBackup(source, fresh.ledger, new MemoryImages(), () =>
          database(),
        ),
    };
    await assert.rejects(
      firstInstall.recover(legacy, "new-owner", "short"),
      /10–128/,
    );
    assert.equal((await fresh.ledger.snapshot()).sales.length, 0);
    await firstInstall.recover(legacy, "new-owner", "A-new-local-password!");
    assert.equal((await fresh.ledger.snapshot()).sales.length, 1);
    assert.equal(await firstInstall.unlocked(), true);
  } finally {
    await db.close();
    await fresh.db.close();
  }
});

test("ACCESS-01 local owner uses salted PBKDF2, rejects wrong passwords, locks and throttles attempts", async () => {
  const { ledger, db } = await setup();
  try {
    let now = 1000;
    const memory = session(),
      access = new OwnerAccess(ledger, memory, () => now);
    const account = await access.setup("Owner", "A-local-test-password!");
    assert.equal(account.username, "owner");
    assert.equal(
      JSON.stringify(account).includes("A-local-test-password!"),
      false,
    );
    assert.equal(await access.unlocked(), true);
    await assert.rejects(
      access.setup("other", "Another-password!"),
      /already exists/,
    );
    access.lock();
    assert.equal(await access.unlocked(), false);
    const attempts = await Promise.allSettled(
      Array.from({ length: 5 }, () => access.login("owner", "wrong")),
    );
    assert.ok(
      attempts.every(
        (attempt) =>
          attempt.status === "rejected" &&
          /incorrect/.test(attempt.reason.message),
      ),
    );
    await assert.rejects(
      access.login("owner", "A-local-test-password!"),
      /30 seconds/,
    );
    now += 31000;
    await access.login("owner", "A-local-test-password!");
    assert.equal(await new OwnerAccess(ledger, memory).unlocked(), true);
    const second = await createAccount("Owner", "A-local-test-password!");
    assert.notEqual(account.salt, second.salt);
    assert.notEqual(account.verifier, second.verifier);
    assert.equal(
      await verifyAccount(account, "owner", "A-local-test-password!"),
      true,
    );
  } finally {
    await db.close();
  }
});

test("ACCESS-02 restoring a pre-login backup retains the configured owner and ledger numbering", async () => {
  const { ledger, db } = await setup();
  try {
    await ledger.checkout(order());
    const source = await createBackup(ledger, new MemoryImages());
    const access = new OwnerAccess(ledger, session());
    const owner = await access.setup("owner", "A-local-test-password!");
    await restoreBackup(source, ledger, new MemoryImages(), () => database());
    assert.deepEqual(await ledger.localSetting(ACCESS_KEY), owner);
    assert.ok((await ledger.checkout(order())).bill_number.endsWith("000002"));
  } finally {
    await db.close();
  }
});

test("ANALYTICS-01 selected GST components add back exactly and negative revenue remains charted", async () => {
  const { ledger, db } = await setup({ now: () => "2026-10-30T04:00:00.000Z" });
  try {
    await ledger.checkout(
      order({
        payments: [
          { method: "cash", amount_paise: 7001 },
          { method: "upi", amount_paise: 9999 },
        ],
      }),
    );
    const reports = await Promise.all(
      ["all", "cash", "upi"].map((method) =>
        ledger.report({ from: "2026-10-01", to: "2026-10-30", method }),
      ),
    );
    const [all, cash, upi] = reports.map(analyticsSummary);
    assert.equal(all.gst_paise, 810);
    assert.equal(cash.gst_paise + upi.gst_paise, all.gst_paise);
    assert.equal(cash.cgst_paise + upi.cgst_paise, all.cgst_paise);
    assert.equal(cash.sgst_paise + upi.sgst_paise, all.sgst_paise);
    assert.equal(all.average_paise, 17000);
    assert.equal(all.split_bills, 1);
    const r = {
      ...reports[0],
      from: "2026-10-29",
      daily: [{ day: "2026-10-30", net_paise: -501 }],
    };
    assert.deepEqual(
      trendSeries(r).map((p) => p.net_paise),
      [0, -501],
    );
    assert.equal(
      trendSeries(r, "weekly").reduce((n, p) => n + p.net_paise, 0),
      -501,
    );
    assert.deepEqual(rollingDates(7, "2026-01-02"), {
      from: "2025-12-27",
      to: "2026-01-02",
    });
  } finally {
    await db.close();
  }
});

test("BACKUP-FOLDER-01 snapshots survive a new app instance; corrupt newest files never replace the ledger", async () => {
  const { ledger, db } = await setup();
  const target = await setup();
  const files = new Map();
  const transport = {
    status: async () => ({ connected: true, name: "Shared test folder" }),
    choose: async () => {},
    write: async (name, source) => {
      files.set(name, source);
      return { uri: name };
    },
    read: async (name) => files.get(name),
    list: async () =>
      [...files.keys()].map((name, index) => ({
        name,
        uri: name,
        modified: index,
      })),
  };
  try {
    const service = new PersistentBackups({
      ledger,
      images: new MemoryImages(),
      transport,
      makeDatabase: () => database(),
    });
    await service.initialize();
    await ledger.checkout(order());
    await service.save();
    files.set("restaurant-backup-broken.json", "truncated");
    const reopened = new PersistentBackups({
      ledger: target.ledger,
      images: new MemoryImages(),
      transport,
      makeDatabase: () => database(),
    });
    await reopened.initialize();
    const result = await reopened.discover();
    assert.equal(result.valid.length, 1);
    assert.equal(result.rejected.length, 1);
    assert.equal(result.valid[0].billCount, 1);
    assert.equal((await target.ledger.snapshot()).sales.length, 0);
    await result.valid[0].restore();
    assert.equal((await target.ledger.snapshot()).sales.length, 1);
    assert.equal(files.size, 2);
    transport.write = async () => {
      throw new Error("No space left");
    };
    await assert.rejects(reopened.save(), /No space/);
    assert.equal((await target.ledger.snapshot()).sales.length, 1);
    assert.equal(files.size, 2);
  } finally {
    await db.close();
    await target.db.close();
  }
});

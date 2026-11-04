import { digest, referencedImages } from "./assets.js";
import { Ledger, validateImagePath, validateSettings } from "./repository.js";
import { TABLES, VERSION, LEGACY_TABLES, V2_TABLES } from "./schema.js";
import { billNumber, financialYear, payments, quote } from "./domain.js";
import { ACCESS_KEY, backupAccount } from "./access.js";
import { validateMenuType } from "./product-options.js";

function validateTableShape(tables, schema) {
  if (Object.keys(tables).sort().join() !== Object.keys(schema).sort().join())
    throw new Error("Incomplete backup tables");
  for (const [table, columns] of Object.entries(schema)) {
    if (!Array.isArray(tables[table])) throw new Error("Invalid backup table");
    for (const row of tables[table]) {
      if (Object.keys(row).sort().join() !== [...columns].sort().join())
        throw new Error(`Invalid columns in ${table}`);
      for (const value of Object.values(row))
        if (
          !(
            value === null ||
            typeof value === "string" ||
            Number.isSafeInteger(value)
          )
        )
          throw new Error("Invalid backup value");
    }
  }
}

export async function createBackup(ledger, images) {
  // Snapshot is read within one SQLite transaction, never by copying an open database file.
  const tables = await ledger.snapshot();
  const files = {};
  for (const path of referencedImages(tables))
    files[path] = await images.read(path);
  const payload = JSON.stringify({
    format: "vgl-restaurant-backup",
    version: VERSION,
    created_at: new Date().toISOString(),
    tables,
    files,
  });
  return JSON.stringify({ sha256: await digest(payload), payload });
}

/** Validate in a disposable SQLite database before touching the active ledger or files. */
export async function inspectBackup(source, makeDatabase) {
  if (source.length > 100000000) throw new Error("Backup exceeds 100 MB limit");
  const envelope = JSON.parse(source);
  if (
    typeof envelope.payload !== "string" ||
    (await digest(envelope.payload)) !== envelope.sha256
  )
    throw new Error("Backup checksum does not match");
  const data = JSON.parse(envelope.payload);
  if (typeof data.created_at !== "string" || !Number.isFinite(Date.parse(data.created_at)) || new Date(data.created_at).toISOString() !== data.created_at)
    throw new Error("Invalid backup creation date");
  if (
    data.format !== "vgl-restaurant-backup" ||
    ![1, 2, VERSION].includes(data.version)
  )
    throw new Error("Unsupported backup format/version");
  const { tables, files } = data;
  backupAccount(data);
  if (data.version === 1) {
    validateTableShape(tables, LEGACY_TABLES);
    tables.payments = tables.payments.map((p) => ({ ...p, position: 0 }));
    tables.adjustment_payments = tables.adjustments.map((a) => {
      const payment = tables.payments.find((p) => p.sale_id === a.sale_id);
      if (!payment) throw new Error("Correction payment missing");
      return {
        adjustment_id: a.id,
        method: payment.method,
        amount_paise: a.amount_paise,
      };
    });
    data.version = 2;
  }
  if (data.version === 2) {
    validateTableShape(tables, V2_TABLES);
    for (const name of ["sales", "sale_lines"])
      tables[name] = tables[name].map(row => ({ ...row, tax_inclusive: 1 }));
    data.version = VERSION;
  }
  if (Object.keys(tables).sort().join() !== Object.keys(TABLES).sort().join())
    throw new Error("Incomplete backup tables");
  for (const [table, columns] of Object.entries(TABLES)) {
    if (!Array.isArray(tables[table])) throw new Error("Invalid backup table");
    for (const row of tables[table]) {
      if (Object.keys(row).sort().join() !== [...columns].sort().join())
        throw new Error(`Invalid columns in ${table}`);
      for (const value of Object.values(row))
        if (
          !(
            value === null ||
            typeof value === "string" ||
            Number.isSafeInteger(value)
          )
        )
          throw new Error("Invalid backup value");
    }
  }
  if (tables.settings.length !== 1 || tables.settings[0].id !== "store")
    throw new Error("Store settings missing");
  validateSettings(JSON.parse(tables.settings[0].value));
  for (const path of referencedImages(tables)) {
    validateImagePath(path);
    if (
      !files[path] ||
      `images/${await digest(files[path])}.jpg` !== path ||
      !/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(files[path]) ||
      files[path].length > 1200000
    )
      throw new Error("Backup image is missing or corrupt");
  }
  for (const key of Object.keys(files))
    if (!referencedImages(tables).includes(key))
      throw new Error("Unexpected file in backup");
  const db = await makeDatabase();
  const scratch = new Ledger(db);
  try {
    await scratch.initialize([], {});
    await scratch.replace(tables);
    if ((await db.query("PRAGMA integrity_check"))[0].integrity_check !== "ok")
      throw new Error("SQLite integrity check failed");
    for (const product of tables.products) {
      validateImagePath(product.image);
      if (
        !product.name.trim() ||
        !product.portion.trim() ||
        !product.category.trim()
      )
        throw new Error("Invalid menu item");
    }
    for (const sale of tables.sales) {
      if (
        new Date(sale.created_at).toISOString() !== sale.created_at ||
        financialYear(sale.created_at) !== sale.fy
      )
        throw new Error("Invalid bill date or series");
      const identity = validateSettings(JSON.parse(sale.identity));
      if (Number(identity.tax_inclusive) !== sale.tax_inclusive)
        throw new Error("Saved GST price basis does not match its identity snapshot");
      if (
        sale.bill_number !==
        billNumber(identity.series, sale.fy, sale.sequence_number)
      )
        throw new Error("Invalid final bill number");
      const lines = tables.sale_lines
        .filter((l) => l.sale_id === sale.id)
        .sort((a, b) => a.position - b.position);
      if (lines.some((l, i) => l.position !== i))
        throw new Error("Invalid item order");
      const q = quote(lines, sale.discount_paise, {
        receipt_mode: sale.mode,
        tax_bps: sale.tax_bps,
        tax_inclusive: sale.tax_inclusive,
        round_rupee: Boolean(sale.round_rupee),
      });
      for (const key of [
        "gross_paise",
        "discount_paise",
        "tax_paise",
        "round_paise",
        "total_paise",
      ])
        if (q[key] !== sale[key])
          throw new Error("Bill totals do not reconcile");
      for (const [i, line] of q.lines.entries())
        for (const key of [
          "gross_paise",
          "discount_paise",
          "net_paise",
          "tax_inclusive",
          "tax_paise",
          "taxable_paise",
          "cgst_paise",
          "sgst_paise",
        ])
          if (line[key] !== lines[i][key])
            throw new Error("Item totals do not reconcile");
      const paid = tables.payments
        .filter((p) => p.sale_id === sale.id)
        .sort((a, b) => a.position - b.position);
      const validated = payments(sale.total_paise, paid);
      if (
        paid.some(
          (p, i) =>
            p.position !== i ||
            ["method", "amount_paise", "tendered_paise", "change_paise"].some(
              (key) => p[key] !== validated[i][key],
            ),
        )
      )
        throw new Error("Payment does not reconcile");
      const seq = tables.sequences.find((s) => s.fy === sale.fy);
      if (!seq || seq.last_number < sale.sequence_number)
        throw new Error("Bill sequence would reuse a number");
      const adjustments = tables.adjustments.filter(
        (a) => a.sale_id === sale.id,
      );
      if (
        adjustments.reduce((n, a) => n + a.amount_paise, 0) >
          sale.total_paise ||
        adjustments.some(
          (a) =>
            !a.reason.trim() ||
            new Date(a.created_at).toISOString() !== a.created_at ||
            a.created_at < sale.created_at,
        ) ||
        (adjustments.some((a) => a.kind === "void") &&
          (adjustments.length !== 1 ||
            adjustments[0].amount_paise !== sale.total_paise))
      )
        throw new Error("Invalid correction history");
      for (const a of adjustments) {
        const refunds = tables.adjustment_payments.filter(
          (p) => p.adjustment_id === a.id,
        );
        payments(a.amount_paise, refunds);
      }
    }
    for (const draft of tables.drafts) {
      const value = JSON.parse(draft.value);
      if (draft.id.startsWith("local:product-menu:")) validateMenuType(value);
    }
    return data;
  } finally {
    await db.close();
  }
}

export async function restoreBackup(source, ledger, images, makeDatabase) {
  const data = await inspectBackup(source, makeDatabase);
  // Restoring a pre-login backup must not remove the current owner's access lock.
  const owner = await ledger.localSetting(ACCESS_KEY);
  if (owner && !data.tables.drafts.some((row) => row.id === `local:${ACCESS_KEY}`))
    data.tables.drafts.push({ id: `local:${ACCESS_KEY}`, value: JSON.stringify(owner) });
  // Immutable images are staged first. Failed validation/DB writes leave current data intact.
  for (const content of Object.values(data.files)) await images.put(content);
  await ledger.replace(data.tables);
  return data;
}

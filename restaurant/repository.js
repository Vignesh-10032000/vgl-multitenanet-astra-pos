import { SCHEMA, TABLES, VERSION, PAYMENT_SCHEMA, migrateGstPricing } from "./schema.js";
import {
  billNumber,
  dateBounds,
  financialYear,
  integer,
  operationId,
  payment,
  payments,
  quote,
  text,
} from "./domain.js";

/** Serialize reads and writes across async bridge calls. No query can see half a checkout. */
export class Ledger {
  #tail = Promise.resolve();
  constructor(
    db,
    { now = () => new Date().toISOString(), uuid = operationId } = {},
  ) {
    this.db = db;
    this.now = now;
    this.uuid = uuid;
  }
  exclusive(fn) {
    const work = this.#tail.then(fn);
    this.#tail = work.catch(() => {});
    return work;
  }
  async transaction(fn) {
    return this.exclusive(async () => {
      await this.db.begin();
      try {
        const result = await fn();
        await this.db.commit();
        return result;
      } catch (error) {
        await this.db.rollback();
        throw error;
      }
    });
  }
  async initialize(menu, defaults) {
    await this.db.exec("PRAGMA foreign_keys=ON;");
    await this.transaction(async () => {
      await this.db.exec(SCHEMA);
      const versions = await this.db.query(
        "SELECT version FROM schema_versions",
      );
      if (versions.some((v) => v.version > VERSION))
        throw new Error("Database belongs to a newer app version");
      if (versions.length && versions.every((v) => v.version < 2)) {
        // Version 1 allowed one tender per bill. Preserve every stored amount,
        // request and snapshot while making room for a second payment row.
        await this.db.exec("ALTER TABLE payments RENAME TO legacy_payments;");
        await this.db.exec(PAYMENT_SCHEMA);
        await this.db.exec(
          "INSERT INTO payments SELECT sale_id,0,method,amount_paise,tendered_paise,change_paise FROM legacy_payments;",
        );
        await this.db.exec(
          "INSERT INTO adjustment_payments SELECT a.id,p.method,a.amount_paise FROM adjustments a JOIN legacy_payments p ON p.sale_id=a.sale_id;",
        );
        await this.db.exec(
          "DROP TABLE legacy_payments; DELETE FROM schema_versions;",
        );
      }
      if (versions.length && versions.every(v => v.version < 3)) {
        await migrateGstPricing(this.db);
        await this.db.exec("DELETE FROM schema_versions;");
        await this.db.run("INSERT INTO schema_versions VALUES(?)", [VERSION]);
      }
      if (!versions.length) {
        await this.db.run("INSERT INTO schema_versions VALUES(?)", [VERSION]);
        await this.db.run("INSERT INTO settings VALUES(?,?)", [
          "store",
          JSON.stringify(defaults),
        ]);
        for (const item of menu)
          await this.insert("products", {
            id: item.reference_id,
            name: item.source_label,
            portion: item.portion_label,
            category: item.category,
            price_paise: item.price_paise,
            image: null,
            active: 1,
          });
      } else if (defaults.gst_setup_revision && defaults.tax_confirmed) {
        const current = await this._settings();
        if (!current.gst_setup_revision) {
          // Apply the owner's confirmed setup only to the original untouched training
          // tax configuration. Keep store edits and every issued bill snapshot intact.
          const wasInitialTaxSetup =
            current.receipt_mode === "training" &&
            !current.gstin &&
            !current.tax_confirmed &&
            current.tax_bps === 0;
          const value = wasInitialTaxSetup
            ? {
                ...current,
                gstin: defaults.gstin,
                receipt_mode: defaults.receipt_mode,
                tax_bps: defaults.tax_bps,
                tax_confirmed: true,
                gst_confirmation_source: defaults.gst_confirmation_source,
                gst_setup_revision: defaults.gst_setup_revision,
              }
            : { ...current, gst_setup_revision: defaults.gst_setup_revision };
          await this.db.run("UPDATE settings SET value=? WHERE id='store'", [
            JSON.stringify(value),
          ]);
        }
      }
      if (versions.length && defaults.gst_pricing_revision) {
        const current = await this._settings();
        if (!current.gst_pricing_revision) {
          await this.db.run("UPDATE settings SET value=? WHERE id='store'", [JSON.stringify({
            ...current,
            tax_inclusive: defaults.tax_inclusive,
            gst_pricing_revision: defaults.gst_pricing_revision,
            gst_confirmation_source: defaults.gst_confirmation_source,
          })]);
        }
      }
    });
  }
  localSetting(id) {
    return this.transaction(async () => {
      const row = (await this.db.query("SELECT value FROM drafts WHERE id=?", [`local:${id}`]))[0];
      return row ? JSON.parse(row.value) : null;
    });
  }
  saveLocalSetting(id, value, createOnly = false) {
    if (!id || id === "store") throw new Error("Invalid local setting");
    return this.transaction(() => this.db.run(
      `${createOnly ? "INSERT" : "INSERT OR REPLACE"} INTO drafts(id,value) VALUES(?,?)`,
      [`local:${id}`, JSON.stringify(value)],
    ));
  }
  async insert(table, record) {
    const columns = TABLES[table];
    if (!columns) throw new Error("Invalid table");
    await this.db.run(
      `INSERT INTO ${table}(${columns.join(",")}) VALUES(${columns.map(() => "?").join(",")})`,
      columns.map((c) => record[c] ?? null),
    );
  }
  installProductPhotos(key, changes) {
    return this.transaction(async () => {
      const id = `local:${text(key, "Photo update", true, 80)}`;
      if ((await this.db.query("SELECT id FROM drafts WHERE id=?", [id])).length) return 0;
      const installed = [];
      for (const change of changes) {
        validateImagePath(change.image);
        if (!change.image) throw new Error("Menu photo is missing");
        const previous = change.previous_image ?? null;
        validateImagePath(previous);
        const product = (await this.db.query("SELECT * FROM products WHERE id=?", [change.id]))[0];
        // Recheck after file preparation: edits/uploads made meanwhile always win.
        if (!product || product.image !== previous || product.name !== change.name || product.portion !== change.portion) continue;
        await this.db.run("UPDATE products SET image=? WHERE id=? AND image IS ?", [change.image, change.id, previous]);
        installed.push({id: change.id, image: change.image});
      }
      await this.db.run("INSERT INTO drafts(id,value) VALUES(?,?)", [id, JSON.stringify({kind:"illustrative-menu-photos", installed, created_at:this.now()})]);
      return installed.length;
    });
  }
  installBrandLogo(key, image) {
    return this.transaction(async () => {
      const id = `local:${text(key, "Brand update", true, 80)}`;
      if ((await this.db.query("SELECT id FROM drafts WHERE id=?", [id])).length) return false;
      const settings = await this._settings();
      validateImagePath(image);
      const installed = Boolean(image && !settings.logo && settings.menu_logo);
      if (installed) {
        settings.logo = image;
        settings.menu_logo = false;
        await this.db.run("UPDATE settings SET value=? WHERE id='store'", [JSON.stringify(settings)]);
      }
      await this.db.run("INSERT INTO drafts(id,value) VALUES(?,?)", [id,
        JSON.stringify({ kind: "owner-brand-logo", image: installed ? image : null, created_at: this.now() })]);
      return installed;
    });
  }
  async _settings() {
    return JSON.parse(
      (await this.db.query("SELECT value FROM settings WHERE id='store'"))[0]
        .value,
    );
  }
  settings() {
    return this.exclusive(() => this._settings());
  }
  saveSettings(value) {
    return this.transaction(async () => {
      const settings = validateSettings(value);
      await this.db.run("UPDATE settings SET value=? WHERE id='store'", [
        JSON.stringify(settings),
      ]);
      return settings;
    });
  }
  products() {
    return this.exclusive(() =>
      this.db.query("SELECT * FROM products ORDER BY category,name,portion"),
    );
  }
  saveProduct(input) {
    return this.transaction(async () => {
      const p = {
        id: input.id || this.uuid(),
        name: text(input.name, "Name", true),
        portion: text(input.portion, "Portion", true, 80),
        category: text(input.category, "Category", true, 80),
        price_paise: integer(input.price_paise, "Price", 1),
        image: input.image || null,
        active: input.active ? 1 : 0,
      };
      validateImagePath(p.image);
      await this.db.run(
        "INSERT INTO products VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,portion=excluded.portion,category=excluded.category,price_paise=excluded.price_paise,image=excluded.image,active=excluded.active",
        Object.values(p),
      );
      return p;
    });
  }
  customers() {
    return this.exclusive(() =>
      this.db.query("SELECT * FROM customers ORDER BY name"),
    );
  }
  saveCustomer(input) {
    return this.transaction(async () => {
      const c = {
        id: input.id || this.uuid(),
        name: text(input.name, "Name", true),
        phone: text(input.phone, "Phone", false, 30),
        city: text(input.city, "City", false, 100),
      };
      await this.db.run(
        "INSERT INTO customers VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,phone=excluded.phone,city=excluded.city",
        Object.values(c),
      );
      return c;
    });
  }
  draft() {
    return this.exclusive(async () =>
      JSON.parse(
        (await this.db.query("SELECT value FROM drafts WHERE id='cart'"))[0]
          ?.value || "null",
      ),
    );
  }
  saveDraft(value) {
    return this.transaction(() =>
      this.db.run("INSERT OR REPLACE INTO drafts VALUES('cart',?)", [
        JSON.stringify(value),
      ]),
    );
  }

  billingPreference(key) {
    return this.exclusive(async () =>
      JSON.parse(
        (
          await this.db.query("SELECT value FROM drafts WHERE id=?", [
            `preference:${key}`,
          ])
        )[0]?.value || "null",
      ),
    );
  }

  saveBillingPreference(key, value) {
    return this.transaction(() =>
      this.db.run("INSERT OR REPLACE INTO drafts VALUES(?,?)", [
        `preference:${key}`,
        JSON.stringify(value),
      ]),
    );
  }

  holdCart(cart, label) {
    return this.transaction(async () => {
      if (!cart.cart?.length) throw new Error("Nothing to hold");
      const id = `hold:${this.uuid()}`;
      await this.db.run("INSERT INTO drafts VALUES(?,?)", [
        id,
        JSON.stringify({
          ...cart,
          label: text(label, "Label", false, 100),
          created_at: this.now(),
        }),
      ]);
      await this.db.run("DELETE FROM drafts WHERE id='cart'");
      return id;
    });
  }

  heldBills() {
    return this.exclusive(async () =>
      (
        await this.db.query(
          "SELECT id,value FROM drafts WHERE id LIKE 'hold:%' ORDER BY id",
        )
      ).map((row) => ({
        ...JSON.parse(row.value),
        id: row.id,
        item_count: JSON.parse(row.value).cart.length,
      })),
    );
  }

  recallHeldBill(id) {
    return this.transaction(async () => {
      if (!String(id).startsWith("hold:")) throw new Error("Invalid held bill");
      const active = JSON.parse(
        (await this.db.query("SELECT value FROM drafts WHERE id='cart'"))[0]
          ?.value || "null",
      );
      if (active?.items?.length || active?.originalCart?.length)
        throw new Error(
          "Hold or clear the active cart before recalling another bill",
        );
      const value = (
        await this.db.query("SELECT value FROM drafts WHERE id=?", [id])
      )[0]?.value;
      if (!value) throw new Error("Held bill no longer exists");
      const cart = JSON.parse(value);
      // Recall and durable active-cart replacement happen together, before removing the hold.
      await this.db.run("INSERT OR REPLACE INTO drafts VALUES('cart',?)", [
        JSON.stringify({
          originalCart: cart.cart,
          operation: cart.saleUuid,
          discount: cart.orderDiscount,
          customer_id: cart.customerId,
        }),
      ]);
      await this.db.run("DELETE FROM drafts WHERE id=?", [id]);
      return cart;
    });
  }

  discardHeldBill(id) {
    if (!String(id).startsWith("hold:"))
      return Promise.reject(new Error("Invalid held bill"));
    return this.transaction(() =>
      this.db.run("DELETE FROM drafts WHERE id=?", [id]),
    );
  }
  async _sale(id) {
    const sale = (
      await this.db.query("SELECT * FROM sales WHERE id=?", [id])
    )[0];
    if (!sale) throw new Error("Bill not found");
    const tenders = await this.db.query(
      "SELECT * FROM payments WHERE sale_id=? ORDER BY position",
      [id],
    );
    return {
      ...sale,
      customer: JSON.parse(sale.customer),
      identity: JSON.parse(sale.identity),
      lines: await this.db.query(
        "SELECT * FROM sale_lines WHERE sale_id=? ORDER BY position",
        [id],
      ),
      payments: tenders,
      payment:
        tenders.length === 1
          ? tenders[0]
          : {
              method: "split",
              amount_paise: sale.total_paise,
              tendered_paise: tenders.reduce((n, p) => n + p.tendered_paise, 0),
              change_paise: tenders.reduce((n, p) => n + p.change_paise, 0),
            },
      adjustments: await this.db.query(
        "SELECT * FROM adjustments WHERE sale_id=? ORDER BY created_at",
        [id],
      ),
    };
  }
  sale(id) {
    return this.exclusive(() => this._sale(id));
  }
  checkout(input) {
    return this.transaction(async () => {
      const op = text(input.operation_id, "Operation identifier", true, 100);
      const request = JSON.stringify({
        items: input.items,
        discount_paise: input.discount_paise ?? 0,
        method: input.method,
        tendered_paise: input.tendered_paise ?? null,
        customer_id: input.customer_id || null,
        ...(input.payments ? { payments: input.payments } : {}),
      });
      const previous = (
        await this.db.query(
          "SELECT id,request FROM sales WHERE operation_id=?",
          [op],
        )
      )[0];
      if (previous) {
        if (previous.request !== request)
          throw new Error(
            "This operation already saved a different bill; open Sales",
          );
        return this._sale(previous.id);
      }
      const settings = await this._settings();
      const items = [];
      if (!Array.isArray(input.items) || input.items.length > 200)
        throw new Error("Invalid cart");
      const seen = new Set();
      for (const item of input.items) {
        if (seen.has(item.product_id)) throw new Error("Duplicate menu line");
        seen.add(item.product_id);
        const p = (
          await this.db.query(
            "SELECT * FROM products WHERE id=? AND active=1",
            [item.product_id],
          )
        )[0];
        if (!p)
          throw new Error(
            "A menu item is inactive or missing. Review this cart.",
          );
        if (
          p.price_paise !== item.unit_paise ||
          p.name !== item.name ||
          p.portion !== item.portion
        )
          throw new Error("Menu changed. Review this cart before paying.");
        items.push({
          product_id: p.id,
          name: p.name,
          portion: p.portion,
          quantity: item.quantity,
          unit_paise: p.price_paise,
        });
      }
      const q = quote(items, input.discount_paise ?? 0, settings);
      const tenders = input.payments
        ? payments(q.total_paise, input.payments)
        : [payment(q.total_paise, input.method, input.tendered_paise)];
      let customer = null;
      if (input.customer_id) {
        customer = (
          await this.db.query("SELECT * FROM customers WHERE id=?", [
            input.customer_id,
          ])
        )[0];
        if (!customer) throw new Error("Customer no longer exists");
      }
      const created_at = this.now();
      const fy = financialYear(created_at);
      await this.db.run(
        "INSERT INTO sequences VALUES(?,1) ON CONFLICT(fy) DO UPDATE SET last_number=last_number+1",
        [fy],
      );
      const seq = (
        await this.db.query("SELECT last_number FROM sequences WHERE fy=?", [
          fy,
        ])
      )[0].last_number;
      const sale = {
        id: this.uuid(),
        operation_id: op,
        request,
        bill_number: billNumber(settings.series, fy, seq),
        fy,
        sequence_number: seq,
        created_at,
        customer: JSON.stringify(customer),
        identity: JSON.stringify(settings),
        mode: settings.receipt_mode,
        tax_bps: settings.tax_bps,
        round_rupee: settings.round_rupee ? 1 : 0,
        ...q,
      };
      await this.insert("sales", sale);
      for (const [position, line] of q.lines.entries())
        await this.insert("sale_lines", {
          ...line,
          sale_id: sale.id,
          position,
        });
      for (const [position, tender] of tenders.entries())
        await this.insert("payments", {
          sale_id: sale.id,
          position,
          ...tender,
        });
      await this.db.run("DELETE FROM drafts WHERE id='cart'");
      return this._sale(sale.id);
    });
  }
  adjust({ sale_id, kind, amount_paise, reason, operation_id, refunds }) {
    return this.transaction(async () => {
      text(operation_id, "Operation identifier", true, 100);
      const prior = (
        await this.db.query("SELECT * FROM adjustments WHERE operation_id=?", [
          operation_id,
        ])
      )[0];
      reason = text(reason, "Reason", true, 500);
      if (prior) {
        if (
          prior.sale_id !== sale_id ||
          prior.kind !== kind ||
          prior.amount_paise !== amount_paise ||
          prior.reason !== reason
        )
          throw new Error("Adjustment identifier already used");
        if (refunds) {
          const saved = await this.db.query(
            "SELECT method,amount_paise FROM adjustment_payments WHERE adjustment_id=? ORDER BY method",
            [prior.id],
          );
          const requested = payments(amount_paise, refunds)
            .map(({ method, amount_paise }) => ({ method, amount_paise }))
            .sort((a, b) => a.method.localeCompare(b.method));
          if (JSON.stringify(saved) !== JSON.stringify(requested))
            throw new Error("Adjustment identifier already used");
        }
        return prior;
      }
      const sale = await this._sale(sale_id);
      const already = sale.adjustments.reduce((n, a) => n + a.amount_paise, 0);
      if (!["void", "refund"].includes(kind))
        throw new Error("Invalid correction");
      if (
        sale.adjustments.some((a) => a.kind === "void") ||
        (kind === "void" && sale.adjustments.length)
      )
        throw new Error("Cannot void a corrected bill");
      integer(
        amount_paise,
        "Correction amount",
        kind === "void" ? 0 : 1,
        sale.total_paise - already,
      );
      if (kind === "void" && amount_paise !== sale.total_paise)
        throw new Error("Void must cover the entire bill");
      if (!refunds && sale.payments.length > 1 && kind !== "void")
        throw new Error("Enter the actual Cash and GPay return amounts");
      const returns = payments(
        amount_paise,
        refunds ||
          (kind === "void"
            ? sale.payments.map((p) => ({
                method: p.method,
                amount_paise: p.amount_paise,
              }))
            : [{ method: sale.payments[0].method, amount_paise }]),
      );
      const a = {
        id: this.uuid(),
        operation_id,
        sale_id,
        kind,
        amount_paise,
        reason,
        created_at: this.now(),
      };
      await this.insert("adjustments", a);
      for (const refund of returns)
        await this.insert("adjustment_payments", {
          adjustment_id: a.id,
          method: refund.method,
          amount_paise: refund.amount_paise,
        });
      return a;
    });
  }
  printAttempt(sale_id, state = "requested", detail = "", id = this.uuid()) {
    return this.transaction(async () => {
      const old = (
        await this.db.query("SELECT id FROM print_attempts WHERE id=?", [id])
      )[0];
      if (old)
        await this.db.run(
          "UPDATE print_attempts SET state=?,detail=? WHERE id=?",
          [state, text(detail, "Print detail", false, 500), id],
        );
      else
        await this.insert("print_attempts", {
          id,
          sale_id,
          created_at: this.now(),
          state,
          detail,
        });
      return id;
    });
  }
  /** Event-date accounting: corrections appear when recorded, including earlier-month bills. */
  report({ from, to, method = "all", search = "" }) {
    return this.transaction(async () => {
      const [start, end] = dateBounds(from, to);
      if (!["all", "cash", "upi"].includes(method))
        throw new Error("Invalid payment filter");
      const needle = text(search, "Search", false, 160).toLocaleLowerCase();
      const saleClause =
        method === "all"
          ? ""
          : " AND EXISTS(SELECT 1 FROM payments fp WHERE fp.sale_id=s.id AND fp.method=?)";
      const returnClause =
        method === "all"
          ? ""
          : " AND EXISTS(SELECT 1 FROM adjustment_payments fp WHERE fp.adjustment_id=a.id AND fp.method=?)";
      const args = method === "all" ? [start, end] : [start, end, method];
      let invoices = await this.db.query(
        `SELECT s.*,COALESCE((SELECT SUM(amount_paise) FROM adjustments a WHERE a.sale_id=s.id),0) AS corrected_paise,(SELECT COUNT(*) FROM adjustments a WHERE a.sale_id=s.id) AS correction_count,EXISTS(SELECT 1 FROM adjustments a WHERE a.sale_id=s.id AND a.kind='void') AS has_void FROM sales s WHERE s.created_at>=? AND s.created_at<?${saleClause} ORDER BY s.created_at,s.bill_number`,
        args,
      );
      const tenders = await this.db.query(
        `SELECT p.* FROM payments p JOIN sales s ON s.id=p.sale_id WHERE s.created_at>=? AND s.created_at<?${saleClause} ORDER BY s.created_at,p.position`,
        args,
      );
      let lines = await this.db.query(
        `SELECT l.*,s.bill_number,s.created_at FROM sale_lines l JOIN sales s ON s.id=l.sale_id WHERE s.created_at>=? AND s.created_at<?${saleClause} ORDER BY s.created_at,l.position`,
        args,
      );
      let adjustments = await this.db.query(
        `SELECT a.*,s.bill_number,s.created_at AS original_date,s.customer FROM adjustments a JOIN sales s ON s.id=a.sale_id WHERE a.created_at>=? AND a.created_at<?${returnClause} ORDER BY a.created_at,a.id`,
        args,
      );
      const returns = await this.db.query(
        `SELECT p.* FROM adjustment_payments p JOIN adjustments a ON a.id=p.adjustment_id WHERE a.created_at>=? AND a.created_at<?${returnClause} ORDER BY a.created_at,p.method`,
        args,
      );
      let prints = await this.db.query(
        `SELECT r.*,s.bill_number,s.customer FROM print_attempts r JOIN sales s ON s.id=r.sale_id WHERE r.created_at>=? AND r.created_at<?${saleClause} ORDER BY r.created_at`,
        args,
      );
      const matches = (row) =>
        !needle ||
        [
          row.bill_number,
          JSON.parse(row.customer)?.name,
          JSON.parse(row.customer)?.phone,
        ].some((v) =>
          String(v || "")
            .toLocaleLowerCase()
            .includes(needle),
        );
      invoices = invoices.filter(matches);
      adjustments = adjustments.filter(matches);
      prints = prints.filter(matches);
      const invoiceIds = new Set(invoices.map((s) => s.id));
      lines = lines.filter((l) => invoiceIds.has(l.sale_id));
      const selectedPayments = tenders.filter((p) => invoiceIds.has(p.sale_id));
      const annotate = (row, rows) => {
        row.method = rows.length > 1 ? "split" : rows[0]?.method;
        row.cash_paise = rows
          .filter((p) => p.method === "cash")
          .reduce((n, p) => n + p.amount_paise, 0);
        row.upi_paise = rows
          .filter((p) => p.method === "upi")
          .reduce((n, p) => n + p.amount_paise, 0);
        row.cash_included_paise = method === "upi" ? 0 : row.cash_paise;
        row.upi_included_paise = method === "cash" ? 0 : row.upi_paise;
        row.matched_paise = row.cash_included_paise + row.upi_included_paise;
      };
      for (const sale of invoices) {
        const paid = selectedPayments.filter((p) => p.sale_id === sale.id);
        annotate(sale, paid);
        sale.tendered_paise = paid.reduce((n, p) => n + p.tendered_paise, 0);
        sale.change_paise = paid.reduce((n, p) => n + p.change_paise, 0);
        const saleLines = lines.filter((l) => l.sale_id === sale.id);
        const weight = saleLines.reduce((n, l) => n + l.net_paise, 0);
        let cumulative = 0,
          distributed = 0;
        for (const line of saleLines) {
          cumulative += line.net_paise;
          const allocation = weight
            ? Number(
                (BigInt(sale.matched_paise) * BigInt(cumulative)) /
                  BigInt(weight),
              )
            : 0;
          line.matched_paise = allocation - distributed;
          line.method = sale.method;
          line.has_void = sale.has_void;
          distributed = allocation;
        }
      }
      for (const adjustment of adjustments)
        annotate(
          adjustment,
          returns.filter((p) => p.adjustment_id === adjustment.id),
        );
      const result = {
        from,
        to,
        method,
        search,
        invoices,
        lines,
        adjustments,
        prints,
        payments: selectedPayments,
      };
      return { ...result, ...summarize(result) };
    });
  }
  snapshot() {
    return this.transaction(async () => {
      const tables = {};
      for (const name of Object.keys(TABLES))
        tables[name] = await this.db.query(`SELECT * FROM ${name}`);
      return tables;
    });
  }
  replace(tables) {
    return this.transaction(async () => {
      for (const name of Object.keys(TABLES).reverse())
        await this.db.run(`DELETE FROM ${name}`);
      for (const name of Object.keys(TABLES))
        for (const row of tables[name]) await this.insert(name, row);
      if ((await this.db.query("PRAGMA foreign_key_check")).length)
        throw new Error("Backup references are invalid");
    });
  }
}

export function validateImagePath(path) {
  if (path !== null && !/^images\/[a-f0-9]{64}\.jpg$/.test(path))
    throw new Error("Invalid image path");
}
export function validateSettings(value) {
  const s = {
    ...value,
    name: text(value.name, "Restaurant name", true),
    address: text(value.address, "Address", false, 350),
    phone: text(value.phone, "Phone", false, 35),
    gstin: text(value.gstin, "GSTIN", false, 15).toUpperCase(),
    series: text(value.series, "Bill series", true, 4).toUpperCase(),
    cashier: text(value.cashier, "Cashier", true, 80),
    footer: text(value.footer, "Footer", false, 250),
    upi_id: text(value.upi_id, "UPI ID", false, 120),
    upi_payee: text(value.upi_payee, "UPI payee", false, 120),
  };
  if (!/^[A-Z0-9]{1,4}$/.test(s.series))
    throw new Error("Series: use 1–4 letters/numbers");
  if (!["training", "bill_of_supply", "tax_invoice"].includes(s.receipt_mode))
    throw new Error("Invalid receipt mode");
  s.tax_bps =
    s.receipt_mode === "tax_invoice"
      ? integer(value.tax_bps, "GST rate", 1, 2800)
      : 0;
  s.round_rupee = Boolean(value.round_rupee);
  if (value.tax_inclusive !== undefined && typeof value.tax_inclusive !== "boolean")
    throw new Error("Choose whether menu prices include GST");
  s.tax_inclusive = value.tax_inclusive ?? true;
  if (s.receipt_mode !== "training" && !value.tax_confirmed)
    throw new Error(
      "Confirm current tax status with your accountant before live billing",
    );
  if (s.receipt_mode !== "training" && !/^[0-9]{2}[A-Z0-9]{13}$/.test(s.gstin))
    throw new Error("Enter the confirmed GSTIN");
  if (
    s.upi_id &&
    (!/^[\w.-]+@[\w.-]+$/.test(s.upi_id) || !s.upi_payee || !s.upi_confirmed)
  )
    throw new Error("Enter and confirm your merchant UPI ID and payee");
  s.logo = s.logo || null;
  validateImagePath(s.logo);
  s.receipt_font = value.receipt_font === "mono" ? "mono" : "sans";
  s.menu_logo = Boolean(value.menu_logo);
  return s;
}

export function summarize({ invoices, adjustments, lines, method = "all" }) {
  const sum = (rows, field) => integer(rows.reduce((n, r) => n + r[field], 0));
  const gross = sum(invoices, "matched_paise"),
    corrections = sum(adjustments, "matched_paise");
  const cash =
    sum(invoices, "cash_included_paise") -
    sum(adjustments, "cash_included_paise");
  const upi =
    sum(invoices, "upi_included_paise") -
    sum(adjustments, "upi_included_paise");
  if (cash + upi !== gross - corrections)
    throw new Error("Payment totals do not reconcile");
  const daily = new Map();
  for (const [rows, sign] of [
    [invoices, 1],
    [adjustments, -1],
  ])
    for (const row of rows) {
      const day = new Date(new Date(row.created_at).getTime() + 19800000)
        .toISOString()
        .slice(0, 10);
      const entry = daily.get(day) || {
        day,
        bills: 0,
        sales_paise: 0,
        corrections_paise: 0,
        net_paise: 0,
      };
      if (sign === 1) {
        entry.bills++;
        entry.sales_paise += row.matched_paise;
      } else entry.corrections_paise += row.matched_paise;
      entry.net_paise += sign * row.matched_paise;
      daily.set(day, entry);
    }
  const groupItems = (rows) => {
    const grouped = new Map();
    for (const l of rows) {
      const key = JSON.stringify([
        l.product_id,
        l.name,
        l.portion,
        l.unit_paise,
      ]);
      const item = grouped.get(key) || {
        name: l.name,
        portion: l.portion,
        quantity: 0,
        net_paise: 0,
        matched_paise: 0,
      };
      item.quantity += l.quantity;
      item.net_paise += l.net_paise;
      item.matched_paise += l.matched_paise;
      grouped.set(key, item);
    }
    return [...grouped.values()];
  };
  return {
    totals: {
      bills: invoices.length,
      sales_paise: gross,
      corrections_paise: corrections,
      net_paise: gross - corrections,
      cash_paise: cash,
      upi_paise: upi,
      discount_paise: sum(invoices, "discount_paise"),
      round_paise: invoices.reduce((n, r) => n + r.round_paise, 0),
      void_paise: sum(
        adjustments.filter((a) => a.kind === "void"),
        "matched_paise",
      ),
      refund_paise: sum(
        adjustments.filter((a) => a.kind === "refund"),
        "matched_paise",
      ),
    },
    daily: [...daily.values()].sort((a, b) => a.day.localeCompare(b.day)),
    items: groupItems(lines),
    top_items: groupItems(lines.filter((l) => !l.has_void))
      .sort(
        (a, b) => b.quantity - a.quantity || b.matched_paise - a.matched_paise,
      )
      .slice(0, 5),
    payment_totals: ["cash", "upi"]
      .filter((m) => method === "all" || method === m)
      .map((m) => ({
        method: m,
        bills: invoices.filter((s) => s[`${m}_paise`] > 0).length,
        received_paise: sum(invoices, `${m}_paise`),
        returned_paise: sum(adjustments, `${m}_paise`),
        net_paise: m === "cash" ? cash : upi,
      })),
  };
}

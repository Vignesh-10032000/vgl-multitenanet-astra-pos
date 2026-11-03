import { metricText, metricHeader } from "./labels.js";
import { decimal, percent } from "./domain.js";
import { saveFile } from "./documents.js";

/** A leading apostrophe protects text in both CSV and XLSX without evaluating formulas. */
export function spreadsheetText(value) {
  const s = String(value ?? "");
  return /^[\s\uFEFF]*[=+\-@]/.test(s) || /^[\t\r\n]/.test(s) ? `'${s}` : s;
}
export function datasets(r) {
  const fmt = decimal;
  const summaryMoneyLabels = Object.keys(r.totals).filter((key) => key.endsWith("_paise")).map(metricText);
  return [
    {
      name: "Invoices",
      columns: [
        "Bill",
        "Timestamp UTC",
        "Customer",
        "Phone",
        "City",
        "Lines",
        "Gross INR",
        "Discount INR",
        "GST INR",
        "Round INR",
        "Total INR",
        "Receipt mode",
        "Payment",
        "Status",
        "Tendered INR",
        "Change INR",
        "Store GSTIN",
        "Taxable INR",
        "CGST %",
        "CGST INR",
        "SGST %",
        "SGST INR",
        "Cash paid INR",
        "GPay paid INR",
        "Selected payment INR",
        "GST price basis",
      ],
      rows: r.invoices.map((s) => {
        const c = JSON.parse(s.customer);
        const lines = r.lines.filter((line) => line.sale_id === s.id);
        const rate = s.mode === "tax_invoice" ? percent(s.tax_bps, 2) : "0";
        return [
          s.bill_number,
          s.created_at,
          c?.name || "Walk-in",
          c?.phone || "",
          c?.city || "",
          lines.length,
          fmt(s.gross_paise),
          fmt(s.discount_paise),
          fmt(s.tax_paise),
          fmt(s.round_paise),
          fmt(s.total_paise),
          s.mode,
          s.method,
          s.correction_count ? "Correction recorded" : "Saved",
          fmt(s.tendered_paise),
          fmt(s.change_paise),
          JSON.parse(s.identity).gstin || "",
          fmt(lines.reduce((n, l) => n + l.taxable_paise, 0)),
          rate,
          fmt(lines.reduce((n, l) => n + l.cgst_paise, 0)),
          rate,
          fmt(lines.reduce((n, l) => n + l.sgst_paise, 0)),
          fmt(s.cash_paise),
          fmt(s.upi_paise),
          fmt(s.matched_paise),
          s.tax_inclusive === 0 ? "Added to menu price" : "Included in menu price",
        ];
      }),
    },
    {
      name: "Payments",
      columns: ["Bill", "Timestamp UTC", "Method", "Amount INR", "Tendered INR", "Change INR", "Included in filter"],
      rows: (r.payments || []).map((p) => {
        const sale = r.invoices.find((s) => s.id === p.sale_id);
        return [sale.bill_number, sale.created_at, p.method, fmt(p.amount_paise), fmt(p.tendered_paise), fmt(p.change_paise), r.method === "all" || r.method === p.method ? "Yes" : "No"];
      }),
    },
    {
      name: "Items",
      columns: [
        "Bill",
        "Timestamp UTC",
        "Product",
        "Portion",
        "Quantity",
        "Unit INR",
        "Gross INR",
        "Discount INR",
        "Taxable INR",
        "CGST INR",
        "SGST INR",
        "Total INR",
        "Payment",
        "Selected payment INR",
      ],
      rows: r.lines.map((l) => [
        l.bill_number,
        l.created_at,
        l.name,
        l.portion,
        l.quantity,
        fmt(l.unit_paise),
        fmt(l.gross_paise),
        fmt(l.discount_paise),
        fmt(l.taxable_paise),
        fmt(l.cgst_paise),
        fmt(l.sgst_paise),
        fmt(l.net_paise),
        l.method,
        fmt(l.matched_paise),
      ]),
    },
    {
      name: "Summary",
      moneyLabels: summaryMoneyLabels,
      columns: ["Metric", "Value"],
      rows: [
        ["From (Asia/Kolkata)", r.from],
        ["To inclusive (Asia/Kolkata)", r.to],
        ["Payment filter", r.method],
        ["Correction basis", "Recorded event date; can refer to earlier bills"],
        ...Object.entries(r.totals).map(([k, v]) => [
          metricText(k),
          k.endsWith("_paise") ? fmt(v) : v,
        ]),
        [
          "Item amounts",
          "Original invoiced quantities and amounts; see Corrections for returns",
        ],
        ["Selected item payment", "Payment share allocated across bill items, including round-off. Subtract selected Corrections for Final Sales."],
        ["UPI", "Cashier recorded; not gateway confirmed"],
      ],
    },
    {
      name: "Daily",
      columns: [
        "Date Asia/Kolkata",
        metricHeader("bills"),
        metricHeader("sales_paise"),
        metricHeader("corrections_paise"),
        metricHeader("net_paise"),
      ],
      rows: r.daily.map((d) => [
        d.day,
        d.bills,
        fmt(d.sales_paise),
        fmt(d.corrections_paise),
        fmt(d.net_paise),
      ]),
    },
    {
      name: "Monthly",
      columns: [
        "Month Asia/Kolkata",
        metricHeader("bills"),
        metricHeader("sales_paise"),
        metricHeader("corrections_paise"),
        metricHeader("net_paise"),
      ],
      rows: monthly(r.daily).map((d) => [
        d.month,
        d.bills,
        fmt(d.sales_paise),
        fmt(d.corrections_paise),
        fmt(d.net_paise),
      ]),
    },
    {
      name: "Item sales",
      columns: [
        "Product snapshot",
        "Portion",
        "Original quantity",
        "Invoiced net INR",
        "Selected payment INR",
      ],
      rows: r.items.map((i) => [
        i.name,
        i.portion,
        i.quantity,
        fmt(i.net_paise),
        fmt(i.matched_paise),
      ]),
    },
    {
      name: "Corrections",
      columns: [
        "Correction ID",
        "Original bill",
        "Original timestamp UTC",
        "Correction timestamp UTC",
        "Kind",
        "Amount INR",
        "Payment",
        "Reason",
        "Cash returned INR",
        "GPay returned INR",
        "Selected payment INR",
      ],
      rows: r.adjustments.map((a) => [
        a.id,
        a.bill_number,
        a.original_date,
        a.created_at,
        a.kind,
        fmt(a.amount_paise),
        a.method,
        a.reason,
        fmt(a.cash_paise),
        fmt(a.upi_paise),
        fmt(a.matched_paise),
      ]),
    },
    {
      name: "Print log",
      columns: ["Attempt ID", "Bill", "Timestamp UTC", "State", "Detail"],
      rows: r.prints.map((p) => [
        p.id,
        p.bill_number,
        p.created_at,
        p.state,
        p.detail,
      ]),
    },
  ];
}
function monthly(days) {
  const months = new Map();
  for (const d of days) {
    const month = d.day.slice(0, 7);
    const m = months.get(month) || {
      month,
      bills: 0,
      sales_paise: 0,
      corrections_paise: 0,
      net_paise: 0,
    };
    for (const k of ["bills", "sales_paise", "corrections_paise", "net_paise"])
      m[k] += d[k];
    months.set(month, m);
  }
  return [...months.values()];
}
export function csv(r) {
  const rows = [];
  const quoted = (value, amount = false) => {
    const content = amount ? String(value) : spreadsheetText(value);
    if (amount && !/^-?\d+\.\d{2}$/.test(content))
      throw new Error("Invalid export amount");
    return '"' + content.replace(/"/g, '""') + '"';
  };
  for (const table of datasets(r)) {
    rows.push(
      quoted(table.name),
      table.columns.map((v) => quoted(v)).join(","),
    );
    for (const row of table.rows)
      rows.push(
        row
          .map((v, index) =>
            quoted(
              v,
              table.columns[index].endsWith("INR") ||
                (table.name === "Summary" &&
                  index === 1 &&
                  (table.moneyLabels || []).includes(row[0])),
            ),
          )
          .join(","),
      );
    rows.push("");
  }
  return "\uFEFF" + rows.join("\r\n");
}
export async function xlsx(r) {
  const [{ default: ExcelJS }, { default: JSZip }] = await Promise.all([
    import("exceljs"),
    import("jszip"),
  ]);
  const workbook = new ExcelJS.Workbook();
  const numericCells = [];
  workbook.creator = "Restaurant POS";
  for (const table of datasets(r)) {
    const sheet = workbook.addWorksheet(table.name);
    sheet.addRow(table.columns);
    sheet.getRow(1).font = { bold: true };
    sheet.getRow(1).alignment = { vertical: "middle", wrapText: true };
    sheet.getRow(1).height = 44;
    sheet.views = [{ state: "frozen", ySplit: 1 }];
    for (const row of table.rows) {
      const added = sheet.addRow(
        row.map((v) => (typeof v === "number" ? v : spreadsheetText(v))),
      );
      for (let col = 0; col < row.length; col++) {
        const amount =
          table.columns[col].endsWith("INR") ||
          (table.name === "Summary" &&
            col === 1 &&
            (table.moneyLabels || []).includes(row[0]));
        if (amount) {
          const cell = added.getCell(col + 1);
          cell.numFmt = "#,##0.00;[Red]-#,##0.00";
          numericCells.push({
            sheet: sheet.id,
            address: cell.address,
            decimal: row[col],
          });
        }
      }
    }
    sheet.columns.forEach((c, i) => {
      c.width = Math.min(45, Math.max(15, table.columns[i].length + 2));
    });
    sheet.autoFilter = {
      from: { row: 1, column: 1 },
      to: { row: Math.max(1, sheet.rowCount), column: table.columns.length },
    };
  }
  // Write the exact decimal string directly as a numeric XML value. No money is calculated
  // through Number / parseFloat, and spreadsheet SUM works on the exported amount cells.
  const zip = await JSZip.loadAsync(await workbook.xlsx.writeBuffer());
  for (const sheet of workbook.worksheets) {
    const path = `xl/worksheets/sheet${sheet.id}.xml`;
    let xml = await zip.file(path).async("string");
    const amounts = new Map(
      numericCells
        .filter((c) => c.sheet === sheet.id)
        .map((c) => [c.address, c.decimal]),
    );
    xml = xml.replace(
      /<c r="([^"]+)"([^>]*)>[\s\S]*?<\/c>/g,
      (original, address, attributes) => {
        if (!amounts.has(address)) return original;
        const value = amounts.get(address);
        if (!/^-?\d+\.\d{2}$/.test(value))
          throw new Error("Invalid export amount");
        return `<c r="${address}"${attributes.replace(/ t="[^"]*"/, "")}><v>${value}</v></c>`;
      },
    );
    zip.file(path, xml);
  }
  return zip.generateAsync({ type: "uint8array", compression: "DEFLATE" });
}

/** Raster PDF uses the browser's Indic shaping and bundled Tamil font on every page. */
export async function pdf(r) {
  await document.fonts.load('18px "Noto Sans Tamil"');
  await document.fonts.ready;
  const pages = [];
  const W = 1754,
    H = 1240;
  for (const table of datasets(r)) {
    // Wide registers use readable field/value blocks rather than clipped 16-column tables.
    const entries = table.rows.length
      ? table.rows
      : [["No records for this period"]];
    let canvas, ctx, y;
    const page = () => {
      if (canvas) pages.push(canvas.toDataURL("image/jpeg", 0.92));
      canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = H;
      ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#111";
      ctx.font = 'bold 27px Inter,"Noto Sans Tamil",sans-serif';
      ctx.fillText(`Auditor export — ${table.name}`, 45, 48);
      ctx.font = '18px Inter,"Noto Sans Tamil",sans-serif';
      ctx.fillText(
        `${r.from} to ${r.to} (Asia/Kolkata) · ${r.method} · Page ${pages.length + 1}`,
        45,
        82,
      );
      ctx.fillText(
        "Amounts INR · Corrections use recorded date · UPI cashier-recorded",
        45,
        111,
      );
      y = 151;
    };
    const wrap = (str, width) => {
      const words = String(str).split(/\s+/);
      const output = [];
      let line = "";
      for (const word of words) {
        if (ctx.measureText(line + " " + word).width > width && line) {
          output.push(line);
          line = word;
        } else line += (line ? " " : "") + word;
      }
      output.push(line);
      return output.flatMap((l) => {
        if (ctx.measureText(l).width <= width) return [l];
        const out = [];
        let s = "";
        for (const c of l) {
          if (ctx.measureText(s + c).width > width) {
            out.push(s);
            s = c;
          } else s += c;
        }
        out.push(s);
        return out;
      });
    };
    page();
    const columns = table.columns.length <= 5 ? table.columns.length : 3;
    const colWidth = (W - 90) / columns;
    for (let ri = 0; ri < entries.length; ri++) {
      const row = entries[ri];
      for (let base = 0; base < row.length; base += columns) {
        const cells = row
          .slice(base, base + columns)
          .map((v, i) =>
            wrap(`${table.columns[base + i]}: ${v}`, colWidth - 22),
          );
        const height = Math.max(...cells.map((c) => c.length)) * 26 + 14;
        if (y + height > H - 65) page();
        ctx.fillStyle = ri % 2 ? "#f1f4f8" : "#fff";
        ctx.fillRect(40, y - 20, W - 80, height);
        ctx.fillStyle = "#111";
        cells.forEach((lines, ci) =>
          lines.forEach((line, li) =>
            ctx.fillText(line, 45 + ci * colWidth, y + li * 26),
          ),
        );
        y += height;
      }
      y += 10;
    }
    pages.push(canvas.toDataURL("image/jpeg", 0.92));
  }
  return imagePDF(pages, W, H);
}

// Minimal PDF 1.4 with full-page JPEG XObjects. All text is shaped before embedding.
function imagePDF(images, width, height) {
  const enc = new TextEncoder();
  const parts = [];
  let offset = 0;
  const offsets = [0];
  const push = (data) => {
    const bytes = typeof data === "string" ? enc.encode(data) : data;
    parts.push(bytes);
    offset += bytes.length;
  };
  const object = (id, body, binary) => {
    offsets[id] = offset;
    push(`${id} 0 obj\n`);
    push(body);
    if (binary) push(binary);
    push("\nendobj\n");
  };
  push("%PDF-1.4\n");
  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(
    2,
    `<< /Type /Pages /Count ${images.length} /Kids [${images.map((_, i) => `${3 + i * 3} 0 R`).join(" ")}] >>`,
  );
  images.forEach((url, i) => {
    const p = 3 + i * 3;
    const bytes = Uint8Array.from(atob(url.split(",")[1]), (c) =>
      c.charCodeAt(0),
    );
    object(
      p,
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /XObject << /Img ${p + 1} 0 R >> >> /Contents ${p + 2} 0 R >>`,
    );
    object(
      p + 1,
      `<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${bytes.length} >>\nstream\n`,
      new Uint8Array([...bytes, ...enc.encode("\nendstream")]),
    );
    const commands = "q 842 0 0 595 0 0 cm /Img Do Q\n";
    object(
      p + 2,
      `<< /Length ${enc.encode(commands).length} >>\nstream\n${commands}endstream`,
    );
  });
  const xref = offset;
  push(`xref\n0 ${offsets.length}\n0000000000 65535 f \n`);
  for (let i = 1; i < offsets.length; i++)
    push(`${String(offsets[i]).padStart(10, "0")} 00000 n \n`);
  push(
    `trailer\n<< /Size ${offsets.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`,
  );
  const result = new Uint8Array(offset);
  let cursor = 0;
  for (const part of parts) {
    result.set(part, cursor);
    cursor += part.length;
  }
  return result;
}
export async function exportReport(r, format) {
  const name = `restaurant-${r.from}-${r.to}-${r.method}.${format}`;
  const content =
    format === "csv"
      ? csv(r)
      : format === "xlsx"
        ? await xlsx(r)
        : await pdf(r);
  return saveFile(
    name,
    format === "csv"
      ? "text/csv;charset=utf-8"
      : format === "xlsx"
        ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        : "application/pdf",
    content,
  );
}

// Validates /data against the contract: schemas, references and arithmetic.
//   npm run check:data
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  DATA_DIR,
  listInbox,
  loadCapturedFixture,
  loadContext,
  loadExpectedOutcomes,
} from "@ap/shared/load";

const errors: string[] = [];
const fail = (msg: string) => errors.push(msg);

const ctx = loadContext(); // throws if any file breaks its schema
const vendorIds = new Set(ctx.vendors.map((v) => v.id));
const poById = new Map(ctx.purchaseOrders.map((p) => [p.id, p]));

for (const po of ctx.purchaseOrders) {
  if (!vendorIds.has(po.vendor_id)) fail(`${po.id}: unknown vendor ${po.vendor_id}`);
}
for (const gr of ctx.receipts) {
  const po = poById.get(gr.po_id);
  if (!po) {
    fail(`${gr.id}: unknown PO ${gr.po_id}`);
    continue;
  }
  for (const l of gr.lines) {
    if (!po.lines.some((p) => p.line_no === l.po_line_no)) {
      fail(`${gr.id}: no line ${l.po_line_no} on ${po.id}`);
    }
  }
}

const inbox = listInbox();
const outcomes = loadExpectedOutcomes();
for (const file of inbox) {
  const inv = loadCapturedFixture(file);
  if (inv.source_file !== file) fail(`${inv.id}: source_file is not ${file}`);
  if (inv.vendor_id && !vendorIds.has(inv.vendor_id)) fail(`${inv.id}: unknown vendor`);
  if (inv.po_id && !poById.has(inv.po_id)) fail(`${inv.id}: unknown PO`);
  const sum = inv.lines.reduce((s, l) => s + l.amount_cents, 0);
  if (inv.lines.some((l) => l.amount_cents !== l.qty * l.unit_price_cents)) {
    fail(`${inv.id}: a line amount is not qty x unit price`);
  }
  if (sum !== inv.subtotal_cents) fail(`${inv.id}: subtotal does not equal line sum`);
  if (inv.subtotal_cents + inv.tax_cents !== inv.total_cents) fail(`${inv.id}: total is off`);
  if (!outcomes.some((o) => o.invoice_id === inv.id)) fail(`${inv.id}: no expected outcome`);
}
for (const o of outcomes) {
  if (!existsSync(join(DATA_DIR, "inbox", `${o.invoice_id}.pdf`))) {
    fail(`${o.invoice_id}: expected outcome without a PDF in inbox`);
  }
}

if (errors.length > 0) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(
  `Data OK: ${ctx.vendors.length} vendors, ${ctx.purchaseOrders.length} POs, ` +
    `${ctx.receipts.length} receipts, ${inbox.length} invoices, ${ctx.bankTxns.length} bank lines.`,
);

// Regenerates everything under /data. Deterministic: same output every run.
//   npm run seed
// Never hand-edit /data. Change this file, run it, commit both.
import { createWriteStream, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import PDFDocument from "pdfkit";
import type {
  BankDetails,
  BankTxn,
  ExpectedOutcome,
  GoodsReceipt,
  Invoice,
  InvoiceLine,
  Policy,
  PurchaseOrder,
  Vendor,
} from "@ap/shared";

const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "data");
const BUYER = "Meridian Manufacturing Co.";
const usd = (c: number) =>
  `$${(c / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

function writeJson(path: string, value: unknown) {
  const full = join(DATA, path);
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, JSON.stringify(value, null, 2) + "\n");
}

function addDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------- master data
// All companies, people and bank details below are fictional.
const vendors: Vendor[] = [
  { id: "V-001", name: "Northwind Packaging LLC", email: "ar@northwind-packaging.example.com", payment_terms_days: 30, bank: { routing_number: "101050001", account_number: "987650001" }, active: true },
  { id: "V-002", name: "Cascade Industrial Supply", email: "billing@cascade-industrial.example.com", payment_terms_days: 30, bank: { routing_number: "101050001", account_number: "987650002" }, active: true },
  { id: "V-003", name: "Brightline Logistics Inc.", email: "invoices@brightline-logistics.example.com", payment_terms_days: 15, bank: { routing_number: "101050001", account_number: "987650003" }, active: true },
  { id: "V-004", name: "Summit Office Furnishings", email: "accounts@summit-office.example.com", payment_terms_days: 45, bank: { routing_number: "101050001", account_number: "987650004" }, active: true },
  { id: "V-005", name: "Harbor Electrical Wholesale", email: "ar@harbor-electrical.example.com", payment_terms_days: 30, bank: { routing_number: "101050001", account_number: "987650005" }, active: true },
];

const purchaseOrders: PurchaseOrder[] = [
  { id: "PO-1001", vendor_id: "V-001", cost_center: "OPS-110", requester: "Priya Raman", created_at: "2026-10-01", currency: "USD", lines: [
    { line_no: 1, sku: "BOX-12", description: "Corrugated shipping box 12in", qty: 500, unit_price_cents: 120 },
    { line_no: 2, sku: "TAPE-2", description: "Packing tape 2in, roll", qty: 200, unit_price_cents: 350 },
  ] },
  { id: "PO-1002", vendor_id: "V-002", cost_center: "MFG-220", requester: "Tomás Ibarra", created_at: "2026-10-03", currency: "USD", lines: [
    { line_no: 1, sku: "GLV-CS", description: "Cut-resistant safety gloves, case", qty: 40, unit_price_cents: 8500 },
  ] },
  { id: "PO-1003", vendor_id: "V-004", cost_center: "FAC-300", requester: "Hannah Okafor", created_at: "2026-10-05", currency: "USD", lines: [
    { line_no: 1, sku: "DSK-SS", description: "Sit-stand desk, 60in", qty: 60, unit_price_cents: 80000 },
  ] },
  { id: "PO-1004", vendor_id: "V-005", cost_center: "FAC-300", requester: "Hannah Okafor", created_at: "2026-10-08", currency: "USD", lines: [
    { line_no: 1, sku: "LED-P24", description: "LED panel light 2x4", qty: 100, unit_price_cents: 4200 },
  ] },
  { id: "PO-1005", vendor_id: "V-003", cost_center: "OPS-110", requester: "Priya Raman", created_at: "2026-10-10", currency: "USD", lines: [
    { line_no: 1, sku: "FRT-PLT", description: "Pallet freight, regional", qty: 10, unit_price_cents: 25000 },
  ] },
];

const goodsReceipts: GoodsReceipt[] = [
  { id: "GR-2001", po_id: "PO-1001", received_at: "2026-10-14", lines: [{ po_line_no: 1, qty_received: 500 }, { po_line_no: 2, qty_received: 200 }] },
  { id: "GR-2002", po_id: "PO-1002", received_at: "2026-10-16", lines: [{ po_line_no: 1, qty_received: 40 }] },
  { id: "GR-2003", po_id: "PO-1003", received_at: "2026-10-20", lines: [{ po_line_no: 1, qty_received: 60 }] },
  // Short delivery: 80 of 100 arrived.
  { id: "GR-2004", po_id: "PO-1004", received_at: "2026-10-21", lines: [{ po_line_no: 1, qty_received: 80 }] },
  { id: "GR-2005", po_id: "PO-1005", received_at: "2026-10-22", lines: [{ po_line_no: 1, qty_received: 10 }] },
];

const policy: Policy = {
  auto_approve_limit_cents: 1_000_000, // $10,000
  max_single_payment_cents: 10_000_000, // $100,000
  price_tolerance_pct: 2,
  qty_tolerance_pct: 0,
  tiers: [
    { up_to_cents: 5_000_000, approver_role: "finance_manager" },
    { up_to_cents: null, approver_role: "cfo" },
  ],
};

// ------------------------------------------------------------------- invoices
type LineSpec = Omit<InvoiceLine, "line_no" | "amount_cents">;

function poLines(poId: string, override: Partial<LineSpec> = {}): LineSpec[] {
  const po = purchaseOrders.find((p) => p.id === poId)!;
  return po.lines.map((l) => ({
    po_line_no: l.line_no,
    description: l.description,
    qty: l.qty,
    unit_price_cents: l.unit_price_cents,
    ...override,
  }));
}

interface Spec {
  vendorId: string | null;
  /** Used when the vendor is not in the master file. */
  stranger?: { name: string; bank: BankDetails; terms: number };
  invoiceNumber: string;
  poId: string | null;
  invoiceDate: string;
  lines: LineSpec[];
  expect: Omit<ExpectedOutcome, "invoice_id">;
}

const specs: Spec[] = [
  { vendorId: "V-001", invoiceNumber: "NW-88213", poId: "PO-1001", invoiceDate: "2026-10-15", lines: poLines("PO-1001"),
    expect: { scenario: "Clean match, under the limit", demo: "A: touchless, straight through to paid", match_outcome: "matched", exception_codes: [], resting_status: "reconciled" } },
  { vendorId: "V-002", invoiceNumber: "CI-40117", poId: "PO-1002", invoiceDate: "2026-10-17", lines: poLines("PO-1002", { unit_price_cents: 8925 }),
    expect: { scenario: "Unit price 5% above PO", demo: "B: agent explains and resolves or escalates", match_outcome: "exception", exception_codes: ["PRICE_VARIANCE"], resting_status: "exception" } },
  { vendorId: "V-004", invoiceNumber: "SOF-2291", poId: "PO-1003", invoiceDate: "2026-10-21", lines: poLines("PO-1003"),
    expect: { scenario: "Clean match, $48,000 is over the auto-approve limit", demo: "C: pauses for a human click, then pays", match_outcome: "matched", exception_codes: [], resting_status: "matched" } },
  { vendorId: "V-005", invoiceNumber: "HE-7730", poId: "PO-1004", invoiceDate: "2026-10-22", lines: poLines("PO-1004"),
    expect: { scenario: "Billed 100, only 80 received", demo: null, match_outcome: "exception", exception_codes: ["QTY_OVER_RECEIPT"], resting_status: "exception" } },
  { vendorId: "V-001", invoiceNumber: "NW-88213", poId: "PO-1001", invoiceDate: "2026-10-15", lines: poLines("PO-1001"),
    expect: { scenario: "Second copy of INV-0001", demo: null, match_outcome: "exception", exception_codes: ["DUPLICATE_INVOICE"], resting_status: "exception" } },
  { vendorId: "V-003", invoiceNumber: "BL-5521", poId: null, invoiceDate: "2026-10-23",
    lines: [{ po_line_no: null, description: "Expedited freight surcharge", qty: 3, unit_price_cents: 40000 }],
    expect: { scenario: "No PO number on the invoice", demo: null, match_outcome: "exception", exception_codes: ["MISSING_PO"], resting_status: "exception" } },
  { vendorId: "V-003", invoiceNumber: "BL-5507", poId: "PO-1005", invoiceDate: "2026-10-23", lines: poLines("PO-1005", { unit_price_cents: 25200 }),
    expect: { scenario: "Unit price 0.8% above PO, inside tolerance", demo: null, match_outcome: "matched", exception_codes: [], resting_status: "reconciled" } },
  { vendorId: null, stranger: { name: "Nortwind Packaging LLC", bank: { routing_number: "101050001", account_number: "555000999" }, terms: 30 },
    invoiceNumber: "NW-88290", poId: "PO-1001", invoiceDate: "2026-10-24", lines: poLines("PO-1001"),
    expect: { scenario: "Look-alike vendor name with different bank details", demo: null, match_outcome: "exception", exception_codes: ["UNKNOWN_VENDOR"], resting_status: "exception" } },
];

const invoices: Invoice[] = specs.map((s, i) => {
  const id = `INV-${String(i + 1).padStart(4, "0")}`;
  const vendor = vendors.find((v) => v.id === s.vendorId);
  const lines: InvoiceLine[] = s.lines.map((l, j) => ({
    line_no: j + 1,
    ...l,
    amount_cents: l.qty * l.unit_price_cents,
  }));
  const subtotal = lines.reduce((sum, l) => sum + l.amount_cents, 0);
  return {
    id,
    source_file: `${id}.pdf`,
    vendor_id: vendor?.id ?? null,
    vendor_name: vendor?.name ?? s.stranger!.name,
    po_id: s.poId,
    invoice_number: s.invoiceNumber,
    invoice_date: s.invoiceDate,
    due_date: addDays(s.invoiceDate, vendor?.payment_terms_days ?? s.stranger!.terms),
    currency: "USD",
    lines,
    subtotal_cents: subtotal,
    tax_cents: 0,
    total_cents: subtotal,
    remit_to: vendor?.bank ?? s.stranger!.bank,
    status: "captured",
    history: [
      { at: `${s.invoiceDate}T15:00:00.000Z`, from: "received", to: "captured", actor: "seed" },
    ],
  };
});

const outcomes: ExpectedOutcome[] = specs.map((s, i) => ({
  invoice_id: invoices[i].id,
  ...s.expect,
}));

// Statement lines for the payments the pipeline makes in mock mode, plus noise.
const paidRef = (n: number) => ({
  amount_cents: -invoices[n - 1].total_cents,
  reference: `ap-${invoices[n - 1].id}`,
});
const bankStatement: BankTxn[] = [
  { id: "BT-9001", posted_at: "2026-11-10", description: "ACH NORTHWIND PACKAGING", ...paidRef(1) },
  { id: "BT-9002", posted_at: "2026-11-10", description: "ACH BRIGHTLINE LOGISTICS", ...paidRef(7) },
  { id: "BT-9003", posted_at: "2026-11-12", description: "ACH SUMMIT OFFICE FURN", ...paidRef(3) },
  { id: "BT-9004", posted_at: "2026-11-13", description: "PAYROLL", amount_cents: -1_875_000, reference: null },
  { id: "BT-9005", posted_at: "2026-11-13", description: "CUSTOMER DEPOSIT", amount_cents: 500_000, reference: null },
];

// ------------------------------------------------------------------------ PDFs
function writePdf(inv: Invoice): Promise<void> {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({
      size: "LETTER",
      margin: 54,
      info: { Title: `Invoice ${inv.invoice_number}`, CreationDate: new Date("2026-11-01T00:00:00Z") },
    });
    const out = createWriteStream(join(DATA, "inbox", inv.source_file));
    out.on("finish", resolve);
    out.on("error", reject);
    doc.pipe(out);

    doc.fontSize(18).text(inv.vendor_name);
    doc.moveDown(0.5).fontSize(24).text("INVOICE", { align: "right" });
    doc.moveDown(0.5).fontSize(10);
    doc.text(`Invoice number: ${inv.invoice_number}`);
    doc.text(`Invoice date: ${inv.invoice_date}`);
    doc.text(`Due date: ${inv.due_date}`);
    if (inv.po_id) doc.text(`PO number: ${inv.po_id}`);
    doc.moveDown().text(`Bill to: ${BUYER}`);
    doc.moveDown(1.5);

    const cols = [54, 300, 370, 460];
    let y = doc.y;
    doc.font("Helvetica-Bold");
    ["Description", "Qty", "Unit price", "Amount"].forEach((h, i) => doc.text(h, cols[i], y));
    doc.font("Helvetica");
    for (const l of inv.lines) {
      y += 20;
      doc.text(l.description, cols[0], y, { width: 235 });
      doc.text(String(l.qty), cols[1], y);
      doc.text(usd(l.unit_price_cents), cols[2], y);
      doc.text(usd(l.amount_cents), cols[3], y);
    }
    y += 36;
    doc.text(`Subtotal: ${usd(inv.subtotal_cents)}`, cols[2], y);
    doc.text(`Tax: ${usd(inv.tax_cents)}`, cols[2], y + 16);
    doc.font("Helvetica-Bold").text(`Total due: ${usd(inv.total_cents)}`, cols[2], y + 32);
    doc.font("Helvetica");
    if (inv.remit_to) {
      doc.text(
        `Remit by ACH to routing ${inv.remit_to.routing_number}, account ${inv.remit_to.account_number}`,
        54,
        y + 72,
      );
    }
    doc.end();
  });
}

// ----------------------------------------------------------------------- write
rmSync(join(DATA, "inbox"), { recursive: true, force: true });
rmSync(join(DATA, "expected"), { recursive: true, force: true });
mkdirSync(join(DATA, "inbox"), { recursive: true });

writeJson("vendors.json", vendors);
writeJson("purchase_orders.json", purchaseOrders);
writeJson("goods_receipts.json", goodsReceipts);
writeJson("policy.json", policy);
writeJson("bank_statement.json", bankStatement);
writeJson("expected/outcomes.json", outcomes);
for (const inv of invoices) {
  writeJson(`expected/captured/${inv.id}.json`, inv);
  await writePdf(inv);
}
console.log(`Seeded ${invoices.length} invoices into ${DATA}`);

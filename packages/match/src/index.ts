// LANE 2.
// match(): a working deterministic baseline. Extend it, keep the signature.
// resolveException(): STUB that escalates everything. This is where the agent goes.
import {
  transition,
  type MatchException,
  type MatchStage,
  type ResolveStage,
} from "@ap/shared";

const usd = (cents: number) => `$${(cents / 100).toFixed(2)}`;

export const match: MatchStage = async (invoice, ctx) => {
  const exceptions: MatchException[] = [];
  const { policy } = ctx;

  const vendor = ctx.vendors.find((v) => v.id === invoice.vendor_id && v.active);
  if (!vendor) {
    exceptions.push({
      code: "UNKNOWN_VENDOR",
      detail: `No active vendor matches "${invoice.vendor_name}"`,
    });
  }

  const duplicate = ctx.priorInvoices.find(
    (p) =>
      p.id !== invoice.id &&
      invoice.vendor_id !== null &&
      p.vendor_id === invoice.vendor_id &&
      p.invoice_number === invoice.invoice_number,
  );
  if (duplicate) {
    exceptions.push({
      code: "DUPLICATE_INVOICE",
      detail: `Same vendor and invoice number as ${duplicate.id}`,
    });
  }

  const po = ctx.purchaseOrders.find((p) => p.id === invoice.po_id);
  if (!po) {
    exceptions.push({
      code: "MISSING_PO",
      detail: invoice.po_id
        ? `PO ${invoice.po_id} not found`
        : "Invoice quotes no PO number",
    });
  } else {
    for (const line of invoice.lines) {
      const poLine = po.lines.find((l) => l.line_no === line.po_line_no);
      if (!poLine) {
        exceptions.push({
          code: "MISSING_PO",
          line_no: line.line_no,
          detail: `Line ${line.line_no} maps to no line on ${po.id}`,
        });
        continue;
      }
      const maxPrice =
        poLine.unit_price_cents * (1 + policy.price_tolerance_pct / 100);
      if (line.unit_price_cents > maxPrice) {
        exceptions.push({
          code: "PRICE_VARIANCE",
          line_no: line.line_no,
          detail: `Unit price above PO by more than ${policy.price_tolerance_pct}%`,
          expected: usd(poLine.unit_price_cents),
          actual: usd(line.unit_price_cents),
        });
      }
      const received = ctx.receipts
        .filter((r) => r.po_id === po.id)
        .flatMap((r) => r.lines)
        .filter((l) => l.po_line_no === poLine.line_no)
        .reduce((sum, l) => sum + l.qty_received, 0);
      if (line.qty > received * (1 + policy.qty_tolerance_pct / 100)) {
        exceptions.push({
          code: "QTY_OVER_RECEIPT",
          line_no: line.line_no,
          detail: "Invoiced quantity exceeds quantity received",
          expected: String(received),
          actual: String(line.qty),
        });
      }
    }
  }

  const lineSum = invoice.lines.reduce((sum, l) => sum + l.amount_cents, 0);
  const linesOk = invoice.lines.every(
    (l) => l.amount_cents === l.qty * l.unit_price_cents,
  );
  if (
    !linesOk ||
    lineSum !== invoice.subtotal_cents ||
    invoice.subtotal_cents + invoice.tax_cents !== invoice.total_cents
  ) {
    exceptions.push({
      code: "TOTAL_MISMATCH",
      detail: "Line amounts, subtotal, tax and total do not add up",
    });
  }

  const outcome = exceptions.length === 0 ? "matched" : "exception";
  return transition(
    {
      ...invoice,
      match: { outcome, exceptions, checked_at: new Date().toISOString() },
    },
    outcome,
    "match",
    exceptions.map((e) => e.code).join(", ") || undefined,
  );
};

export const resolveException: ResolveStage = async (invoice) => {
  if (invoice.status !== "exception" || !invoice.match) return invoice;
  return {
    ...invoice,
    match: {
      ...invoice.match,
      resolution: {
        action: "escalated",
        rationale: "Stub: no exception agent yet, so everything goes to a person.",
        by: "resolve-stub",
      },
    },
  };
};

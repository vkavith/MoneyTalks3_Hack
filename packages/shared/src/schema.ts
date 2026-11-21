// THE CONTRACT. Every lane reads and writes these shapes.
// Do not change this file in a feature PR. See AGENTS.md, "Changing the contract".
import { z } from "zod";

/** All money is integer cents. Never floats. */
export const Cents = z.number().int();
/** Calendar dates are YYYY-MM-DD. Timestamps are ISO 8601 UTC. */
export const IsoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const IsoDateTime = z.string().datetime();

export const BankDetails = z.object({
  routing_number: z.string(),
  account_number: z.string(),
});

export const Vendor = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().email(),
  payment_terms_days: z.number().int().positive(),
  bank: BankDetails,
  active: z.boolean(),
});

export const PoLine = z.object({
  line_no: z.number().int().positive(),
  sku: z.string(),
  description: z.string(),
  qty: z.number().int().positive(),
  unit_price_cents: Cents,
});

export const PurchaseOrder = z.object({
  id: z.string(),
  vendor_id: z.string(),
  cost_center: z.string(),
  requester: z.string(),
  created_at: IsoDate,
  currency: z.literal("USD"),
  lines: z.array(PoLine).min(1),
});

export const GoodsReceipt = z.object({
  id: z.string(),
  po_id: z.string(),
  received_at: IsoDate,
  lines: z.array(
    z.object({
      po_line_no: z.number().int().positive(),
      qty_received: z.number().int().nonnegative(),
    }),
  ),
});

export const InvoiceStatus = z.enum([
  "received",
  "captured",
  "matched",
  "exception",
  "approved",
  "rejected",
  "paid",
  "reconciled",
]);

export const ExceptionCode = z.enum([
  "PRICE_VARIANCE",
  "QTY_OVER_RECEIPT",
  "MISSING_PO",
  "DUPLICATE_INVOICE",
  "UNKNOWN_VENDOR",
  "TOTAL_MISMATCH",
]);

export const InvoiceLine = z.object({
  line_no: z.number().int().positive(),
  /** Which PO line this bills. null when the invoice quotes no PO. */
  po_line_no: z.number().int().positive().nullable(),
  description: z.string(),
  qty: z.number().int().positive(),
  unit_price_cents: Cents,
  amount_cents: Cents,
});

export const MatchException = z.object({
  code: ExceptionCode,
  line_no: z.number().int().positive().optional(),
  detail: z.string(),
  expected: z.string().optional(),
  actual: z.string().optional(),
});

export const MatchResult = z.object({
  outcome: z.enum(["matched", "exception"]),
  exceptions: z.array(MatchException),
  checked_at: IsoDateTime,
  /** Filled by the exception agent (lane 2). */
  resolution: z
    .object({
      action: z.enum(["auto_resolved", "escalated"]),
      rationale: z.string(),
      by: z.string(),
    })
    .optional(),
});

export const Approval = z.object({
  decision: z.enum(["auto_approved", "approved", "rejected", "pending"]),
  /** A person's name once decided, or the role it is waiting on while pending. */
  approver: z.string().nullable(),
  reason: z.string(),
  decided_at: IsoDateTime.nullable(),
});

export const Payment = z.object({
  provider: z.enum(["mock", "increase"]),
  transfer_id: z.string(),
  amount_cents: Cents,
  idempotency_key: z.string(),
  status: z.enum(["pending", "submitted", "settled", "returned"]),
  created_at: IsoDateTime,
});

export const Reconciliation = z.object({
  bank_txn_id: z.string(),
  matched_at: IsoDateTime,
});

export const HistoryEntry = z.object({
  at: IsoDateTime,
  from: InvoiceStatus.nullable(),
  to: InvoiceStatus,
  actor: z.string(),
  note: z.string().optional(),
});

/** The one record that travels through the whole pipeline. */
export const Invoice = z.object({
  id: z.string(),
  source_file: z.string(),
  /** null when the name on the invoice matches no vendor in the master file. */
  vendor_id: z.string().nullable(),
  vendor_name: z.string(),
  po_id: z.string().nullable(),
  invoice_number: z.string(),
  invoice_date: IsoDate,
  due_date: IsoDate,
  currency: z.literal("USD"),
  lines: z.array(InvoiceLine).min(1),
  subtotal_cents: Cents,
  tax_cents: Cents,
  total_cents: Cents,
  /** Bank details printed on the invoice, if any. Informational only: payments
   *  always go to the bank details in the vendor master file. */
  remit_to: BankDetails.optional(),
  status: InvoiceStatus,
  match: MatchResult.optional(),
  approval: Approval.optional(),
  payment: Payment.optional(),
  reconciliation: Reconciliation.optional(),
  history: z.array(HistoryEntry),
});

export const BankTxn = z.object({
  id: z.string(),
  posted_at: IsoDate,
  /** Negative = money out. */
  amount_cents: Cents,
  description: z.string(),
  /** Carries the payment idempotency key for payments we originated. */
  reference: z.string().nullable(),
});

export const Policy = z.object({
  auto_approve_limit_cents: Cents,
  max_single_payment_cents: Cents,
  price_tolerance_pct: z.number().nonnegative(),
  qty_tolerance_pct: z.number().nonnegative(),
  /** First tier whose up_to_cents covers the total wins. null = no ceiling. */
  tiers: z.array(
    z.object({ up_to_cents: Cents.nullable(), approver_role: z.string() }),
  ),
});

export const ExpectedOutcome = z.object({
  invoice_id: z.string(),
  scenario: z.string(),
  demo: z.string().nullable(),
  match_outcome: z.enum(["matched", "exception"]),
  exception_codes: z.array(ExceptionCode),
  /** Where the invoice rests when no human acts. */
  resting_status: InvoiceStatus,
});

export type BankDetails = z.infer<typeof BankDetails>;
export type Vendor = z.infer<typeof Vendor>;
export type PoLine = z.infer<typeof PoLine>;
export type PurchaseOrder = z.infer<typeof PurchaseOrder>;
export type GoodsReceipt = z.infer<typeof GoodsReceipt>;
export type InvoiceStatus = z.infer<typeof InvoiceStatus>;
export type ExceptionCode = z.infer<typeof ExceptionCode>;
export type InvoiceLine = z.infer<typeof InvoiceLine>;
export type MatchException = z.infer<typeof MatchException>;
export type MatchResult = z.infer<typeof MatchResult>;
export type Approval = z.infer<typeof Approval>;
export type Payment = z.infer<typeof Payment>;
export type Reconciliation = z.infer<typeof Reconciliation>;
export type HistoryEntry = z.infer<typeof HistoryEntry>;
export type Invoice = z.infer<typeof Invoice>;
export type BankTxn = z.infer<typeof BankTxn>;
export type Policy = z.infer<typeof Policy>;
export type ExpectedOutcome = z.infer<typeof ExpectedOutcome>;

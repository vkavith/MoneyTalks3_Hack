// Stage signatures. Each lane implements its functions behind these types.
// The orchestrator only ever calls these, so internals are free to change.
import type {
  BankTxn,
  GoodsReceipt,
  Invoice,
  Policy,
  PurchaseOrder,
  Vendor,
} from "./schema";

export interface PipelineContext {
  vendors: Vendor[];
  purchaseOrders: PurchaseOrder[];
  receipts: GoodsReceipt[];
  policy: Policy;
  /** Invoices already seen, for duplicate detection. */
  priorInvoices: Invoice[];
  bankTxns: BankTxn[];
}

export interface HumanDecision {
  approver: string;
  decision: "approved" | "rejected";
  reason: string;
}

/** Lane 1. File in data/inbox -> Invoice with status "captured". */
export type CaptureStage = (sourceFile: string) => Promise<Invoice>;

/** Lane 2. captured -> matched | exception. */
export type MatchStage = (
  invoice: Invoice,
  ctx: PipelineContext,
) => Promise<Invoice>;

/** Lane 2. exception -> matched (auto-resolved) | exception (escalated). */
export type ResolveStage = MatchStage;

/** Lane 3. matched -> approved | rejected, or stays matched with approval pending. */
export type ApproveStage = (
  invoice: Invoice,
  ctx: PipelineContext,
  human?: HumanDecision,
) => Promise<Invoice>;

/** Lane 3. approved -> paid. */
export type PayStage = MatchStage;

/** Lane 3. paid -> reconciled, or unchanged if no bank line matches yet. */
export type ReconcileStage = MatchStage;

// LANE 3. Working baseline with a mock payment provider.
// Replace the mock with the Increase sandbox in ./increase.ts. Keep signatures.
import {
  transition,
  type ApproveStage,
  type Payment,
  type PayStage,
  type ReconcileStage,
} from "@ap/shared";
import { payWithIncrease } from "./increase";

export const approve: ApproveStage = async (invoice, ctx, human) => {
  if (invoice.status !== "matched") {
    throw new Error(`${invoice.id}: only matched invoices can be approved`);
  }
  const now = new Date().toISOString();

  if (human) {
    return transition(
      {
        ...invoice,
        approval: {
          decision: human.decision,
          approver: human.approver,
          reason: human.reason,
          decided_at: now,
        },
      },
      human.decision,
      `human:${human.approver}`,
      human.reason,
    );
  }

  if (invoice.total_cents <= ctx.policy.auto_approve_limit_cents) {
    return transition(
      {
        ...invoice,
        approval: {
          decision: "auto_approved",
          approver: null,
          reason: "Matched and under the auto-approve limit",
          decided_at: now,
        },
      },
      "approved",
      "approve",
    );
  }

  const tier = ctx.policy.tiers.find(
    (t) => t.up_to_cents === null || invoice.total_cents <= t.up_to_cents,
  );
  return {
    ...invoice,
    approval: {
      decision: "pending",
      approver: tier?.approver_role ?? "controller",
      reason: "Total is over the auto-approve limit",
      decided_at: null,
    },
  };
};

/** Guardrails live here, not in the agent's prompt. */
export const pay: PayStage = async (invoice, ctx) => {
  if (invoice.status !== "approved") {
    throw new Error(`${invoice.id}: refusing to pay, status is ${invoice.status}`);
  }
  if (invoice.payment) {
    throw new Error(`${invoice.id}: refusing to pay twice`);
  }
  // Payee and amount come from our records, never from model output
  // and never from the bank details printed on the invoice.
  const vendor = ctx.vendors.find((v) => v.id === invoice.vendor_id && v.active);
  if (!vendor) {
    throw new Error(`${invoice.id}: no active vendor on file`);
  }
  if (invoice.total_cents > ctx.policy.max_single_payment_cents) {
    throw new Error(`${invoice.id}: over the single-payment limit`);
  }

  const idempotencyKey = `ap-${invoice.id}`;
  const provider = process.env.PAYMENT_PROVIDER ?? "mock";
  const payment: Payment =
    provider === "increase"
      ? await payWithIncrease(invoice, vendor, idempotencyKey)
      : {
          provider: "mock",
          transfer_id: `mock_${invoice.id}`,
          amount_cents: invoice.total_cents,
          idempotency_key: idempotencyKey,
          status: "settled",
          created_at: new Date().toISOString(),
        };

  return transition({ ...invoice, payment }, "paid", "pay", payment.transfer_id);
};

export const reconcile: ReconcileStage = async (invoice, ctx) => {
  if (invoice.status !== "paid" || !invoice.payment) return invoice;
  const { payment } = invoice;
  const txn = ctx.bankTxns.find(
    (t) =>
      t.reference === payment.idempotency_key &&
      t.amount_cents === -payment.amount_cents,
  );
  if (!txn) return invoice;
  return transition(
    {
      ...invoice,
      reconciliation: {
        bank_txn_id: txn.id,
        matched_at: new Date().toISOString(),
      },
    },
    "reconciled",
    "reconcile",
    txn.id,
  );
};

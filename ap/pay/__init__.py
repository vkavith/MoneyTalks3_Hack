"""LANE 3. Working baseline with a mock payment provider.

Replace the mock with the Increase sandbox in ./increase.py. Keep signatures.
"""

from __future__ import annotations

import os

from ap.shared import (
    Approval,
    HumanDecision,
    Invoice,
    Payment,
    PipelineContext,
    Reconciliation,
    now_utc,
    transition,
)

from .increase import pay_with_increase


class PaymentRefused(RuntimeError):
    pass


def approve(invoice: Invoice, ctx: PipelineContext, human: HumanDecision | None = None) -> Invoice:
    if invoice.status != "matched":
        raise ValueError(f"{invoice.id}: only matched invoices can be approved")

    if human is not None:
        approval = Approval(
            decision=human.decision,
            approver=human.approver,
            reason=human.reason,
            decided_at=now_utc(),
        )
        return transition(
            invoice.model_copy(update={"approval": approval}),
            human.decision,
            f"human:{human.approver}",
            human.reason,
        )

    if invoice.total_cents <= ctx.policy.auto_approve_limit_cents:
        approval = Approval(
            decision="auto_approved",
            approver=None,
            reason="Matched and under the auto-approve limit",
            decided_at=now_utc(),
        )
        return transition(invoice.model_copy(update={"approval": approval}), "approved", "approve")

    tier = next(
        (
            t
            for t in ctx.policy.tiers
            if t.up_to_cents is None or invoice.total_cents <= t.up_to_cents
        ),
        None,
    )
    pending = Approval(
        decision="pending",
        approver=tier.approver_role if tier else "controller",
        reason="Total is over the auto-approve limit",
        decided_at=None,
    )
    return invoice.model_copy(update={"approval": pending})


def pay(invoice: Invoice, ctx: PipelineContext) -> Invoice:
    """Guardrails live here, not in the agent's prompt."""
    if invoice.status != "approved":
        raise PaymentRefused(f"{invoice.id}: refusing to pay, status is {invoice.status}")
    if invoice.payment is not None:
        raise PaymentRefused(f"{invoice.id}: refusing to pay twice")
    # Payee and amount come from our records, never from model output
    # and never from the bank details printed on the invoice.
    vendor = next((v for v in ctx.vendors if v.id == invoice.vendor_id and v.active), None)
    if vendor is None:
        raise PaymentRefused(f"{invoice.id}: no active vendor on file")
    if invoice.total_cents > ctx.policy.max_single_payment_cents:
        raise PaymentRefused(f"{invoice.id}: over the single-payment limit")

    idempotency_key = f"ap-{invoice.id}"
    if os.environ.get("PAYMENT_PROVIDER", "mock") == "increase":
        payment = pay_with_increase(invoice, vendor, idempotency_key)
    else:
        payment = Payment(
            provider="mock",
            transfer_id=f"mock_{invoice.id}",
            amount_cents=invoice.total_cents,
            idempotency_key=idempotency_key,
            status="settled",
            created_at=now_utc(),
        )
    return transition(
        invoice.model_copy(update={"payment": payment}), "paid", "pay", payment.transfer_id
    )


def reconcile(invoice: Invoice, ctx: PipelineContext) -> Invoice:
    payment = invoice.payment
    if invoice.status != "paid" or payment is None:
        return invoice
    txn = next(
        (
            t
            for t in ctx.bank_txns
            if t.reference == payment.idempotency_key and t.amount_cents == -payment.amount_cents
        ),
        None,
    )
    if txn is None:
        return invoice
    reconciliation = Reconciliation(bank_txn_id=txn.id, matched_at=now_utc())
    return transition(
        invoice.model_copy(update={"reconciliation": reconciliation}),
        "reconciled",
        "reconcile",
        txn.id,
    )

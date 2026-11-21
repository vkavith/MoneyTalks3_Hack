"""reconcile() on the mock provider, against data/bank_statement.json."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from ap.pay import pay, reconcile
from ap.shared import BankTxn, Invoice, PipelineContext


def test_matches_the_statement_line_by_reference_and_amount(
    approved_small: Invoice, ctx: PipelineContext
) -> None:
    done = reconcile(pay(approved_small, ctx), ctx)
    assert done.status == "reconciled"
    assert done.reconciliation is not None and done.reconciliation.bank_txn_id == "BT-9001"
    assert done.payment is not None and done.payment.status == "settled"


def test_unmatched_payment_is_left_alone(approved_small: Invoice, ctx: PipelineContext) -> None:
    paid = pay(approved_small, ctx)
    quiet = replace(ctx, bank_txns=[])
    assert reconcile(paid, quiet) == paid


def test_not_paid_is_a_no_op(approved_small: Invoice, ctx: PipelineContext) -> None:
    assert reconcile(approved_small, ctx) == approved_small


def test_a_returned_line_sends_the_invoice_back_to_approved(
    approved_small: Invoice, ctx: PipelineContext
) -> None:
    paid = pay(approved_small, ctx)
    assert paid.payment is not None
    returned_line = BankTxn(
        id="BT-9999",
        posted_at=date(2026, 11, 12),
        amount_cents=paid.payment.amount_cents,
        description="ACH RETURN R02 ACCOUNT CLOSED",
        reference=paid.payment.idempotency_key,
    )
    back = reconcile(paid, replace(ctx, bank_txns=[*ctx.bank_txns, returned_line]))
    assert back.status == "approved"
    assert back.payment is not None and back.payment.status == "returned"
    repaid = pay(back, ctx)
    assert repaid.payment is not None and repaid.payment.idempotency_key == "ap-INV-0001-2"

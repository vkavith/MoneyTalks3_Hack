"""LANE 3. Approve, pay and reconcile.

The guardrails live in ``pay()``, in code, not in a prompt. Prism (``prism.py``)
adds a second layer: a guardrail check on the free text behind the decision and
an audit trace of every decision. Money moves only through ``pay()``, and only
through the Increase sandbox (``increase.py``) or the in-repo mock.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from ap.shared import (
    Approval,
    HumanDecision,
    Invoice,
    Payment,
    PipelineContext,
    Reconciliation,
    Vendor,
    now_utc,
    transition,
)

from .increase import (
    FAILED_TRANSFER_STATES,
    IncreaseClient,
    IncreaseError,
    SandboxRequired,
    pay_with_increase,
    payment_status,
)
from .prism import Message, PrismClient, Stopwatch, prism_client

__all__ = ["PaymentRefused", "approve", "pay", "payment_idempotency_key", "reconcile"]


class PaymentRefused(RuntimeError):
    """A guardrail in ``pay()`` stopped the payment. ``guardrail`` names which."""

    def __init__(self, message: str, guardrail: str = "unspecified") -> None:
        super().__init__(message)
        self.guardrail = guardrail


# ---------------------------------------------------------------------------
# approve


def approve(invoice: Invoice, ctx: PipelineContext, human: HumanDecision | None = None) -> Invoice:
    if invoice.status != "matched":
        raise ValueError(f"{invoice.id}: only matched invoices can be approved")
    watch = Stopwatch()
    trace_id = _trace_id(invoice, "approve")

    if human is not None:
        approval = Approval(
            decision=human.decision,
            approver=human.approver,
            reason=human.reason,
            decided_at=now_utc(),
        )
        out = transition(
            invoice.model_copy(update={"approval": approval}),
            human.decision,
            f"human:{human.approver}",
            human.reason,
        )
        _record(
            "approve",
            invoice,
            trace_id,
            _approval_context(invoice, human),
            f"{human.decision.upper()} by {human.approver}: {human.reason}",
            watch,
            outcome=human.decision,
            approver=human.approver,
        )
        return out

    if invoice.total_cents <= ctx.policy.auto_approve_limit_cents:
        approval = Approval(
            decision="auto_approved",
            approver=None,
            reason="Matched and under the auto-approve limit",
            decided_at=now_utc(),
        )
        out = transition(invoice.model_copy(update={"approval": approval}), "approved", "approve")
        _record(
            "approve",
            invoice,
            trace_id,
            _approval_context(invoice, None),
            f"AUTO-APPROVED: {_dollars(invoice.total_cents)} is within the "
            f"{_dollars(ctx.policy.auto_approve_limit_cents)} auto-approve limit",
            watch,
            outcome="auto_approved",
        )
        return out

    tier = next(
        (
            t
            for t in ctx.policy.tiers
            if t.up_to_cents is None or invoice.total_cents <= t.up_to_cents
        ),
        None,
    )
    role = tier.approver_role if tier else "controller"
    pending = Approval(
        decision="pending",
        approver=role,
        reason="Total is over the auto-approve limit",
        decided_at=None,
    )
    out = invoice.model_copy(update={"approval": pending})
    _record(
        "approve",
        invoice,
        trace_id,
        _approval_context(invoice, None),
        f"PENDING: {_dollars(invoice.total_cents)} is over the auto-approve limit, "
        f"waiting on {role}",
        watch,
        outcome="pending",
        approver_role=role,
    )
    return out


# ---------------------------------------------------------------------------
# pay


def payment_idempotency_key(invoice: Invoice) -> str:
    """``ap-<invoice id>``; a re-send after a returned payment gets ``-2``, ``-3``...

    Increase replays a request with a reused key, so the key has to change for
    a payment that was legitimately returned and must go out again.
    """
    attempts = sum(1 for h in invoice.history if h.to_status == "paid")
    return f"ap-{invoice.id}" if attempts == 0 else f"ap-{invoice.id}-{attempts + 1}"


def _provider() -> str:
    return os.environ.get("PAYMENT_PROVIDER", "mock")


def _check_guardrails(invoice: Invoice, ctx: PipelineContext) -> Vendor:
    """Every refusal reason, in order. Returns the vendor to pay."""
    if invoice.payment is not None and invoice.payment.status != "returned":
        raise PaymentRefused(
            f"{invoice.id}: refusing to pay twice (transfer {invoice.payment.transfer_id})",
            guardrail="double_payment",
        )
    if invoice.status != "approved":
        raise PaymentRefused(
            f"{invoice.id}: refusing to pay, status is {invoice.status}", guardrail="status"
        )
    # Payee and amount come from our records, never from model output and never
    # from the bank details printed on the invoice (invoice.remit_to).
    vendor = next((v for v in ctx.vendors if v.id == invoice.vendor_id and v.active), None)
    if vendor is None:
        raise PaymentRefused(f"{invoice.id}: no active vendor on file", guardrail="vendor")
    if invoice.total_cents <= 0:
        raise PaymentRefused(f"{invoice.id}: amount must be positive", guardrail="amount")
    if invoice.total_cents > ctx.policy.max_single_payment_cents:
        raise PaymentRefused(
            f"{invoice.id}: {_dollars(invoice.total_cents)} is over the single-payment limit "
            f"of {_dollars(ctx.policy.max_single_payment_cents)}",
            guardrail="limit",
        )
    if _provider() == "increase":
        try:
            IncreaseClient.require_sandbox(os.environ.get("INCREASE_BASE_URL", ""))
        except SandboxRequired as exc:
            raise PaymentRefused(
                f"{invoice.id}: refusing to pay, {exc}", guardrail="sandbox"
            ) from exc
        if invoice.payment is not None:
            _confirm_returned_with_provider(invoice, invoice.payment)
    return vendor


def _confirm_returned_with_provider(invoice: Invoice, payment: Payment) -> None:
    """A re-send is allowed only if Increase itself says the first transfer failed.

    Our own record saying "returned" is not enough: ask the provider, so a bad
    statement line can never talk ``pay()`` into a second transfer.
    """
    if payment.provider != "increase":
        raise PaymentRefused(
            f"{invoice.id}: refusing to re-pay a {payment.provider} payment through increase",
            guardrail="double_payment",
        )
    client = IncreaseClient.from_env()
    try:
        state = client.get_transfer(payment.transfer_id).get("status")
    finally:
        client.close()
    if state not in FAILED_TRANSFER_STATES:
        raise PaymentRefused(
            f"{invoice.id}: refusing to pay twice, transfer {payment.transfer_id} is {state}",
            guardrail="double_payment",
        )


def pay(invoice: Invoice, ctx: PipelineContext) -> Invoice:
    """Guardrails live here, not in the agent's prompt."""
    watch = Stopwatch()
    trace_id = _trace_id(invoice, "pay")
    messages: list[Message] = [{"role": "user", "content": f"Pay invoice {invoice.id}."}]
    try:
        vendor = _check_guardrails(invoice, ctx)
        key = payment_idempotency_key(invoice)
        messages = _payment_context(invoice, vendor, key)
        _prism_gate(invoice, trace_id, messages, watch)
        payment = _send(invoice, vendor, key)
    except PaymentRefused as exc:
        if exc.guardrail != "prism":
            _record(
                "pay",
                invoice,
                trace_id,
                messages,
                f"REFUSED ({exc.guardrail}): {exc}",
                watch,
                outcome="refused",
                guardrail=exc.guardrail,
            )
        raise
    except IncreaseError as exc:
        _record("pay", invoice, trace_id, messages, f"FAILED: {exc}", watch, outcome="failed")
        raise

    paid = transition(
        invoice.model_copy(update={"payment": payment}), "paid", "pay", payment.transfer_id
    )
    _record(
        "pay",
        invoice,
        trace_id,
        messages,
        f"PAID {_dollars(payment.amount_cents)} to {vendor.name} via {payment.provider}, "
        f"transfer {payment.transfer_id}, status {payment.status}",
        watch,
        outcome="paid",
        provider=payment.provider,
        transfer_id=payment.transfer_id,
        idempotency_key=payment.idempotency_key,
    )
    return paid


def _prism_gate(invoice: Invoice, trace_id: str, messages: list[Message], watch: Stopwatch) -> None:
    """Ask Prism's guardrails; enforce a block. Anything short of a block proceeds."""
    prism = prism_client()
    if prism is None:
        return
    verdict = prism.evaluate(trace_id, messages)
    if not verdict.blocked:
        return
    rule = verdict.rule_name or verdict.rule_type or "rule"
    # Honour the block the way Prism checks for it: the trace goes out under the
    # same trace_id with no output, so its enforcement check reads "honoured".
    prism.trace(
        trace_id,
        invoice.id,
        messages,
        "",
        watch.elapsed_ms,
        metadata={
            "invoice_id": invoice.id,
            "stage": "pay",
            "outcome": "refused",
            "guardrail": "prism",
            "rule": rule,
            "matched_text": verdict.matched_text,
        },
    )
    raise PaymentRefused(
        f"{invoice.id}: refused by Prism guardrail {rule}"
        + (f" ({verdict.matched_text!r})" if verdict.matched_text else ""),
        guardrail="prism",
    )


def _send(invoice: Invoice, vendor: Vendor, idempotency_key: str) -> Payment:
    if _provider() == "increase":
        try:
            return pay_with_increase(invoice, vendor, idempotency_key)
        except SandboxRequired as exc:
            raise PaymentRefused(f"{invoice.id}: {exc}", guardrail="sandbox") from exc
    return Payment(
        provider="mock",
        transfer_id=f"mock_{idempotency_key}",
        amount_cents=invoice.total_cents,
        idempotency_key=idempotency_key,
        status="settled",
        created_at=now_utc(),
    )


# ---------------------------------------------------------------------------
# reconcile


def _simulate_settlement() -> bool:
    return os.environ.get("INCREASE_SIMULATE_SETTLEMENT", "1") not in ("0", "false", "no")


def reconcile(invoice: Invoice, ctx: PipelineContext) -> Invoice:
    """Tie the payment to a bank line. A returned payment goes back to ``approved``."""
    payment = invoice.payment
    if invoice.status != "paid" or payment is None:
        return invoice
    watch = Stopwatch()
    trace_id = _trace_id(invoice, "reconcile")

    txns = ctx.bank_txns
    current = payment
    provider_state: str | None = None
    if payment.provider == "increase":
        client = IncreaseClient.from_env()
        try:
            transfer = client.get_transfer(payment.transfer_id)
            if transfer.get("status") == "pending_submission" and _simulate_settlement():
                transfer = client.settle_in_sandbox(payment.transfer_id)
            elif transfer.get("status") == "submitted" and _simulate_settlement():
                transfer = client.settle_in_sandbox(payment.transfer_id)
            provider_state = transfer.get("status")
            current = payment.model_copy(update={"status": payment_status(transfer)})
            txns = client.bank_txns(
                known_keys={payment.transfer_id: payment.idempotency_key}, resolve_unknown=False
            )
        finally:
            client.close()

    context = [{"role": "user", "content": _reconcile_text(invoice, current, len(txns))}]

    return_line = next(
        (
            t
            for t in txns
            if t.reference == payment.idempotency_key and t.amount_cents == payment.amount_cents
        ),
        None,
    )
    if current.status == "returned" or return_line is not None:
        returned = current.model_copy(update={"status": "returned"})
        note = f"payment {provider_state or 'returned'}" + (
            f" ({return_line.id})" if return_line else ""
        )
        out = transition(
            invoice.model_copy(update={"payment": returned}), "approved", "reconcile", note
        )
        _record(
            "reconcile",
            invoice,
            trace_id,
            context,
            f"RETURNED: transfer {payment.transfer_id} came back; invoice is approved again "
            "and will be paid with a new idempotency key",
            watch,
            outcome="returned",
            transfer_id=payment.transfer_id,
        )
        return out

    # Increase posts the debit line at submission, before settlement. Only a
    # settled transfer is reconciled; a submitted one stays paid and waits.
    settled_enough = payment.provider != "increase" or current.status == "settled"
    txn = next(
        (
            t
            for t in txns
            if settled_enough
            and t.reference == payment.idempotency_key
            and t.amount_cents == -payment.amount_cents
        ),
        None,
    )
    if txn is None:
        _record(
            "reconcile",
            invoice,
            trace_id,
            context,
            f"UNMATCHED: no statement line for {payment.idempotency_key} yet "
            f"(payment status {current.status})",
            watch,
            outcome="unmatched",
        )
        return invoice if current == payment else invoice.model_copy(update={"payment": current})

    reconciliation = Reconciliation(bank_txn_id=txn.id, matched_at=now_utc())
    settled = current.model_copy(update={"status": "settled"})
    out = transition(
        invoice.model_copy(update={"reconciliation": reconciliation, "payment": settled}),
        "reconciled",
        "reconcile",
        txn.id,
    )
    _record(
        "reconcile",
        invoice,
        trace_id,
        context,
        f"RECONCILED: {payment.idempotency_key} matched bank line {txn.id} "
        f"for {_dollars(-txn.amount_cents)}",
        watch,
        outcome="reconciled",
        bank_txn_id=txn.id,
    )
    return out


# ---------------------------------------------------------------------------
# Prism context and recording. No bank account or routing numbers, ever.


def _dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _trace_id(invoice: Invoice, stage: str) -> str:
    return f"{invoice.id}-{stage}-{uuid.uuid4().hex[:8]}"


def _invoice_text(invoice: Invoice) -> str:
    lines = "; ".join(
        f"{line.qty} x {line.description} @ {_dollars(line.unit_price_cents)}"
        for line in invoice.lines
    )
    return (
        f"Invoice {invoice.id} (vendor's number {invoice.invoice_number}) from "
        f"{invoice.vendor_name} [{invoice.vendor_id or 'no vendor on file'}], "
        f"PO {invoice.po_id or 'none'}, dated {invoice.invoice_date}, due {invoice.due_date}, "
        f"total {_dollars(invoice.total_cents)}. Lines: {lines}."
    )


def _approval_context(invoice: Invoice, human: HumanDecision | None) -> list[Message]:
    system = (
        "You are the approval step of an accounts-payable agent. Approve matched invoices "
        "under the auto-approve limit; route larger ones to the approver tier."
    )
    text = _invoice_text(invoice)
    if human is not None:
        text += f" Human decision by {human.approver}: {human.decision}. Reason: {human.reason}"
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def _payment_context(invoice: Invoice, vendor: Vendor, idempotency_key: str) -> list[Message]:
    system = (
        "You are the payment step of an accounts-payable agent. The payee is always the vendor "
        "master record and the amount is always the invoice total. Bank details are never "
        "read from the invoice or from this conversation."
    )
    approval = invoice.approval
    approval_text = (
        f" Approval: {approval.decision} by {approval.approver or 'policy'}: {approval.reason}."
        if approval
        else ""
    )
    text = (
        f"Pay {_dollars(invoice.total_cents)} to vendor {vendor.name} [{vendor.id}] for "
        f"{_invoice_text(invoice)}{approval_text} Idempotency key {idempotency_key}."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def _reconcile_text(invoice: Invoice, payment: Payment, statement_lines: int) -> str:
    return (
        f"Reconcile {invoice.id}: transfer {payment.transfer_id} via {payment.provider}, "
        f"{_dollars(payment.amount_cents)}, idempotency key {payment.idempotency_key}, "
        f"status {payment.status}, against {statement_lines} statement lines."
    )


def _record(
    stage: str,
    invoice: Invoice,
    trace_id: str,
    input_messages: list[Message],
    output: str,
    watch: Stopwatch,
    **metadata: Any,
) -> None:
    client: PrismClient | None = prism_client()
    if client is None:
        return
    client.trace(
        trace_id,
        invoice.id,
        input_messages,
        output,
        watch.elapsed_ms,
        metadata={
            "invoice_id": invoice.id,
            "stage": stage,
            "status_before": invoice.status,
            "vendor_id": invoice.vendor_id,
            "amount_cents": invoice.total_cents,
            **metadata,
        },
    )

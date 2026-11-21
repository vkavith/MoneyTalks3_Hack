"""LANE 4. The "PO to payment" workflow, run step by step for the API and UI.

Phases follow the workflow diagram in docs/workflow.md:

1. Order & receive   purchase order, goods receipt          (seed data)
2. Invoice & match   capture, 3-way match, exceptions       (lanes 1 and 2)
3. Approve & post    approval routed by amount              (lane 3, humans)
4. Pay               payment run through the sandbox        (lane 3)
5. Reconcile & close bank statement vs payment, audit trail (lane 3, lane 4)

Status always comes from the invoice record and its history; nothing here
sets status except the stage functions, which go through ``transition()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ap.intake import capture
from ap.match import match, resolve_exception
from ap.pay import approve, pay, reconcile
from ap.shared import HumanDecision, Invoice, InvoiceStatus, PipelineContext
from ap.shared.load import list_inbox, load_context

PHASES: list[dict[str, Any]] = [
    {"id": "order", "title": "1. Order & receive", "statuses": []},
    {
        "id": "match",
        "title": "2. Invoice & match",
        "statuses": ["received", "captured", "exception"],
    },
    {"id": "approve", "title": "3. Approve & post", "statuses": ["matched", "rejected"]},
    {"id": "pay", "title": "4. Pay", "statuses": ["approved", "paid"]},
    {"id": "close", "title": "5. Reconcile & close", "statuses": ["reconciled"]},
]


def phase_of(status: InvoiceStatus) -> str:
    for phase in PHASES:
        if status in phase["statuses"]:
            return str(phase["id"])
    return "match"


def needs_human(inv: Invoice) -> bool:
    """Yellow boxes in the diagram: exceptions escalated, or approval pending."""
    if inv.status == "matched" and inv.approval is not None:
        return inv.approval.decision == "pending"
    if inv.status == "exception" and inv.match is not None and inv.match.resolution is not None:
        return inv.match.resolution.action == "escalated"
    return False


@dataclass
class Workflow:
    """In-memory store of invoices moving through the workflow."""

    ctx: PipelineContext = field(default_factory=load_context)
    invoices: dict[str, Invoice] = field(default_factory=dict)

    def reset(self) -> None:
        self.ctx = load_context()
        self.invoices = {}

    def inbox(self) -> list[str]:
        return list_inbox()

    def _advance(self, inv: Invoice) -> Invoice:
        """Run the automatic stages until the invoice rests or needs a human."""
        if inv.status == "matched" and inv.approval is None:
            inv = approve(inv, self.ctx)
        if inv.status == "approved":
            inv = pay(inv, self.ctx)
        if inv.status == "paid":
            inv = reconcile(inv, self.ctx)
        return Invoice.model_validate(inv.model_dump())

    def process(self, source_file: str) -> Invoice:
        seen = self.ctx.with_prior(list(self.invoices.values()))
        inv = capture(source_file)
        inv = match(inv, seen)
        if inv.status == "exception":
            inv = resolve_exception(inv, seen)
        inv = self._advance(inv)
        self.invoices[inv.id] = inv
        return inv

    def process_all(self) -> list[Invoice]:
        done = {i.source_file for i in self.invoices.values()}
        return [self.process(f) for f in self.inbox() if f not in done]

    def decide(self, invoice_id: str, decision: HumanDecision) -> Invoice:
        inv = self.invoices[invoice_id]
        if not needs_human(inv) or inv.status != "matched":
            raise ValueError(f"{invoice_id} is not waiting for approval")
        inv = approve(inv, self.ctx, decision)
        inv = self._advance(inv)
        self.invoices[inv.id] = inv
        return inv

    def summary(self, inv: Invoice) -> dict[str, Any]:
        return {
            "id": inv.id,
            "vendor_name": inv.vendor_name,
            "po_id": inv.po_id,
            "total_cents": inv.total_cents,
            "status": inv.status,
            "phase": phase_of(inv.status),
            "needs_human": needs_human(inv),
            "exceptions": [e.code for e in inv.match.exceptions] if inv.match else [],
        }

    def detail(self, invoice_id: str) -> dict[str, Any]:
        inv = self.invoices[invoice_id]
        po = next((p for p in self.ctx.purchase_orders if p.id == inv.po_id), None)
        receipts = [r for r in self.ctx.receipts if po is not None and r.po_id == po.id]
        return {
            "invoice": inv.model_dump(mode="json"),
            "phase": phase_of(inv.status),
            "needs_human": needs_human(inv),
            "purchase_order": po.model_dump(mode="json") if po else None,
            "goods_receipts": [r.model_dump(mode="json") for r in receipts],
            "guardrails": {
                "sandbox": True,
                "auto_approve_limit_cents": self.ctx.policy.auto_approve_limit_cents,
                "max_single_payment_cents": self.ctx.policy.max_single_payment_cents,
                "idempotency_key": inv.payment.idempotency_key if inv.payment else None,
            },
        }

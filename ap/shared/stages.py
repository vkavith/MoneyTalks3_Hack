"""Stage signatures. Each lane implements its functions behind these types.

The orchestrator only ever calls these, so internals are free to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

from .schema import BankTxn, GoodsReceipt, Invoice, Model, Policy, PurchaseOrder, Vendor


@dataclass(frozen=True)
class PipelineContext:
    vendors: list[Vendor]
    purchase_orders: list[PurchaseOrder]
    receipts: list[GoodsReceipt]
    policy: Policy
    bank_txns: list[BankTxn]
    prior_invoices: list[Invoice] = field(default_factory=list)
    """Invoices already seen, for duplicate detection."""

    def with_prior(self, invoices: list[Invoice]) -> PipelineContext:
        return replace(self, prior_invoices=list(invoices))


class HumanDecision(Model):
    approver: str
    decision: Literal["approved", "rejected"]
    reason: str


class CaptureStage(Protocol):
    """Lane 1. File in data/inbox -> Invoice with status "captured"."""

    def __call__(self, source_file: str) -> Invoice: ...


class InvoiceStage(Protocol):
    """Lanes 2 and 3: match, resolve_exception, pay, reconcile.

    match:             captured  -> matched | exception
    resolve_exception: exception -> matched (auto-resolved) | exception (escalated)
    pay:               approved  -> paid
    reconcile:         paid      -> reconciled, or unchanged if no bank line matches yet
    """

    def __call__(self, invoice: Invoice, ctx: PipelineContext) -> Invoice: ...


class ApproveStage(Protocol):
    """Lane 3. matched -> approved | rejected, or stays matched with approval pending."""

    def __call__(
        self, invoice: Invoice, ctx: PipelineContext, human: HumanDecision | None = None
    ) -> Invoice: ...

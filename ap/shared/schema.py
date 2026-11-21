"""THE CONTRACT. Every lane reads and writes these shapes.

Do not change this file in a feature PR. See AGENTS.md, "Changing the contract".

Conventions: money is integer cents (never floats), calendar dates are
``datetime.date``, timestamps are timezone-aware UTC ``datetime``.
Models are frozen: build a changed copy with ``model_copy(update={...})``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Cents = Annotated[int, Field(strict=True)]

InvoiceStatus = Literal[
    "received",
    "captured",
    "matched",
    "exception",
    "approved",
    "rejected",
    "paid",
    "reconciled",
]

ExceptionCode = Literal[
    "PRICE_VARIANCE",
    "QTY_OVER_RECEIPT",
    "MISSING_PO",
    "DUPLICATE_INVOICE",
    "UNKNOWN_VENDOR",
    "TOTAL_MISMATCH",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BankDetails(Model):
    routing_number: str
    account_number: str


class Vendor(Model):
    id: str
    name: str
    email: str
    payment_terms_days: int = Field(gt=0)
    bank: BankDetails
    active: bool


class PoLine(Model):
    line_no: int = Field(gt=0)
    sku: str
    description: str
    qty: int = Field(gt=0)
    unit_price_cents: Cents


class PurchaseOrder(Model):
    id: str
    vendor_id: str
    cost_center: str
    requester: str
    created_at: date
    currency: Literal["USD"]
    lines: list[PoLine] = Field(min_length=1)


class ReceiptLine(Model):
    po_line_no: int = Field(gt=0)
    qty_received: int = Field(ge=0)


class GoodsReceipt(Model):
    id: str
    po_id: str
    received_at: date
    lines: list[ReceiptLine]


class InvoiceLine(Model):
    line_no: int = Field(gt=0)
    po_line_no: int | None
    """Which PO line this bills. None when the invoice quotes no PO."""
    description: str
    qty: int = Field(gt=0)
    unit_price_cents: Cents
    amount_cents: Cents


class MatchException(Model):
    code: ExceptionCode
    line_no: int | None = None
    detail: str
    expected: str | None = None
    actual: str | None = None


class Resolution(Model):
    """Filled by the exception agent (lane 2)."""

    action: Literal["auto_resolved", "escalated"]
    rationale: str
    by: str


class MatchResult(Model):
    outcome: Literal["matched", "exception"]
    exceptions: list[MatchException]
    checked_at: AwareDatetime
    resolution: Resolution | None = None


class Approval(Model):
    decision: Literal["auto_approved", "approved", "rejected", "pending"]
    approver: str | None
    """A person's name once decided, or the role it is waiting on while pending."""
    reason: str
    decided_at: AwareDatetime | None


class Payment(Model):
    provider: Literal["mock", "increase"]
    transfer_id: str
    amount_cents: Cents
    idempotency_key: str
    status: Literal["pending", "submitted", "settled", "returned"]
    created_at: AwareDatetime


class Reconciliation(Model):
    bank_txn_id: str
    matched_at: AwareDatetime


class HistoryEntry(Model):
    at: AwareDatetime
    from_status: InvoiceStatus | None
    to_status: InvoiceStatus
    actor: str
    note: str | None = None


class Invoice(Model):
    """The one record that travels through the whole pipeline."""

    id: str
    source_file: str
    vendor_id: str | None
    """None when the name on the invoice matches no vendor in the master file."""
    vendor_name: str
    po_id: str | None
    invoice_number: str
    invoice_date: date
    due_date: date
    currency: Literal["USD"]
    lines: list[InvoiceLine] = Field(min_length=1)
    subtotal_cents: Cents
    tax_cents: Cents
    total_cents: Cents
    remit_to: BankDetails | None = None
    """Bank details printed on the invoice, if any. Informational only:
    payments always go to the bank details in the vendor master file."""
    status: InvoiceStatus
    match: MatchResult | None = None
    approval: Approval | None = None
    payment: Payment | None = None
    reconciliation: Reconciliation | None = None
    history: list[HistoryEntry]


class BankTxn(Model):
    id: str
    posted_at: date
    amount_cents: Cents
    """Negative = money out."""
    description: str
    reference: str | None
    """Carries the payment idempotency key for payments we originated."""


class ApprovalTier(Model):
    up_to_cents: Cents | None
    approver_role: str


class Policy(Model):
    auto_approve_limit_cents: Cents
    max_single_payment_cents: Cents
    price_tolerance_pct: float = Field(ge=0)
    qty_tolerance_pct: float = Field(ge=0)
    tiers: list[ApprovalTier]
    """First tier whose up_to_cents covers the total wins. None = no ceiling."""


class ExpectedOutcome(Model):
    invoice_id: str
    scenario: str
    demo: str | None
    match_outcome: Literal["matched", "exception"]
    exception_codes: list[ExceptionCode]
    resting_status: InvoiceStatus
    """Where the invoice rests when no human acts."""

from __future__ import annotations

from datetime import UTC, datetime

from .schema import HistoryEntry, Invoice, InvoiceStatus

# The only legal status moves. Change status through transition(), never by hand.
ALLOWED: dict[InvoiceStatus, tuple[InvoiceStatus, ...]] = {
    "received": ("captured",),
    "captured": ("matched", "exception"),
    "exception": ("matched", "rejected"),
    "matched": ("approved", "rejected"),
    "approved": ("paid",),
    # paid -> approved covers a returned payment that must be sent again.
    "paid": ("reconciled", "approved"),
    "rejected": (),
    "reconciled": (),
}


class IllegalTransition(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


def transition(invoice: Invoice, to: InvoiceStatus, actor: str, note: str | None = None) -> Invoice:
    """Return a copy of the invoice in the new status, with a history entry."""
    if to not in ALLOWED[invoice.status]:
        raise IllegalTransition(f"Illegal transition {invoice.status} -> {to} for {invoice.id}")
    entry = HistoryEntry(
        at=now_utc(), from_status=invoice.status, to_status=to, actor=actor, note=note
    )
    return invoice.model_copy(update={"status": to, "history": [*invoice.history, entry]})

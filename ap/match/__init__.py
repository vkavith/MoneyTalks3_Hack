"""LANE 2.

match(): a working deterministic baseline. Extend it, keep the signature.
resolve_exception(): STUB that escalates everything. This is where the agent goes.
"""

from __future__ import annotations

from ap.shared import (
    Invoice,
    MatchException,
    MatchResult,
    PipelineContext,
    Resolution,
    now_utc,
    transition,
)


def _usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def match(invoice: Invoice, ctx: PipelineContext) -> Invoice:
    exceptions: list[MatchException] = []
    policy = ctx.policy

    vendor = next((v for v in ctx.vendors if v.id == invoice.vendor_id and v.active), None)
    if vendor is None:
        exceptions.append(
            MatchException(
                code="UNKNOWN_VENDOR",
                detail=f'No active vendor matches "{invoice.vendor_name}"',
            )
        )

    duplicate = next(
        (
            p
            for p in ctx.prior_invoices
            if p.id != invoice.id
            and invoice.vendor_id is not None
            and p.vendor_id == invoice.vendor_id
            and p.invoice_number == invoice.invoice_number
        ),
        None,
    )
    if duplicate is not None:
        exceptions.append(
            MatchException(
                code="DUPLICATE_INVOICE",
                detail=f"Same vendor and invoice number as {duplicate.id}",
            )
        )

    po = next((p for p in ctx.purchase_orders if p.id == invoice.po_id), None)
    if po is None:
        detail = f"PO {invoice.po_id} not found" if invoice.po_id else "Invoice quotes no PO number"
        exceptions.append(MatchException(code="MISSING_PO", detail=detail))
    else:
        for line in invoice.lines:
            po_line = next((ln for ln in po.lines if ln.line_no == line.po_line_no), None)
            if po_line is None:
                exceptions.append(
                    MatchException(
                        code="MISSING_PO",
                        line_no=line.line_no,
                        detail=f"Line {line.line_no} maps to no line on {po.id}",
                    )
                )
                continue
            if line.unit_price_cents * 100 > po_line.unit_price_cents * (
                100 + policy.price_tolerance_pct
            ):
                exceptions.append(
                    MatchException(
                        code="PRICE_VARIANCE",
                        line_no=line.line_no,
                        detail=f"Unit price above PO by more than {policy.price_tolerance_pct:g}%",
                        expected=_usd(po_line.unit_price_cents),
                        actual=_usd(line.unit_price_cents),
                    )
                )
            received = sum(
                rl.qty_received
                for r in ctx.receipts
                if r.po_id == po.id
                for rl in r.lines
                if rl.po_line_no == po_line.line_no
            )
            if line.qty * 100 > received * (100 + policy.qty_tolerance_pct):
                exceptions.append(
                    MatchException(
                        code="QTY_OVER_RECEIPT",
                        line_no=line.line_no,
                        detail="Invoiced quantity exceeds quantity received",
                        expected=str(received),
                        actual=str(line.qty),
                    )
                )

    lines_ok = all(ln.amount_cents == ln.qty * ln.unit_price_cents for ln in invoice.lines)
    line_sum = sum(ln.amount_cents for ln in invoice.lines)
    if (
        not lines_ok
        or line_sum != invoice.subtotal_cents
        or invoice.subtotal_cents + invoice.tax_cents != invoice.total_cents
    ):
        exceptions.append(
            MatchException(
                code="TOTAL_MISMATCH",
                detail="Line amounts, subtotal, tax and total do not add up",
            )
        )

    result = MatchResult(
        outcome="exception" if exceptions else "matched",
        exceptions=exceptions,
        checked_at=now_utc(),
    )
    return transition(
        invoice.model_copy(update={"match": result}),
        result.outcome,
        "match",
        ", ".join(e.code for e in exceptions) or None,
    )


def resolve_exception(invoice: Invoice, ctx: PipelineContext) -> Invoice:
    if invoice.status != "exception" or invoice.match is None:
        return invoice
    resolution = Resolution(
        action="escalated",
        rationale="Stub: no exception agent yet, so everything goes to a person.",
        by="resolve-stub",
    )
    return invoice.model_copy(
        update={"match": invoice.match.model_copy(update={"resolution": resolution})}
    )

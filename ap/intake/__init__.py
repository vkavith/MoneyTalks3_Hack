"""Capture invoice PDFs into the shared invoice contract."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ap.intake.extraction import CaptureError, PrintedInvoice, extract_pdf
from ap.shared import HistoryEntry, Invoice, InvoiceLine, PipelineContext, now_utc, transition
from ap.shared.load import DATA_DIR, load_context


def _cents(printed: str) -> int:
    return int(Decimal(printed.removeprefix("$").replace(",", "")) * 100)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _invoice(source_file: str, printed: PrintedInvoice, ctx: PipelineContext) -> Invoice:
    vendor_id = next(
        (
            vendor.id
            for vendor in ctx.vendors
            if vendor.name.strip().casefold() == printed.vendor_name.strip().casefold()
        ),
        None,
    )
    po = next((order for order in ctx.purchase_orders if order.id == printed.po_id), None)
    po_lines: dict[str, list[int]] = {}
    if po:
        for po_line in po.lines:
            po_lines.setdefault(_normalize(po_line.description), []).append(po_line.line_no)

    lines = []
    for number, line in enumerate(printed.lines, start=1):
        candidates = po_lines.get(_normalize(line.description), [])
        lines.append(
            InvoiceLine(
                line_no=number,
                po_line_no=candidates[0] if len(candidates) == 1 else None,
                description=line.description,
                qty=line.qty,
                unit_price_cents=_cents(line.unit_price),
                amount_cents=_cents(line.amount),
            )
        )

    return Invoice(
        id=Path(source_file).stem,
        source_file=source_file,
        vendor_id=vendor_id,
        vendor_name=printed.vendor_name,
        po_id=printed.po_id,
        invoice_number=printed.invoice_number,
        invoice_date=date.fromisoformat(printed.invoice_date),
        due_date=date.fromisoformat(printed.due_date),
        currency="USD",
        lines=lines,
        subtotal_cents=_cents(printed.subtotal),
        tax_cents=_cents(printed.tax),
        total_cents=_cents(printed.total),
        remit_to=printed.remit_to,
        status="received",
        history=[
            HistoryEntry(at=now_utc(), from_status=None, to_status="received", actor="intake")
        ],
    )


def capture(source_file: str) -> Invoice:
    path = Path(source_file)
    if path.name != source_file or path.suffix.lower() != ".pdf" or "\\" in source_file:
        raise CaptureError("Expected a PDF file name in the invoice inbox.")
    inbox = (DATA_DIR / "inbox").resolve()
    pdf = (inbox / path).resolve()
    if pdf.parent != inbox:
        raise CaptureError("The invoice PDF must be inside the invoice inbox.")

    printed = extract_pdf(pdf)
    ctx = load_context()
    try:
        invoice = _invoice(source_file, printed, ctx)
    except ValueError:
        raise CaptureError(f"Invoice PDF {source_file} contains invalid dates or fields.") from None
    return transition(invoice, "captured", "capture")

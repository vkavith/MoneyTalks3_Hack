"""Regenerates everything under /data. Deterministic: same output every run.

    python scripts/seed.py

Never hand-edit /data. Change this file, run it, commit both.
All companies, people and bank details below are fictional.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from ap.shared import (
    ApprovalTier,
    BankDetails,
    BankTxn,
    ExceptionCode,
    ExpectedOutcome,
    GoodsReceipt,
    HistoryEntry,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Policy,
    PoLine,
    PurchaseOrder,
    ReceiptLine,
    Vendor,
)

DATA = Path(__file__).resolve().parents[1] / "data"
BUYER = "Meridian Manufacturing Co."
ROUTING = "101050001"


def usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def write_json(path: str, value: BaseModel | list[Any]) -> None:
    full = DATA / path
    full.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, BaseModel):
        payload: Any = value.model_dump(mode="json", exclude_unset=True)
    else:
        payload = [v.model_dump(mode="json", exclude_unset=True) for v in value]
    full.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- master data
def vendor(n: int, name: str, email: str, terms: int) -> Vendor:
    return Vendor(
        id=f"V-{n:03d}",
        name=name,
        email=email,
        payment_terms_days=terms,
        bank=BankDetails(routing_number=ROUTING, account_number=f"98765{n:04d}"),
        active=True,
    )


VENDORS = [
    vendor(1, "Northwind Packaging LLC", "ar@northwind-packaging.example.com", 30),
    vendor(2, "Cascade Industrial Supply", "billing@cascade-industrial.example.com", 30),
    vendor(3, "Brightline Logistics Inc.", "invoices@brightline-logistics.example.com", 15),
    vendor(4, "Summit Office Furnishings", "accounts@summit-office.example.com", 45),
    vendor(5, "Harbor Electrical Wholesale", "ar@harbor-electrical.example.com", 30),
]


def po(
    id: str, vendor_id: str, cost_center: str, requester: str, created: str, *lines: PoLine
) -> PurchaseOrder:
    return PurchaseOrder(
        id=id,
        vendor_id=vendor_id,
        cost_center=cost_center,
        requester=requester,
        created_at=date.fromisoformat(created),
        currency="USD",
        lines=list(lines),
    )


def pl(line_no: int, sku: str, description: str, qty: int, unit_price_cents: int) -> PoLine:
    return PoLine(
        line_no=line_no,
        sku=sku,
        description=description,
        qty=qty,
        unit_price_cents=unit_price_cents,
    )


PURCHASE_ORDERS = [
    po(
        "PO-1001",
        "V-001",
        "OPS-110",
        "Priya Raman",
        "2026-10-01",
        pl(1, "BOX-12", "Corrugated shipping box 12in", 500, 120),
        pl(2, "TAPE-2", "Packing tape 2in, roll", 200, 350),
    ),
    po(
        "PO-1002",
        "V-002",
        "MFG-220",
        "Tomás Ibarra",
        "2026-10-03",
        pl(1, "GLV-CS", "Cut-resistant safety gloves, case", 40, 8500),
    ),
    po(
        "PO-1003",
        "V-004",
        "FAC-300",
        "Hannah Okafor",
        "2026-10-05",
        pl(1, "DSK-SS", "Sit-stand desk, 60in", 60, 80000),
    ),
    po(
        "PO-1004",
        "V-005",
        "FAC-300",
        "Hannah Okafor",
        "2026-10-08",
        pl(1, "LED-P24", "LED panel light 2x4", 100, 4200),
    ),
    po(
        "PO-1005",
        "V-003",
        "OPS-110",
        "Priya Raman",
        "2026-10-10",
        pl(1, "FRT-PLT", "Pallet freight, regional", 10, 25000),
    ),
]


def receipt(id: str, po_id: str, received: str, *qtys: int) -> GoodsReceipt:
    return GoodsReceipt(
        id=id,
        po_id=po_id,
        received_at=date.fromisoformat(received),
        lines=[ReceiptLine(po_line_no=i + 1, qty_received=q) for i, q in enumerate(qtys)],
    )


GOODS_RECEIPTS = [
    receipt("GR-2001", "PO-1001", "2026-10-14", 500, 200),
    receipt("GR-2002", "PO-1002", "2026-10-16", 40),
    receipt("GR-2003", "PO-1003", "2026-10-20", 60),
    receipt("GR-2004", "PO-1004", "2026-10-21", 80),  # short delivery: 80 of 100 arrived
    receipt("GR-2005", "PO-1005", "2026-10-22", 10),
]

POLICY = Policy(
    auto_approve_limit_cents=1_000_000,  # $10,000
    max_single_payment_cents=10_000_000,  # $100,000
    price_tolerance_pct=2,
    qty_tolerance_pct=0,
    tiers=[
        ApprovalTier(up_to_cents=5_000_000, approver_role="finance_manager"),
        ApprovalTier(up_to_cents=None, approver_role="cfo"),
    ],
)


# ------------------------------------------------------------------- invoices
@dataclass
class Line:
    po_line_no: int | None
    description: str
    qty: int
    unit_price_cents: int


@dataclass
class Stranger:
    """A sender that is not in the vendor master file."""

    name: str
    account_number: str
    terms: int


@dataclass
class Spec:
    vendor_id: str | None
    invoice_number: str
    po_id: str | None
    invoice_date: str
    lines: list[Line]
    scenario: str
    match_outcome: InvoiceStatus
    resting_status: InvoiceStatus
    codes: tuple[ExceptionCode, ...] = ()
    demo: str | None = None
    stranger: Stranger | None = None


def po_lines(po_id: str, unit_price_cents: int | None = None) -> list[Line]:
    order = next(p for p in PURCHASE_ORDERS if p.id == po_id)
    return [
        Line(ln.line_no, ln.description, ln.qty, unit_price_cents or ln.unit_price_cents)
        for ln in order.lines
    ]


SPECS = [
    Spec(
        "V-001",
        "NW-88213",
        "PO-1001",
        "2026-10-15",
        po_lines("PO-1001"),
        "Clean match, under the limit",
        "matched",
        "reconciled",
        demo="A: touchless, straight through to paid",
    ),
    Spec(
        "V-002",
        "CI-40117",
        "PO-1002",
        "2026-10-17",
        po_lines("PO-1002", 8925),
        "Unit price 5% above PO",
        "exception",
        "exception",
        ("PRICE_VARIANCE",),
        demo="B: agent explains and resolves or escalates",
    ),
    Spec(
        "V-004",
        "SOF-2291",
        "PO-1003",
        "2026-10-21",
        po_lines("PO-1003"),
        "Clean match, $48,000 is over the auto-approve limit",
        "matched",
        "matched",
        demo="C: pauses for a human click, then pays",
    ),
    Spec(
        "V-005",
        "HE-7730",
        "PO-1004",
        "2026-10-22",
        po_lines("PO-1004"),
        "Billed 100, only 80 received",
        "exception",
        "exception",
        ("QTY_OVER_RECEIPT",),
    ),
    Spec(
        "V-001",
        "NW-88213",
        "PO-1001",
        "2026-10-15",
        po_lines("PO-1001"),
        "Second copy of INV-0001",
        "exception",
        "exception",
        ("DUPLICATE_INVOICE",),
    ),
    Spec(
        "V-003",
        "BL-5521",
        None,
        "2026-10-23",
        [Line(None, "Expedited freight surcharge", 3, 40000)],
        "No PO number on the invoice",
        "exception",
        "exception",
        ("MISSING_PO",),
    ),
    Spec(
        "V-003",
        "BL-5507",
        "PO-1005",
        "2026-10-23",
        po_lines("PO-1005", 25200),
        "Unit price 0.8% above PO, inside tolerance",
        "matched",
        "reconciled",
    ),
    Spec(
        None,
        "NW-88290",
        "PO-1001",
        "2026-10-24",
        po_lines("PO-1001"),
        "Look-alike vendor name with different bank details",
        "exception",
        "exception",
        ("UNKNOWN_VENDOR",),
        stranger=Stranger("Nortwind Packaging LLC", "555000999", 30),
    ),
]


def build_invoice(n: int, spec: Spec) -> Invoice:
    inv_id = f"INV-{n:04d}"
    known = next((v for v in VENDORS if v.id == spec.vendor_id), None)
    if known is not None:
        name, bank, terms = known.name, known.bank, known.payment_terms_days
    else:
        assert spec.stranger is not None
        name = spec.stranger.name
        bank = BankDetails(routing_number=ROUTING, account_number=spec.stranger.account_number)
        terms = spec.stranger.terms
    lines = [
        InvoiceLine(
            line_no=i + 1,
            po_line_no=ln.po_line_no,
            description=ln.description,
            qty=ln.qty,
            unit_price_cents=ln.unit_price_cents,
            amount_cents=ln.qty * ln.unit_price_cents,
        )
        for i, ln in enumerate(spec.lines)
    ]
    subtotal = sum(ln.amount_cents for ln in lines)
    invoice_date = date.fromisoformat(spec.invoice_date)
    return Invoice(
        id=inv_id,
        source_file=f"{inv_id}.pdf",
        vendor_id=known.id if known else None,
        vendor_name=name,
        po_id=spec.po_id,
        invoice_number=spec.invoice_number,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=terms),
        currency="USD",
        lines=lines,
        subtotal_cents=subtotal,
        tax_cents=0,
        total_cents=subtotal,
        remit_to=bank,
        status="captured",
        history=[
            HistoryEntry(
                at=datetime.combine(invoice_date, time(15), tzinfo=UTC),
                from_status="received",
                to_status="captured",
                actor="seed",
            )
        ],
    )


INVOICES = [build_invoice(i + 1, s) for i, s in enumerate(SPECS)]

OUTCOMES = [
    ExpectedOutcome(
        invoice_id=inv.id,
        scenario=s.scenario,
        demo=s.demo,
        match_outcome="matched" if s.match_outcome == "matched" else "exception",
        exception_codes=list(s.codes),
        resting_status=s.resting_status,
    )
    for inv, s in zip(INVOICES, SPECS, strict=True)
]


def bank_line(id: str, posted: str, description: str, paid_invoice: int) -> BankTxn:
    inv = INVOICES[paid_invoice - 1]
    return BankTxn(
        id=id,
        posted_at=date.fromisoformat(posted),
        amount_cents=-inv.total_cents,
        description=description,
        reference=f"ap-{inv.id}",
    )


# Statement lines for the payments the pipeline makes in mock mode, plus noise.
BANK_STATEMENT = [
    bank_line("BT-9001", "2026-11-10", "ACH NORTHWIND PACKAGING", 1),
    bank_line("BT-9002", "2026-11-10", "ACH BRIGHTLINE LOGISTICS", 7),
    bank_line("BT-9003", "2026-11-12", "ACH SUMMIT OFFICE FURN", 3),
    BankTxn(
        id="BT-9004",
        posted_at=date(2026, 11, 13),
        amount_cents=-1_875_000,
        description="PAYROLL",
        reference=None,
    ),
    BankTxn(
        id="BT-9005",
        posted_at=date(2026, 11, 13),
        amount_cents=500_000,
        description="CUSTOMER DEPOSIT",
        reference=None,
    ),
]


# ------------------------------------------------------------------------ PDFs
def write_pdf(inv: Invoice) -> None:
    # invariant=1 keeps the file byte-identical between runs.
    c = canvas.Canvas(str(DATA / "inbox" / inv.source_file), pagesize=LETTER, invariant=1)
    c.setTitle(f"Invoice {inv.invoice_number}")
    left, right = 54, 558
    y = 738.0

    c.setFont("Helvetica", 18)
    c.drawString(left, y, inv.vendor_name)
    c.setFont("Helvetica", 24)
    c.drawRightString(right, y - 36, "INVOICE")

    c.setFont("Helvetica", 10)
    y -= 72
    header = [
        f"Invoice number: {inv.invoice_number}",
        f"Invoice date: {inv.invoice_date.isoformat()}",
        f"Due date: {inv.due_date.isoformat()}",
    ]
    if inv.po_id:
        header.append(f"PO number: {inv.po_id}")
    for text in header:
        c.drawString(left, y, text)
        y -= 14
    y -= 8
    c.drawString(left, y, f"Bill to: {BUYER}")

    cols = [left, 300, 370, 460]
    y -= 36
    c.setFont("Helvetica-Bold", 10)
    for x, title in zip(cols, ["Description", "Qty", "Unit price", "Amount"], strict=True):
        c.drawString(x, y, title)
    c.setFont("Helvetica", 10)
    for ln in inv.lines:
        y -= 20
        c.drawString(cols[0], y, ln.description)
        c.drawString(cols[1], y, str(ln.qty))
        c.drawString(cols[2], y, usd(ln.unit_price_cents))
        c.drawString(cols[3], y, usd(ln.amount_cents))

    y -= 36
    c.drawString(cols[2], y, f"Subtotal: {usd(inv.subtotal_cents)}")
    c.drawString(cols[2], y - 16, f"Tax: {usd(inv.tax_cents)}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(cols[2], y - 32, f"Total due: {usd(inv.total_cents)}")
    c.setFont("Helvetica", 10)
    if inv.remit_to:
        c.drawString(
            left,
            y - 72,
            f"Remit by ACH to routing {inv.remit_to.routing_number}, "
            f"account {inv.remit_to.account_number}",
        )
    c.showPage()
    c.save()


# ----------------------------------------------------------------------- write
def main() -> None:
    for folder in ("inbox", "expected"):
        shutil.rmtree(DATA / folder, ignore_errors=True)
    (DATA / "inbox").mkdir(parents=True)

    write_json("vendors.json", VENDORS)
    write_json("purchase_orders.json", PURCHASE_ORDERS)
    write_json("goods_receipts.json", GOODS_RECEIPTS)
    write_json("policy.json", POLICY)
    write_json("bank_statement.json", BANK_STATEMENT)
    write_json("expected/outcomes.json", OUTCOMES)
    for inv in INVOICES:
        write_json(f"expected/captured/{inv.id}.json", inv)
        write_pdf(inv)
    print(f"Seeded {len(INVOICES)} invoices into {DATA}")


if __name__ == "__main__":
    main()

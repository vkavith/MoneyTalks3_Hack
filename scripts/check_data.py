"""Validates /data against the contract: schemas, references and arithmetic.

python scripts/check_data.py
"""

from __future__ import annotations

import sys

from ap.shared.load import (
    DATA_DIR,
    list_inbox,
    load_captured_fixture,
    load_context,
    load_expected_outcomes,
)


def main() -> int:
    errors: list[str] = []
    ctx = load_context()  # raises if any file breaks its schema
    vendor_ids = {v.id for v in ctx.vendors}
    po_by_id = {p.id: p for p in ctx.purchase_orders}

    for po in ctx.purchase_orders:
        if po.vendor_id not in vendor_ids:
            errors.append(f"{po.id}: unknown vendor {po.vendor_id}")
    for gr in ctx.receipts:
        order = po_by_id.get(gr.po_id)
        if order is None:
            errors.append(f"{gr.id}: unknown PO {gr.po_id}")
            continue
        po_line_nos = {ln.line_no for ln in order.lines}
        for rl in gr.lines:
            if rl.po_line_no not in po_line_nos:
                errors.append(f"{gr.id}: no line {rl.po_line_no} on {order.id}")

    inbox = list_inbox()
    outcomes = load_expected_outcomes()
    outcome_ids = {o.invoice_id for o in outcomes}
    for file in inbox:
        inv = load_captured_fixture(file)
        if inv.source_file != file:
            errors.append(f"{inv.id}: source_file is not {file}")
        if inv.vendor_id and inv.vendor_id not in vendor_ids:
            errors.append(f"{inv.id}: unknown vendor")
        if inv.po_id and inv.po_id not in po_by_id:
            errors.append(f"{inv.id}: unknown PO")
        if any(ln.amount_cents != ln.qty * ln.unit_price_cents for ln in inv.lines):
            errors.append(f"{inv.id}: a line amount is not qty x unit price")
        if sum(ln.amount_cents for ln in inv.lines) != inv.subtotal_cents:
            errors.append(f"{inv.id}: subtotal does not equal line sum")
        if inv.subtotal_cents + inv.tax_cents != inv.total_cents:
            errors.append(f"{inv.id}: total is off")
        if inv.id not in outcome_ids:
            errors.append(f"{inv.id}: no expected outcome")
    for o in outcomes:
        if not (DATA_DIR / "inbox" / f"{o.invoice_id}.pdf").exists():
            errors.append(f"{o.invoice_id}: expected outcome without a PDF in inbox")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"Data OK: {len(ctx.vendors)} vendors, {len(ctx.purchase_orders)} POs, "
        f"{len(ctx.receipts)} receipts, {len(inbox)} invoices, {len(ctx.bank_txns)} bank lines."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

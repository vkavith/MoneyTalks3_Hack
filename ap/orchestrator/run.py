"""LANE 4. Walking skeleton: runs every inbox invoice through every stage
and checks the result against data/expected/outcomes.json.

    python -m ap.orchestrator.run
    python -m ap.orchestrator.run --approve INV-0003     (simulate a human approval)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Collection

from ap.intake import capture
from ap.match import match, resolve_exception
from ap.pay import approve, pay, reconcile
from ap.shared import HumanDecision, Invoice
from ap.shared.load import list_inbox, load_context, load_expected_outcomes


def run_pipeline(human_approvals: Collection[str] = ()) -> list[Invoice]:
    ctx = load_context()
    done: list[Invoice] = []

    for file in list_inbox():
        seen = ctx.with_prior(done)
        inv = capture(file)
        inv = match(inv, seen)
        if inv.status == "exception":
            inv = resolve_exception(inv, seen)
        if inv.status == "matched":
            inv = approve(inv, ctx)
            pending = inv.approval is not None and inv.approval.decision == "pending"
            if pending and inv.id in human_approvals:
                decision = HumanDecision(
                    approver="demo-approver",
                    decision="approved",
                    reason="Approved from the command line",
                )
                inv = approve(inv, ctx, decision)
        if inv.status == "approved":
            inv = pay(inv, ctx)
        if inv.status == "paid":
            inv = reconcile(inv, ctx)
        # Round-trip through validation so a stage cannot smuggle in a bad shape.
        done.append(Invoice.model_validate(inv.model_dump()))
    return done


def compare(results: list[Invoice], human_approvals: Collection[str] = ()) -> list[dict[str, str]]:
    """One row per invoice, with ok = "yes" when it matches the expected outcome."""
    expected = {e.invoice_id: e for e in load_expected_outcomes()}
    rows = []
    for inv in results:
        exp = expected.get(inv.id)
        codes = sorted({e.code for e in inv.match.exceptions}) if inv.match else []
        ok = (
            exp is not None
            and codes == sorted(exp.exception_codes)
            and (inv.id in human_approvals or inv.status == exp.resting_status)
        )
        rows.append(
            {
                "invoice": inv.id,
                "status": inv.status,
                "exceptions": ",".join(codes) or "-",
                "approval": inv.approval.decision if inv.approval else "-",
                "ok": "yes" if ok else "NO",
                "scenario": exp.scenario if exp else "?",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", action="append", default=[], metavar="INVOICE_ID")
    args = parser.parse_args()

    rows = compare(run_pipeline(args.approve), args.approve)
    widths = {k: max(len(k), *(len(r[k]) for r in rows)) for k in rows[0]}
    print("  ".join(k.ljust(widths[k]) for k in widths))
    for r in rows:
        print("  ".join(r[k].ljust(widths[k]) for k in widths))

    failures = sum(r["ok"] != "yes" for r in rows)
    if failures:
        print(f"{failures} invoice(s) differ from data/expected/outcomes.json", file=sys.stderr)
        return 1
    print("Pipeline matches expected outcomes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

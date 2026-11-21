"""Lane 3 demo against the Increase sandbox, with Prism recording every step.

    python -m ap.pay.demo setup            # create + fund a sandbox account; prints the .env line
    python -m ap.pay.demo pay INV-0001     # approve -> pay (ACH) -> settle -> reconcile
    python -m ap.pay.demo pay INV-0003 --approve "Jane Doe"   # over the limit: human approves
    python -m ap.pay.demo return INV-0007  # pay, simulate a return, re-pay with a new key
    python -m ap.pay.demo refuse INV-0001  # show the guardrails refusing bad requests

Reads .env itself so the keys never need to be exported by hand. Sandbox only.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ap.shared import HumanDecision, Invoice, PipelineContext, transition
from ap.shared.load import load_captured_fixture, load_context

from . import PaymentRefused, approve, pay, reconcile
from .increase import IncreaseClient
from .prism import PrismConfig


def load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=value lines, no overrides of the real environment."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def show(invoice: Invoice) -> None:
    print(f"\n{invoice.id}: status={invoice.status}")
    if invoice.approval:
        print(f"  approval: {invoice.approval.decision} ({invoice.approval.approver})")
    if invoice.payment:
        p = invoice.payment
        print(
            f"  payment:  {p.provider} {p.transfer_id} ${p.amount_cents / 100:,.2f} "
            f"key={p.idempotency_key} status={p.status}"
        )
    if invoice.reconciliation:
        print(f"  reconciled to bank line {invoice.reconciliation.bank_txn_id}")
    print("  history:")
    for h in invoice.history:
        print(
            f"    {h.at:%H:%M:%S} {h.from_status or '-':>10} -> {h.to_status:<10} "
            f"{h.actor}  {h.note or ''}"
        )


def matched(invoice_id: str) -> Invoice:
    """The captured fixture moved to matched, standing in for lanes 1 and 2."""
    inv = load_captured_fixture(f"{invoice_id}.pdf")
    return transition(inv, "matched", "demo:lane3", "stand-in for match()")


def approved(invoice_id: str, ctx: PipelineContext, approver: str | None) -> Invoice:
    inv = approve(matched(invoice_id), ctx)
    if inv.status != "approved" and approver:
        human = HumanDecision(approver=approver, decision="approved", reason="Approved in the demo")
        inv = approve(inv, ctx, human)
    return inv


def cmd_setup(_: argparse.Namespace) -> int:
    client = IncreaseClient.from_env()
    try:
        ids = client.setup_sandbox()
    finally:
        client.close()
    print("Sandbox account created and funded with $1,000,000.00 by a simulated wire.")
    print(f"Add this line to .env:\n\nINCREASE_ACCOUNT_ID={ids['INCREASE_ACCOUNT_ID']}\n")
    return 0


def cmd_pay(args: argparse.Namespace) -> int:
    ctx = load_context()
    inv = approved(args.invoice, ctx, args.approve)
    show(inv)
    if inv.status != "approved":
        print("\nStill waiting on a human. Re-run with --approve <name>.")
        return 1
    inv = pay(inv, ctx)
    show(inv)
    inv = reconcile(inv, ctx)
    show(inv)
    return 0 if inv.status == "reconciled" else 1


def cmd_return(args: argparse.Namespace) -> int:
    ctx = load_context()
    inv = pay(approved(args.invoice, ctx, args.approve), ctx)
    assert inv.payment is not None
    show(inv)
    client = IncreaseClient.from_env()
    try:
        client.settle_in_sandbox(inv.payment.transfer_id)
        client.simulate_return(inv.payment.transfer_id, reason="account_closed")
    finally:
        client.close()
    print("\n(simulated: the receiving bank returned the transfer)")
    inv = reconcile(inv, ctx)
    show(inv)
    print("\nPaying again with a fresh idempotency key...")
    inv = pay(inv, ctx)
    inv = reconcile(inv, ctx)
    show(inv)
    return 0 if inv.status == "reconciled" else 1


def cmd_refuse(args: argparse.Namespace) -> int:
    ctx = load_context()
    inv = approved(args.invoice, ctx, args.approve)
    attempts = {
        "not approved": matched(args.invoice),
        "over the single-payment limit": inv.model_copy(
            update={"total_cents": ctx.policy.max_single_payment_cents + 1}
        ),
        "vendor not on file": inv.model_copy(update={"vendor_id": "V-999"}),
    }
    paid = pay(inv, ctx)
    attempts["already paid"] = paid
    for label, candidate in attempts.items():
        try:
            pay(candidate, ctx)
            print(f"  {label:32} PAID (unexpected!)")
        except PaymentRefused as exc:
            print(f"  {label:32} refused [{exc.guardrail}] {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    os.environ["PAYMENT_PROVIDER"] = "increase"  # this demo is the sandbox, never the mock
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    for name, func in (("pay", cmd_pay), ("return", cmd_return), ("refuse", cmd_refuse)):
        p = sub.add_parser(name)
        p.add_argument("invoice")
        p.add_argument("--approve", metavar="NAME", help="human approver for over-limit invoices")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    prism = PrismConfig.from_env()
    print(
        f"provider={os.environ['PAYMENT_PROVIDER']} base={os.environ.get('INCREASE_BASE_URL')} "
        f"prism={'on, project ' + prism.project_id if prism else 'off'}"
    )
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())

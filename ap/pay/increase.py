"""LANE 3 TODO: send an ACH credit through the Increase SANDBOX.

Read the current docs before writing this; do not guess field names.
    https://increase.com/documentation/sandbox
    https://increase.com/documentation/sending-ach-transfers
    https://increase.com/documentation/api

Requirements:
- Base URL from INCREASE_BASE_URL, which must be the sandbox host.
- Pass idempotency_key as the request's idempotency key.
- Amount and bank details come from the arguments below, nothing else.
- Use the sandbox simulation endpoints to settle (and, for the demo, return) a transfer.
"""

from __future__ import annotations

import os

from ap.shared import Invoice, Payment, Vendor


def pay_with_increase(invoice: Invoice, vendor: Vendor, idempotency_key: str) -> Payment:
    base = os.environ.get("INCREASE_BASE_URL", "")
    if "sandbox" not in base:
        raise RuntimeError("INCREASE_BASE_URL must point at the Increase sandbox")
    raise NotImplementedError("Increase provider not implemented yet (lane 3)")

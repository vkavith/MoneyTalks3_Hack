"""Build a finance review from read-only match evidence."""

from __future__ import annotations

import json
import os
from difflib import get_close_matches
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

from ap.shared import Invoice, MatchException, PipelineContext, Resolution


class ReviewDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

    summary: str = Field(min_length=1, max_length=600)


def _draft_with_nicrron(evidence: list[str], key: str, model: str) -> ReviewDraft:
    base_url = os.environ.get("NICRRON_BASE_URL", "https://api.nicrron.ai/v1")
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Write a short note to a finance reviewer using only the given "
                            "evidence. The invoice is held for review. Include the proposed "
                            "question if there is one. Do not invent facts or claim any "
                            "approval, payment, or other action has happened. Return JSON "
                            "with a single string field named summary."
                        ),
                    },
                    {"role": "user", "content": json.dumps(evidence)},
                ],
            }
        ).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        body = json.load(response)
    return ReviewDraft.model_validate_json(body["choices"][0]["message"]["content"])


def _vendor_warning(invoice: Invoice, ctx: PipelineContext) -> str:
    active = {vendor.name.casefold(): vendor for vendor in ctx.vendors if vendor.active}
    similar = get_close_matches(invoice.vendor_name.casefold(), active, n=1, cutoff=0.85)
    warning = "UNKNOWN_VENDOR: Possible fraud. No active vendor matches the invoice."
    if similar:
        vendor = active[similar[0]]
        warning += " The invoice name resembles an active vendor."
        if invoice.remit_to is not None and invoice.remit_to != vendor.bank:
            warning += " The invoice bank details differ from that vendor's master record."
    return f"{warning} Verify the vendor through an established contact before payment."


def _evidence(issue: MatchException, invoice: Invoice, ctx: PipelineContext) -> str:
    if issue.code == "PRICE_VARIANCE":
        return (
            f"PRICE_VARIANCE: Line {issue.line_no} bills {issue.actual} per unit versus "
            f"{issue.expected} on the PO, above the {ctx.policy.price_tolerance_pct:g}% "
            "tolerance. Buyer draft: Can you confirm whether the billed unit price was "
            "authorized or request a corrected invoice?"
        )
    if issue.code == "QTY_OVER_RECEIPT":
        return (
            f"QTY_OVER_RECEIPT: Line {issue.line_no} bills {issue.actual} units, with "
            f"{issue.expected} received. Confirm the receipt before considering a short pay."
        )
    if issue.code == "DUPLICATE_INVOICE":
        return "DUPLICATE_INVOICE: The same vendor and invoice number were already processed."
    if issue.code == "MISSING_PO":
        candidates = sum(1 for po in ctx.purchase_orders if po.vendor_id == invoice.vendor_id)
        return (
            f"MISSING_PO: The invoice or line could not be matched to a PO. "
            f"There are {candidates} POs for this vendor in the records. "
            "Ask the buyer to confirm the correct PO and line."
        )
    line_sum = sum(line.amount_cents for line in invoice.lines)
    return (
        f"TOTAL_MISMATCH: Line amounts sum to {line_sum} cents. The invoice lists a subtotal "
        f"of {invoice.subtotal_cents} cents, tax of {invoice.tax_cents} cents, and a total of "
        f"{invoice.total_cents} cents. Verify line extensions and totals before approval."
    )


def investigate(
    invoice: Invoice, ctx: PipelineContext, exceptions: list[MatchException]
) -> Resolution:
    if any(issue.code == "UNKNOWN_VENDOR" for issue in exceptions):
        return Resolution(action="escalated", rationale=_vendor_warning(invoice, ctx), by="match")

    evidence = [_evidence(issue, invoice, ctx) for issue in exceptions]
    rationale = " ".join(evidence) or "The invoice is held for review without match evidence."
    key = os.environ.get("NICRRON_API_KEY")
    if key and evidence:
        model = os.environ.get("NICRRON_MODEL", "anthropic/claude-sonnet-5-5")
        try:
            draft = _draft_with_nicrron(evidence, key, model)
        except (URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
            pass
        else:
            return Resolution(
                action="escalated",
                rationale=f"{rationale}\n\nNicrron draft: {draft.summary}",
                by=f"nicrron:{model}",
            )

    return Resolution(action="escalated", rationale=rationale, by="match")

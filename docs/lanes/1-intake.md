# Lane 1: Intake

**Owner:** _name_

## Mission

Turn an invoice PDF into a correct, structured `Invoice` with status `captured`.

## You own

`ap/intake/` and `tests/intake/`. Your one public function is `capture(source_file: str) -> Invoice`.

## Inputs and outputs

- **In:** a file name in `data/inbox/`, for example `INV-0001.pdf`.
- **Out:** a valid `Invoice` with status `captured` and no `match`, `approval` or `payment` sections.
- **Ground truth:** `data/expected/captured/INV-000N.json`, loaded with `load_captured_fixture`. Your output should equal it, ignoring `history` timestamps.

## How to build it

1. **Define an extraction model.** In `ap/intake/`, write a small Pydantic model for what the model should return: the header fields and lines as printed, with amounts as strings or dollars. This is your internal shape; it is not the contract.
2. **Extract.** Send the PDF to a model that reads documents and ask for output matching that model. Validate the reply with Pydantic and retry once on failure.
3. **Normalize.** Convert dollar amounts to integer cents (parse with `Decimal`, then convert; never go through `float`) and dates to `datetime.date`. Compute nothing the invoice states: take subtotal, tax and total as printed, so a bad invoice is caught downstream as `TOTAL_MISMATCH`.
4. **Resolve the vendor.** Look the printed name up in `vendors.json`. Exact match after trimming and case-folding gives `vendor_id`; anything else gives `None`. Do not fuzzy-match: INV-0008 is a deliberate look-alike ("Nortwind") and must come out as `vendor_id=None`.
5. **Map lines to the PO.** If the invoice quotes a PO, set each line's `po_line_no` by matching the description to the PO's lines. With no PO, use `None`.
6. **Record `remit_to`** from the bank details printed on the invoice.
7. **Set the status** by building the record as `received` and calling `transition(inv, "captured", "capture")`, so the history starts correctly.
8. **Test** every inbox file against its fixture in `tests/intake/`. Mark tests that call a model with a pytest marker and skip them when no API key is set, so CI stays green without one.

## Done when

- All 8 inbox PDFs produce output equal to their fixtures.
- The stub that reads `data/expected/` is gone from `ap/intake/__init__.py`.
- A malformed or unreadable PDF raises a clear error and does not return a half-filled invoice.

## Stretch

- Accept invoices from an email inbox or an upload endpoint (coordinate the endpoint with lane 4).
- Return a confidence value per field. This needs a contract change, so ask lane 4 first.
- Handle a scanned, image-only PDF.

## Kickoff prompt

Paste this into your coding agent:

```
You are working in lane 1 (Intake) of a 4-person hackathon repo. The project is Python.

First read AGENTS.md, docs/contract.md and docs/lanes/1-intake.md. Then set up
the virtual environment, run `pip install -e ".[dev]"` and `python scripts/check.py`,
and confirm the check passes.

Your task: replace the stub in ap/intake/__init__.py with a real
capture(source_file) that reads the PDF in data/inbox and returns an Invoice
with status "captured", following the steps in the lane brief.

Rules that matter most:
- Edit only ap/intake/ and tests/intake/. If you need anything changed elsewhere, stop and tell me.
- Import all models from ap.shared. Keep the capture signature unchanged.
- Test against data/expected/captured/ and never modify anything under data/.
- Money is integer cents; never pass an amount through float.
- Do not fuzzy-match vendor names.
- Read the model provider's current docs before writing the PDF extraction call.
- Run `python scripts/check.py` before every commit. Work on a branch named lane1/<topic>.

Start by showing me your plan in five lines or fewer, then build it.
```

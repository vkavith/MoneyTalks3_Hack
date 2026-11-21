# Lane 1: Intake

**Owner:** _name_

## Mission

Turn an invoice PDF into a correct, structured `Invoice` with status `captured`.

## You own

`packages/intake/`. Your one exported function is `capture(sourceFile)`.

## Inputs and outputs

- **In:** a file name in `data/inbox/`, for example `INV-0001.pdf`.
- **Out:** an `Invoice` that passes `Invoice.parse()`, with status `captured` and no `match`, `approval` or `payment` sections.
- **Ground truth:** `data/expected/captured/INV-000N.json`. Your output should equal it, ignoring `history` timestamps.

## How to build it

1. **Extract.** Send the PDF to a model that reads documents and ask for JSON in the shape of the header and line fields. Validate the reply with the zod schema and retry once on failure.
2. **Normalize.** Convert dollar amounts to integer cents and dates to `YYYY-MM-DD`. Compute nothing the invoice states: take `subtotal`, `tax` and `total` as printed, so a bad invoice is caught downstream as `TOTAL_MISMATCH`.
3. **Resolve the vendor.** Look the printed name up in `vendors.json`. Exact match after trimming and case-folding gives `vendor_id`; anything else gives `null`. Do not fuzzy-match: INV-0008 is a deliberate look-alike ("Nortwind") and must come out as `vendor_id: null`.
4. **Map lines to the PO.** If the invoice quotes a PO, set each line's `po_line_no` by matching the description to the PO's lines. With no PO, use `null`.
5. **Record `remit_to`** from the bank details printed on the invoice.
6. **Set the status** with `transition()` from a `received` record, so the history starts correctly.
7. **Test** every inbox file against its fixture. Add a test script to your package and keep `npm run check` green.

## Done when

- All 8 inbox PDFs produce output equal to their fixtures.
- The stub that reads `data/expected/` is gone from `packages/intake/src/index.ts`.
- A malformed or unreadable PDF throws a clear error and does not return a half-filled invoice.

## Stretch

- Accept invoices from an email inbox or an upload endpoint (coordinate the endpoint with lane 4).
- Return a confidence value per field. This needs a contract change, so ask lane 4 first.
- Handle a scanned, image-only PDF.

## Kickoff prompt

Paste this into your coding agent:

```
You are working in lane 1 (Intake) of a 4-person hackathon repo.

First read AGENTS.md, docs/contract.md and docs/lanes/1-intake.md, then run
`npm install && npm run check` and confirm it passes.

Your task: replace the stub in packages/intake/src/index.ts with a real
capture(sourceFile) that reads the PDF in data/inbox and returns an Invoice
with status "captured", following the steps in the lane brief.

Rules that matter most:
- Edit only packages/intake/. If you need anything changed elsewhere, stop and tell me.
- Import all types and schemas from @ap/shared. Keep the capture signature unchanged.
- Test against data/expected/captured/ and never modify anything under data/.
- Do not fuzzy-match vendor names.
- Read the model provider's current docs before writing the PDF extraction call.
- Run `npm run check` before every commit. Work on a branch named lane1/<topic>.

Start by showing me your plan in five lines or fewer, then build it.
```

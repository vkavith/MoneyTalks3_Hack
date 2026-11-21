# The contract

The code in `packages/shared/src/` is the source of truth. This page explains it.

## One record

A single `Invoice` object travels through the whole pipeline. Each stage takes it, adds its own section and returns a new copy.

| Section | Written by | Contains |
|---|---|---|
| header and `lines` | `capture` (lane 1) | vendor, PO number, invoice number, dates, line items, totals, `remit_to` |
| `match` | `match`, `resolveException` (lane 2) | outcome, list of exceptions, the agent's resolution |
| `approval` | `approve` (lane 3) | decision, approver, reason |
| `payment` | `pay` (lane 3) | provider, transfer ID, amount, idempotency key, status |
| `reconciliation` | `reconcile` (lane 3) | the bank line it was tied to |
| `history` | `transition()` | every status change, with time, actor and note |

`history` is the audit trail the UI shows. You get it for free by using `transition()`.

## Statuses

```
received -> captured -> matched ---------> approved -> paid -> reconciled
                     \-> exception -> matched
```

| From | To | Who |
|---|---|---|
| `received` | `captured` | lane 1 |
| `captured` | `matched`, `exception` | lane 2 |
| `exception` | `matched` (resolved), `rejected` | lane 2, or a person |
| `matched` | `approved`, `rejected` | lane 3, or a person |
| `approved` | `paid` | lane 3 |
| `paid` | `reconciled`; `approved` if the payment was returned | lane 3 |

An invoice waiting for a human approver stays `matched` with `approval.decision = "pending"`.
An invoice the agent could not resolve stays `exception` with `match.resolution.action = "escalated"`.

## Stage functions

Signatures are in `packages/shared/src/stages.ts`.

| Function | Package | In | Out |
|---|---|---|---|
| `capture(sourceFile)` | `@ap/intake` | file name in `data/inbox` | `captured` |
| `match(invoice, ctx)` | `@ap/match` | `captured` | `matched` or `exception` |
| `resolveException(invoice, ctx)` | `@ap/match` | `exception` | `matched`, or `exception` escalated |
| `approve(invoice, ctx, human?)` | `@ap/pay` | `matched` | `approved`, `rejected`, or `matched` pending |
| `pay(invoice, ctx)` | `@ap/pay` | `approved` | `paid` |
| `reconcile(invoice, ctx)` | `@ap/pay` | `paid` | `reconciled`, or unchanged |

`ctx` is a `PipelineContext`: vendors, purchase orders, goods receipts, policy, invoices already processed, and bank statement lines.

## Exception codes

| Code | Meaning |
|---|---|
| `PRICE_VARIANCE` | Unit price above the PO by more than `policy.price_tolerance_pct` |
| `QTY_OVER_RECEIPT` | Billed more than was received |
| `MISSING_PO` | No PO number, PO not found, or a line maps to no PO line |
| `DUPLICATE_INVOICE` | Same vendor and invoice number as one already seen |
| `UNKNOWN_VENDOR` | Vendor name matches no active vendor in the master file |
| `TOTAL_MISMATCH` | Line amounts, subtotal, tax and total do not add up |

## Conventions

- Money is integer cents. `total_cents: 130000` is $1,300.00.
- Dates are `YYYY-MM-DD`. Timestamps are ISO 8601 UTC.
- IDs: `V-001`, `PO-1001`, `GR-2001`, `INV-0001`, `BT-9001`.
- Payment idempotency key: `ap-<invoice id>`. The bank line carries it in `reference`, which is how reconciliation ties them together.
- Policy values (tolerances, approval limits) come from `data/policy.json`. Do not hard-code them.

## Changing it

See "Changing the contract" in [AGENTS.md](../AGENTS.md). Short version: the lane 4 owner makes the change in a `contract:` PR that contains nothing else.

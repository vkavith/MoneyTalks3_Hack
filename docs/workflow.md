# Workflow: PO to payment

Pay only what was ordered, received and approved.

| Phase | Diagram box | Code | Status |
|---|---|---|---|
| 1. Order & receive | Purchase order, Goods receipt | `data/purchase_orders.json`, `data/goods_receipts.json` | — |
| 2. Invoice & match | Vendor invoice, Capture & validate | `capture()` (lane 1) | `received → captured` |
| | 3-way match (within tolerance) | `match()` (lane 2) | `captured → matched / exception` |
| | Exceptions: fix, then re-match (human) | `resolve_exception()` (lane 2) | `exception → matched`, or escalated |
| 3. Approve & post | Approval by amount and cost center (human) | `approve()` (lane 3) | `matched → approved / rejected`, or pending |
| | Post to ledger | not built; shown as approved | — |
| 4. Pay | Payment run (ACH via sandbox) | `pay()` (lane 3) | `approved → paid` |
| 5. Reconcile & close | Bank statement vs payment | `reconcile()` (lane 3) | `paid → reconciled` |
| | Close & audit | `history` timeline in the UI (lane 4) | — |

Run the demo:

```bash
python -m ap.orchestrator.api     # open http://localhost:8000
```

Implementation: `ap/orchestrator/workflow.py` (step runner), `ap/orchestrator/api.py` (JSON API + static UI), `web/` (board, approval queue, invoice detail).

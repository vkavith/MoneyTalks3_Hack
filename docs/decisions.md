# Decisions

One line each, newest at the bottom: date, lane, decision, and why if it is not obvious. Anything another lane would be surprised by goes here.

- Kickoff, lane 4: Python 3.11+ with Pydantic v2 for the contract, because the team knows Python. Only the UI in `web/` may use another language.
- Kickoff, lane 4: One installable package (`ap`), one `pyproject.toml`, plain `venv` and `pip`.
- Kickoff, lane 4: Models are frozen and reject unknown fields. Stages return copies.
- Kickoff, lane 4: Money is integer cents; dates are `datetime.date`; timestamps are timezone-aware UTC.
- Kickoff, lane 4: Stage functions are synchronous.
- Kickoff, lane 3: Payments default to the mock provider; the Increase sandbox is opt-in through `PAYMENT_PROVIDER=increase`.
- Kickoff, lane 2: 3-way match stays deterministic code; the model is used only to investigate and explain exceptions.
- 2026-11-21, lane 3: Every approve/pay/reconcile decision is traced to Prism (Block Convey) with the invoice id as the session, and `pay()` asks Prism's guardrails (`/api/guardrails/evaluate`) before money moves. Prism fails open; the hard guardrails stay in code. Traces never carry bank numbers. Needs `PRISMTRACE_API_KEY` + `PRISMTRACE_PROJECT_ID`; off without them.
- 2026-11-21, lane 3: A returned payment keeps its `payment` block with `status="returned"` and the invoice goes `paid -> approved`. The re-send uses idempotency key `ap-<id>-2` (then `-3`...), because Increase replays a reused key. Reconciliation treats a positive statement line with our reference as a return.
- 2026-11-21, lane 3: With `PAYMENT_PROVIDER=increase`, `reconcile()` reads the sandbox transactions instead of `data/bank_statement.json` and, unless `INCREASE_SIMULATE_SETTLEMENT=0`, pushes the transfer through the sandbox submit/settle simulations first. `python -m ap.pay.demo` runs the sandbox flows and loads `.env` itself.

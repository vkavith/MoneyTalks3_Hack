# Lane 3: Approve and pay

**Owner:** _name_

## Mission

Take a matched invoice through approval, pay it through a bank sandbox, and tie the payment back to the bank statement. This lane moves money, so its guardrails are the ones that matter most.

## You own

`ap/pay/` and `tests/pay/`. Your public functions are `approve(invoice, ctx, human=None)`, `pay(invoice, ctx)` and `reconcile(invoice, ctx)`.

## Inputs and outputs

- **`approve`:** `matched` in. Out: `approved` if the total is within `policy.auto_approve_limit_cents`; otherwise still `matched` with `approval.decision == "pending"` and the role it is waiting on. Called again with a `HumanDecision`, it moves to `approved` or `rejected`.
- **`pay`:** `approved` in, `paid` out, with the `payment` section filled.
- **`reconcile`:** `paid` in. Out: `reconciled` once a bank line matches, otherwise unchanged.

## What you start with

All three functions work against a mock provider, so the pipeline pays and reconciles INV-0001 and INV-0007 on day zero. `ap/pay/increase.py` is an empty shell for the real sandbox.

## How to build it

1. **Get a sandbox key.** Follow https://increase.com/documentation/sandbox. Create a sandbox account to pay from, and put the key and account ID in `.env` as `INCREASE_API_KEY` and `INCREASE_ACCOUNT_ID`. Share them with the team outside the repo.
2. **Implement `pay_with_increase`.** Send an ACH credit to the bank details in the vendor master file, for `invoice.total_cents`, with the idempotency key passed in. Use Increase's Python SDK or `httpx`; add whichever you pick to `pyproject.toml`. Read https://increase.com/documentation/sending-ach-transfers first; do not write the request from memory.
3. **Move it through settlement.** In the sandbox a transfer does not settle by itself: use the simulation endpoints in the API reference to submit and settle it, and update `payment.status` as it moves.
4. **Reconcile against the sandbox.** With `PAYMENT_PROVIDER=increase`, list the account's transactions and match each to a payment by transfer ID or idempotency key. Keep the mock path, which reads `data/bank_statement.json`, working for CI.
5. **Handle a return.** Simulate a returned transfer, set `payment.status` to `"returned"` and move the invoice from `paid` back to `approved` so it can be paid again. This makes a strong reconciliation moment in the demo.
6. **Expose the human approval.** Agree with lane 4 how the UI's approve button calls `approve(invoice, ctx, human)`.
7. **Keep CI on the mock.** `PAYMENT_PROVIDER=mock` is the default and what CI uses, so tests never depend on the network.

## Guardrails that must stay in `pay()`

Each one raises `PaymentRefused`.

- Refuse unless status is `approved`.
- Refuse if the invoice already has a `payment`.
- Payee bank details come from `vendors.json`, never from `invoice.remit_to` and never from model output.
- Amount is `invoice.total_cents`, never a number a model produced.
- Refuse above `policy.max_single_payment_cents`.
- Idempotency key is `ap-<invoice id>`, so a retry cannot pay twice.
- Refuse to run unless the base URL is the sandbox host.

If `pay` is ever exposed to an agent as a tool, the tool takes an invoice ID and nothing else.

## Done when

- INV-0001 is paid through the Increase sandbox and shows as reconciled.
- Calling `pay` twice on one invoice makes one transfer.
- INV-0003 waits for a human, then pays after approval: this is demo invoice C.
- `tests/pay/` has a test for each guardrail, using `pytest.raises(PaymentRefused)`.

## Stretch

- Schedule payments for the due date and show the queue.
- Early-payment discount: flag invoices where paying early saves money.
- A second rail (real-time payment or wire) chosen by amount.

## Kickoff prompt

Paste this into your coding agent:

```
You are working in lane 3 (Approve and pay) of a 4-person hackathon repo. The project is Python.

First read AGENTS.md, docs/contract.md and docs/lanes/3-pay.md. Then set up
the virtual environment, run `pip install -e ".[dev]"` and `python scripts/check.py`,
and confirm the check passes.

Your task: first write a test in tests/pay/ for every guardrail in pay(). Then
implement pay_with_increase in ap/pay/increase.py against the Increase SANDBOX,
then reconciliation against sandbox transactions and handling of a returned
transfer, following the lane brief. Keep the mock provider working as the default.

Rules that matter most:
- Edit only ap/pay/ and tests/pay/. If you need anything changed elsewhere, stop and tell me.
- Import all models from ap.shared. Keep all three function signatures unchanged.
- Sandbox keys only. Read them from the environment. Never print or commit a key.
- Do not remove or weaken any guardrail in pay().
- Amount and payee come from the invoice record and vendors.json only.
- Read the current Increase docs before writing any request. Do not guess field names.
- Tests must pass with PAYMENT_PROVIDER=mock and no network.
- Run `python scripts/check.py` before every commit. Work on a branch named lane3/<topic>.

Start by showing me your plan in five lines or fewer, then build it.
```

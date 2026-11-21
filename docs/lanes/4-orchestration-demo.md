# Lane 4: Orchestration and demo

**Owner:** _name_

## Mission

Make four people's work run as one product, and make it easy to understand in three minutes. You own `main`, the contract and what the judges see.

## You own

`apps/`, `packages/shared/`, `scripts/`, `data/`, `docs/` and the root config.

## Three jobs

### 1. Integrator

- Keep `npm run check` green on `main`. When it goes red, fixing it is everyone's first priority and you coordinate.
- Review and merge PRs quickly. Small and often beats large and late.
- Own contract changes: make them in a `contract:` PR with nothing else in it, announce them, and make sure everyone rebases.
- Own `scripts/seed.ts`. When another lane needs a new scenario or a changed expectation, you add it.
- Turn on branch protection for `main`: require a PR and the `check` workflow.

### 2. Orchestrator and UI

`apps/orchestrator/src/run.ts` already runs every invoice through every stage from the command line. Build the product around it:

1. **A small API** that holds invoices in memory (or SQLite) and exposes: list invoices, get one invoice with its history, start processing an inbox file, and approve or reject a pending invoice.
2. **Run stages as steps, not one blocking call**, so the UI can show an invoice moving. Emit an event on each `transition()`.
3. **A web app in `apps/web/`** with three views:
   - **Pipeline board:** one column per status, invoices as cards that move as stages finish.
   - **Invoice detail:** the PDF beside the extracted fields, the match result line by line (PO, receipt and invoice values side by side), the agent's rationale, and the `history` as a timeline.
   - **Approval queue:** pending invoices with approve and reject buttons that call `approve(invoice, ctx, human)`.
4. **Show the guardrails.** A visible "sandbox" badge, the payment's idempotency key, and the limit that triggered a human approval. Judges ask about safety; put the answers on screen.

### 3. Demo and pitch

- Write and rehearse the script in [docs/demo-script.md](../demo-script.md).
- Record a backup video of the full run once it works, in case the sandbox or the network fails live.
- Build the pitch: the problem, the live demo, what is real against what is mocked, and what comes next.

## Done when

- One command starts the API and the UI.
- Demo invoices A, B and C run from the UI with no terminal visible.
- Every status change on screen comes from `history`, not from UI-side guesses.
- The backup video exists.

## Stretch

- A reset button that reloads the seed data between demo runs.
- Upload a new PDF from the UI.
- A metrics strip: touchless rate, average time from capture to paid, exceptions by code.

## Kickoff prompt

Paste this into your coding agent:

```
You are working in lane 4 (Orchestration and demo) of a 4-person hackathon repo.

First read AGENTS.md, docs/contract.md and docs/lanes/4-orchestration-demo.md,
then run `npm install && npm run check` and confirm it passes.

Your task: build a small API around the pipeline in apps/orchestrator and a
web UI in apps/web with a pipeline board, an invoice detail view and an
approval queue, following the lane brief. All in TypeScript.

Rules that matter most:
- You own apps/, packages/shared/, scripts/, data/ and docs/. Do not edit
  packages/intake/, packages/match/ or packages/pay/; call their exported functions.
- Contract changes go in their own PR titled "contract: ..." with nothing else in it.
- Never hand-edit data/. Change scripts/seed.ts and run `npm run seed`.
- The UI shows status from the invoice's history; it never invents state.
- Keep `npm run check` green on main at all times.
- Run `npm run check` before every commit. Work on a branch named lane4/<topic>.

Start by showing me your plan in five lines or fewer, then build it.
```

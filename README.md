# AP agent: invoice to payment

An agent that takes a vendor invoice from PDF to paid: capture, 3-way match, exception handling, approval, sandbox payment and reconciliation.

## Start here

```bash
npm install
cp .env.example .env
npm run check        # typecheck + data check + end-to-end pipeline
```

`npm run check` passes on day zero because every stage has a stub or a baseline. Your job is to replace your stage with the real thing without breaking it.

```bash
npm run pipeline                       # run all 8 seed invoices end to end
npm run pipeline -- --approve INV-0003 # same, with a human approving the $48,000 invoice
npm run seed                           # regenerate /data (lane 4 only)
```

## Who does what

| Lane | Owner | Builds | Brief |
|---|---|---|---|
| 1 Intake | _name_ | Invoice PDF to a structured `Invoice` | [docs/lanes/1-intake.md](docs/lanes/1-intake.md) |
| 2 Match & exceptions | _name_ | 3-way match and the agent that resolves mismatches | [docs/lanes/2-match.md](docs/lanes/2-match.md) |
| 3 Approve & pay | _name_ | Approval rules, sandbox payment, reconciliation | [docs/lanes/3-pay.md](docs/lanes/3-pay.md) |
| 4 Orchestration & demo | _name_ | State machine, UI, audit trail, pitch; owns `main` and the contract | [docs/lanes/4-orchestration-demo.md](docs/lanes/4-orchestration-demo.md) |

Each brief ends with a kickoff prompt to paste into your coding agent.

## How we stay in sync

- **[AGENTS.md](AGENTS.md)** is the shared prompt. Every coding agent reads it first. `CLAUDE.md` points to it.
- **[docs/contract.md](docs/contract.md)** describes the one `Invoice` record, its statuses and the stage functions. The code is in `packages/shared/`.
- **`data/`** is the shared data source, described in [data/README.md](data/README.md).
- **`npm run check`** runs in CI on every PR. If it is red, fixing it comes before anything else.

## Layout

```
packages/shared/     the contract: schema, transitions, stage signatures   (lane 4)
packages/intake/     capture()                                             (lane 1)
packages/match/      match(), resolveException()                           (lane 2)
packages/pay/        approve(), pay(), reconcile()                         (lane 3)
apps/orchestrator/   runs the stages in order                              (lane 4)
apps/web/            demo UI, to be created                                (lane 4)
data/                seed data and ground truth, generated
scripts/             seed.ts, check-data.ts
docs/                contract, lane briefs, schedule, demo script, checklist
```

## Schedule

See [docs/schedule.md](docs/schedule.md). It assumes a 24-hour event; scale the checkpoints if yours is different.

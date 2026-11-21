# Schedule

Assumes a 24-hour event. For a different length, keep the proportions.

| When | Checkpoint | What must be true |
|---|---|---|
| Hour 0 to 1 | Kickoff, all four together | Lanes assigned and names written into the README. Everyone has cloned, run `npm run check` and pasted the kickoff prompt into their agent. Keys shared. Contract read aloud once; any change agreed now. |
| Hour 8 | Real code in every lane | Intake reads at least the clean PDFs. The exception agent handles one code. A payment has gone through the sandbox. The UI shows the board from live data. `main` is green. |
| Hour 16 | Feature complete | All stubs gone. Demo invoices A, B and C run from the UI. |
| Hour 19 | Feature freeze | Bug fixes and polish only. No new dependencies, no contract changes. |
| Hour 20 | Backup video recorded | A clean end-to-end run on video. |
| Hour 21 to 23 | Rehearse | Full demo run three times with a timer. Pitch finalized. |
| Hour 24 | Submit | |

## Every four hours

A five-minute standup: what merged, what is blocked, whether `main` is green. The lane 4 owner runs it.

## If you fall behind

Cut in this order, last resort first:

1. Stretch goals.
2. Real PDF extraction for the harder invoices; keep fixtures for those.
3. The real sandbox; fall back to the mock provider and say so in the pitch.
4. Never cut: the exception agent on invoice B, the human approval on invoice C, and the audit trail.

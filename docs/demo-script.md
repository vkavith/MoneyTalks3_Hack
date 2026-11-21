# Demo script

Three minutes, three invoices. Reset the data before you start.

## Opening (20 seconds)

"Paying a supplier invoice means checking it against what was ordered and what arrived, getting it approved, paying it and reconciling the bank. Most of that is still done by hand. Our agent does it end to end, and stops for a person exactly where it should."

## Invoice A: touchless (40 seconds)

- Drop `INV-0001.pdf` in.
- Point at the card moving: captured, matched, approved, paid, reconciled.
- Open the detail view: PO, receipt and invoice agree line by line; under the limit, so no human; the payment's sandbox transfer ID; the bank line it reconciled to.
- Say: "Nobody touched that."

## Invoice B: the agent handles an exception (60 seconds)

- Drop `INV-0002.pdf` in.
- It stops at exception. Open it: unit price $89.25 against $85.00 on the PO, 5% over a 2% tolerance.
- Show the agent's rationale and the message it drafted to the buyer.
- Say: "The rules caught it. The agent worked out why and what to do next, and it cannot change what gets paid without a person."

## Invoice C: human in the loop (40 seconds)

- Drop `INV-0003.pdf` in.
- It matches cleanly but waits: $48,000 is over the $10,000 auto-approve limit.
- Click approve in the approval queue. It pays and reconciles.
- Open the history timeline: every step, who did it and when.

## Close (20 seconds)

- Flash INV-0008 if there is time: a look-alike vendor name with different bank details, flagged as possible fraud and never paid.
- Say what is real (extraction, matching, the agent, sandbox payment) and what is mocked.
- One sentence on what comes next.

## Before going on stage

- [ ] Data reset, browser zoomed in, notifications off
- [ ] Sandbox key working; a test payment sent in the last ten minutes
- [ ] Backup video open in another tab
- [ ] One person drives, one person talks

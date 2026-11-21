// LANE 4. Walking skeleton: runs every inbox invoice through every stage
// and checks the result against data/expected/outcomes.json.
//   npm run pipeline
//   npm run pipeline -- --approve INV-0003     (simulate a human approval)
import { capture } from "@ap/intake";
import { match, resolveException } from "@ap/match";
import { approve, pay, reconcile } from "@ap/pay";
import { Invoice } from "@ap/shared";
import { listInbox, loadContext, loadExpectedOutcomes } from "@ap/shared/load";

const args = process.argv.slice(2);
const humanApprovals = new Set(
  args.flatMap((a, i) => (a === "--approve" && args[i + 1] ? [args[i + 1]] : [])),
);

export async function runPipeline(): Promise<Invoice[]> {
  const ctx = loadContext();
  const done: Invoice[] = [];

  for (const file of listInbox()) {
    let inv = await capture(file);
    inv = await match(inv, { ...ctx, priorInvoices: done });
    if (inv.status === "exception") {
      inv = await resolveException(inv, { ...ctx, priorInvoices: done });
    }
    if (inv.status === "matched") {
      inv = await approve(inv, ctx);
      if (inv.approval?.decision === "pending" && humanApprovals.has(inv.id)) {
        inv = await approve(inv, ctx, {
          approver: "demo-approver",
          decision: "approved",
          reason: "Approved from the command line",
        });
      }
    }
    if (inv.status === "approved") inv = await pay(inv, ctx);
    if (inv.status === "paid") inv = await reconcile(inv, ctx);
    done.push(Invoice.parse(inv));
  }
  return done;
}

const results = await runPipeline();
const expected = new Map(loadExpectedOutcomes().map((e) => [e.invoice_id, e]));
let failures = 0;

console.table(
  results.map((inv) => {
    const exp = expected.get(inv.id);
    const codes = [...new Set(inv.match?.exceptions.map((e) => e.code) ?? [])];
    const wantCodes = [...(exp?.exception_codes ?? [])].sort().join(",");
    const ok =
      !!exp &&
      codes.sort().join(",") === wantCodes &&
      (humanApprovals.has(inv.id) || inv.status === exp.resting_status);
    if (!ok) failures++;
    return {
      invoice: inv.id,
      scenario: exp?.scenario ?? "?",
      status: inv.status,
      exceptions: codes.join(",") || "-",
      approval: inv.approval?.decision ?? "-",
      ok: ok ? "yes" : "NO",
    };
  }),
);

if (failures > 0) {
  console.error(`${failures} invoice(s) differ from data/expected/outcomes.json`);
  process.exit(1);
}
console.log("Pipeline matches expected outcomes.");

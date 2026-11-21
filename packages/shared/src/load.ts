// Node-only helpers for reading /data. Import from "@ap/shared/load".
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import {
  BankTxn,
  ExpectedOutcome,
  GoodsReceipt,
  Invoice,
  Policy,
  PurchaseOrder,
  Vendor,
} from "./schema";
import type { PipelineContext } from "./stages";

export const DATA_DIR =
  process.env.AP_DATA_DIR ??
  join(dirname(fileURLToPath(import.meta.url)), "../../../data");

function read<T>(schema: z.ZodType<T>, ...path: string[]): T {
  return schema.parse(
    JSON.parse(readFileSync(join(DATA_DIR, ...path), "utf8")),
  );
}

export function loadContext(): PipelineContext {
  return {
    vendors: read(z.array(Vendor), "vendors.json"),
    purchaseOrders: read(z.array(PurchaseOrder), "purchase_orders.json"),
    receipts: read(z.array(GoodsReceipt), "goods_receipts.json"),
    policy: read(Policy, "policy.json"),
    bankTxns: read(z.array(BankTxn), "bank_statement.json"),
    priorInvoices: [],
  };
}

/** PDF file names in data/inbox, in arrival order. */
export function listInbox(): string[] {
  return readdirSync(join(DATA_DIR, "inbox"))
    .filter((f) => f.endsWith(".pdf"))
    .sort();
}

/** Ground truth for what capture should produce from an inbox file. */
export function loadCapturedFixture(sourceFile: string): Invoice {
  return read(
    Invoice,
    "expected",
    "captured",
    sourceFile.replace(/\.pdf$/, ".json"),
  );
}

export function loadExpectedOutcomes(): ExpectedOutcome[] {
  return read(z.array(ExpectedOutcome), "expected", "outcomes.json");
}

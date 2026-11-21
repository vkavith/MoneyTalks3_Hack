// LANE 3 TODO: send an ACH credit through the Increase SANDBOX.
// Read the current docs before writing this; do not guess field names.
//   https://increase.com/documentation/sandbox
//   https://increase.com/documentation/sending-ach-transfers
//   https://increase.com/documentation/api
// Requirements:
//   - Base URL from INCREASE_BASE_URL, which must be the sandbox host.
//   - Pass idempotencyKey as the request's idempotency key.
//   - Amount and bank details come from the arguments below, nothing else.
//   - Use the sandbox simulation endpoints to settle (and, for the demo, return) a transfer.
import type { Invoice, Payment, Vendor } from "@ap/shared";

export async function payWithIncrease(
  _invoice: Invoice,
  _vendor: Vendor,
  _idempotencyKey: string,
): Promise<Payment> {
  const base = process.env.INCREASE_BASE_URL ?? "";
  if (!base.includes("sandbox")) {
    throw new Error("INCREASE_BASE_URL must point at the Increase sandbox");
  }
  throw new Error("Increase provider not implemented yet (lane 3)");
}

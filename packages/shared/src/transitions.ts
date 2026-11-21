import type { Invoice, InvoiceStatus } from "./schema";

/** The only legal status moves. Change status through transition(), never by hand. */
export const ALLOWED: Record<InvoiceStatus, InvoiceStatus[]> = {
  received: ["captured"],
  captured: ["matched", "exception"],
  exception: ["matched", "rejected"],
  matched: ["approved", "rejected"],
  approved: ["paid"],
  // paid -> approved covers a returned payment that must be sent again.
  paid: ["reconciled", "approved"],
  rejected: [],
  reconciled: [],
};

export function transition(
  invoice: Invoice,
  to: InvoiceStatus,
  actor: string,
  note?: string,
): Invoice {
  if (!ALLOWED[invoice.status].includes(to)) {
    throw new Error(
      `Illegal transition ${invoice.status} -> ${to} for ${invoice.id}`,
    );
  }
  return {
    ...invoice,
    status: to,
    history: [
      ...invoice.history,
      {
        at: new Date().toISOString(),
        from: invoice.status,
        to,
        actor,
        ...(note ? { note } : {}),
      },
    ],
  };
}

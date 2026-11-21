// Lane 4 demo UI. Every status shown comes from the API (the invoice record).
const $ = (id) => document.getElementById(id);
const money = (c) => `$${(c / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function render() {
  const [phases, invoices] = await Promise.all([api("/api/phases"), api("/api/invoices")]);
  $("board").innerHTML = phases.map((p) => {
    let cards;
    if (p.id === "order") {
      cards = `<div class="card doc"><b>Purchase order</b><br>What we ordered</div>
               <div class="card doc"><b>Goods receipt</b><br>What actually arrived</div>`;
    } else {
      cards = invoices.filter((i) => i.phase === p.id).map((i) => `
        <div class="card ${i.needs_human ? "human" : ""} ${i.exceptions.length ? "exception" : ""}" data-id="${esc(i.id)}">
          <b>${esc(i.id)}</b> · ${money(i.total_cents)}<br>${esc(i.vendor_name)}
          <div class="status">${esc(i.status)}${i.exceptions.length ? " · " + esc(i.exceptions.join(", ")) : ""}</div>
        </div>`).join("");
    }
    return `<div class="phase"><h3>${esc(p.title)}</h3>${cards}</div>`;
  }).join("");
  document.querySelectorAll(".card[data-id]").forEach((el) => el.onclick = () => showDetail(el.dataset.id));

  const pending = invoices.filter((i) => i.needs_human && i.status === "matched");
  $("queue").innerHTML = pending.length ? pending.map((i) => `
    <div class="queue-item"><b>${esc(i.id)}</b> ${money(i.total_cents)} · ${esc(i.vendor_name)}<br>
      <button onclick="decide('${esc(i.id)}','approved')">Approve</button>
      <button class="reject" onclick="decide('${esc(i.id)}','rejected')">Reject</button>
    </div>`).join("") : `<p class="muted">Nothing waiting.</p>`;
}

async function showDetail(id) {
  const d = await api(`/api/invoices/${id}`);
  const inv = d.invoice;
  const poLines = Object.fromEntries((d.purchase_order?.lines || []).map((l) => [l.line_no, l]));
  const received = {};
  d.goods_receipts.forEach((r) => r.lines.forEach((l) => received[l.po_line_no] = (received[l.po_line_no] || 0) + l.qty_received));
  const rows = inv.lines.map((l) => {
    const po = poLines[l.po_line_no];
    return `<tr><td>${esc(l.description)}</td>
      <td>${po ? po.qty + " @ " + money(po.unit_price_cents) : "-"}</td>
      <td>${received[l.po_line_no] ?? "-"}</td>
      <td>${l.qty} @ ${money(l.unit_price_cents)}</td></tr>`;
  }).join("");
  const res = inv.match?.resolution;
  const g = d.guardrails;
  $("detail").innerHTML = `
    <p><b>${esc(inv.id)}</b> · ${esc(inv.vendor_name)} · PO ${esc(inv.po_id || "none")}<br>
       Total ${money(inv.total_cents)} · status <b>${esc(inv.status)}</b>
       · <a href="/inbox/${esc(inv.source_file)}" target="_blank">PDF</a></p>
    <h3>3-way match</h3>
    <table><tr><th>Line</th><th>PO</th><th>Received</th><th>Invoice</th></tr>${rows}</table>
    ${(inv.match?.exceptions || []).map((e) => `<p>⚠️ <b>${esc(e.code)}</b> ${esc(e.detail)}</p>`).join("")}
    ${res ? `<p><b>Agent (${esc(res.action)}):</b> ${esc(res.rationale)}</p>` : ""}
    ${inv.approval ? `<p><b>Approval:</b> ${esc(inv.approval.decision)} · ${esc(inv.approval.approver || "")} · ${esc(inv.approval.reason)}</p>` : ""}
    <h3>Guardrails</h3>
    <p>Sandbox: yes · auto-approve limit ${money(g.auto_approve_limit_cents)} ·
       single-payment limit ${money(g.max_single_payment_cents)}<br>
       Idempotency key: <code>${esc(g.idempotency_key || "-")}</code></p>
    <h3>Audit trail</h3>
    <ol class="timeline">${inv.history.map((h) => `<li>${esc(h.at)} · ${esc(h.from_status || "∅")} → <b>${esc(h.to_status)}</b> by ${esc(h.actor)} ${esc(h.note || "")}</li>`).join("")}</ol>`;
}

async function decide(id, decision) {
  const reason = prompt(`Reason to ${decision === "approved" ? "approve" : "reject"} ${id}?`, "Reviewed in demo");
  if (reason === null) return;
  await api(`/api/invoices/${id}/decision`, { approver: "demo-approver", decision, reason });
  await render();
  await showDetail(id);
}

$("process").onclick = async () => { await api("/api/process", {}); await render(); };
$("reset").onclick = async () => { await api("/api/reset", {}); $("detail").innerHTML = "Select an invoice."; await render(); };
render();

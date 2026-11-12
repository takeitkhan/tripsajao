import { get, post } from '../api.js';
import { lookups } from '../data.js';
import { h, btn, field, area, modal, tabs, table, badge, pageHead, money, fmtDateTime, humanize, toast } from '../ui.js';
import { withDocs } from '../docs.js';

export const detailsText = (d) => [humanize(d.method), d.account_name, d.account_number, d.bank_name].filter(Boolean).join(' | ');

function reviewModal(p, action, title, verb, onDone) {
  const note = area({ rows: 2, maxlength: 500, placeholder: 'Optional note, visible in your records' });
  const m = modal({
    title, body: [h('p', {}, `${money(p.amount)} for ${p.partnerName}`), field('Note', note)],
    actions: [btn('Cancel', { onClick: () => m.close() }),
      btn(verb, { kind: action === 'reject' ? 'danger' : 'primary', onClick: async () => { await post(`/payouts/${p.id}/${action}`, { note: note.value.trim() || null }); toast(`${verb} done`, 'ok'); m.close(); onDone(); } })],
  });
}

export function render(ctx) {
  const canApprove = ctx.can('payouts:approve');
  return h('div', {}, pageHead('Payouts', 'Partner payout requests waiting for you to approve and settle.'), withDocs('payouts', () => manage(canApprove)));
}

async function manage(canApprove) {
  const STATUSES = [['PENDING', 'Waiting for approval'], ['APPROVED', 'Approved, to pay'], ['PAID', 'Paid'], ['REJECTED', 'Rejected'], ['', 'All']];
  const t = tabs(STATUSES.map(([id, label]) => ({
    id: id || 'ALL', label,
    render: async () => {
      const [page, lk] = await Promise.all([get('/payouts', { status: id, limit: 200 }), lookups()]);
      const rows = page.items.map((p) => ({ ...p, partnerName: lk.partners[p.partner_id]?.name || 'Partner' }));
      const reload = () => t.refresh();
      return table([
        { label: 'Requested', render: (p) => fmtDateTime(p.created_at) },
        { label: 'Partner', render: (p) => h('b', {}, p.partnerName) },
        { label: 'Amount', class: 'num', render: (p) => money(p.amount) },
        { label: 'Pay to', render: (p) => detailsText(p.payout_details) },
        { label: 'Status', render: (p) => badge(p.status) },
        { label: '', render: (p) => canApprove ? h('div', { class: 'actions' },
          p.status === 'PENDING' ? [btn('Approve', { kind: 'sm primary', onClick: () => reviewModal(p, 'approve', 'Approve payout', 'Approve', reload) }), btn('Reject', { kind: 'sm danger', onClick: () => reviewModal(p, 'reject', 'Reject payout', 'Reject', reload) })] : null,
          p.status === 'APPROVED' ? btn('Mark as paid', { kind: 'sm primary', onClick: () => reviewModal(p, 'mark-paid', 'Mark payout as paid', 'Mark as paid', reload) }) : null) : null },
      ], rows, { empty: id === 'PENDING' ? 'No payouts are waiting. Requests from partners appear here.' : 'Nothing here yet.' });
    },
  })), { initial: 'PENDING' });
  return t;
}

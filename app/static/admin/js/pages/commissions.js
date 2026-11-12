// Commissions: what you owe to resellers (you are the owner) and what resellers owe you (you are the reseller).
import { get, post } from '../api.js';
import { h, btn, field, inp, area, modal, table, tabs, figures, emptyState, pageHead, toast, humanize, fmtDate, fmtDateTime, money, today } from '../ui.js';
import { withDocs } from '../docs.js';

const LABEL = { DUE: 'Waiting for payment', PAID: 'Paid, not confirmed yet', CONFIRMED: 'Settled', DISPUTED: 'Disputed' };
const KIND = { DUE: 'warn', PAID: 'info', CONFIRMED: 'ok', DISPUTED: 'bad' };
const statusBadge = (s) => h('span', { class: 'badge ' + (KIND[s.status] || '') }, LABEL[s.status] || humanize(s.status));
const late = (s) => (s.overdue ? h('span', { class: 'badge bad', style: { marginLeft: '6px' } }, `${s.days_overdue} day${s.days_overdue === 1 ? '' : 's'} late`) : null);
const period = (s) => (s.mode === 'PER_BOOKING' ? `Stay ending ${fmtDate(s.period_end)}` : `${fmtDate(s.period_start)} to ${fmtDate(s.period_end)}`);

export function render(ctx) {
  return h('div', {}, pageHead('Commissions', 'Commission for rooms sold by resellers: what is owed, what is paid, and what is settled.'), withDocs('channel', () => body(ctx)));
}

async function body(ctx) {
  const canManage = ctx.can('channel:manage');
  const sum = await get('/channel/summary');
  const t = tabs([
    { id: 'RESELLER', label: 'Owed to me', render: () => list('RESELLER', canManage, () => t.refresh()) },
    { id: 'OWNER', label: 'I owe', render: () => list('OWNER', canManage, () => t.refresh()) },
  ], { initial: sessionStorage.getItem('kt.comm.tab') || (sum.as_owner.length && !sum.as_reseller.length ? 'OWNER' : 'RESELLER') });
  t.addEventListener('click', (e) => { const b = e.target.closest('[role=tab]'); if (b) sessionStorage.setItem('kt.comm.tab', b.textContent.startsWith('I owe') ? 'OWNER' : 'RESELLER'); });
  return h('div', { class: 'stack' }, totals(sum), t);
}

function totals(sum) {
  const block = (title, rows, owner) => (rows.length ? h('div', {}, h('h2', { class: 'section' }, title), ...rows.map((r) => figures([
    { label: owner ? 'Comes due after check-out' : 'Coming after check-out', value: money(r.upcoming, r.currency) },
    { label: 'Earned, no statement yet', value: money(r.unbilled, r.currency) },
    { label: owner ? 'Waiting for you to pay' : 'Waiting for payment', value: money(r.to_pay, r.currency) },
    { label: owner ? 'Late' : 'Late', value: money(r.overdue, r.currency), color: Number(r.overdue) > 0 ? 'var(--bad, #c0392b)' : null },
    { label: 'Paid, to be confirmed', value: money(r.awaiting_confirmation, r.currency) },
    { label: 'Settled', value: money(r.settled, r.currency) },
  ]))) : null);
  const a = block('Commission owed to me', sum.as_reseller, false);
  const b = block('Commission I owe', sum.as_owner, true);
  return a || b ? h('div', { class: 'stack' }, a, b) : null;
}

async function list(role, canManage, reload) {
  const rows = await get('/channel/statements', { role });
  const mine = role === 'OWNER';
  return h('div', { class: 'stack' },
    h('p', { class: 'muted' }, mine
      ? 'Commission becomes payable after the guest checks out. Pay the reseller outside this system (bank, bKash, cash), then press "Mark as paid" with the reference. The reseller confirms they received it.'
      : 'Commission becomes payable after the guest checks out. When the owner says they paid, check your account and confirm, or tell us it did not arrive.'),
    table([
      { label: 'Statement', render: (s) => h('b', {}, s.code) },
      { label: mine ? 'Reseller' : 'Owner', render: (s) => s.counterpart },
      { label: 'Covers', render: period },
      { label: 'Due', render: (s) => fmtDate(s.due_date) },
      { label: 'Amount', class: 'num', render: (s) => h('b', {}, money(s.amount, s.currency)) },
      { label: 'Status', render: (s) => h('span', {}, statusBadge(s), late(s)) },
    ], rows, { onRowClick: (s) => open(s.id, canManage, reload), empty: mine ? 'No commission is due to any reseller yet.' : 'No commission is owed to you yet. It appears after your guests check out.' }));
}

async function open(id, canManage, reload) {
  const s = await get(`/channel/statements/${id}`);
  const mine = s.role === 'OWNER';
  const actions = [btn('Close', { onClick: () => m.close() })];
  if (canManage && mine && ['DUE', 'DISPUTED'].includes(s.status)) actions.push(btn('Mark as paid', { kind: 'primary', onClick: () => { m.close(); payModal(s, reload); } }));
  if (canManage && !mine && s.status === 'PAID') {
    actions.push(btn('It did not arrive', { kind: 'danger', onClick: () => { m.close(); disputeModal(s, reload); } }));
    actions.push(btn('I received it', { kind: 'primary', onClick: async () => { await post(`/channel/statements/${s.id}/confirm`); toast('Thank you. This statement is settled.', 'ok'); m.close(); await reload(); } }));
  }
  const info = [
    ['Between', mine ? `You and ${s.counterpart}` : `${s.counterpart} and you`],
    ['Covers', period(s)], ['Due', fmtDate(s.due_date)], ['Amount', money(s.amount, s.currency)],
    s.paid_reference ? ['Payment reference', `${s.paid_reference}${s.paid_on ? `, paid on ${fmtDate(s.paid_on)}` : ''}`] : null,
    s.paid_note ? ['Note from the owner', s.paid_note] : null,
    s.confirmed_at ? ['Confirmed received', fmtDateTime(s.confirmed_at)] : null,
    s.dispute_reason ? ['Not received', s.dispute_reason] : null,
  ].filter(Boolean);
  const m = modal({ title: `Statement ${s.code}`, wide: true, actions, body: [
    h('div', { class: 'row' }, statusBadge(s), late(s)),
    h('dl', { class: 'kv' }, info.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
    s.status === 'DISPUTED' && mine ? h('p', { class: 'muted' }, 'The reseller says the money did not arrive. Check the payment, then press "Mark as paid" again with the correct reference.') : null,
    table([
      { label: 'Booking', render: (l) => l.booking_ref }, { label: 'Property', render: (l) => l.property_name }, { label: 'Guest', render: (l) => l.guest_name || '-' },
      { label: 'Stay', render: (l) => `${fmtDate(l.check_in)} to ${fmtDate(l.check_out)}` },
      { label: '', render: (l) => (l.kind === 'REFUND_OF_COMMISSION' ? h('span', { class: 'muted' }, 'Cancelled booking, commission taken back') : null) },
      { label: 'Amount', class: 'num', render: (l) => money(l.amount, s.currency) },
    ], s.lines || []),
  ] });
}

function payModal(s, reload) {
  const ref = inp({ placeholder: 'For example bKash TXN12345 or bank slip number' });
  const on = inp({ type: 'date', value: today(), max: today() });
  const note = area({ rows: 2, maxlength: 500 });
  const m = modal({ title: `Mark ${money(s.amount, s.currency)} as paid`, body: [
    h('p', {}, `Pay ${s.counterpart} outside this system, then record it here. They will be asked to confirm that the money arrived.`),
    field('Payment reference', ref), field('Paid on', on), field('Note (optional)', note)],
  actions: [btn('Cancel', { onClick: () => m.close() }), btn('Mark as paid', { kind: 'primary', onClick: async () => {
    if (ref.value.trim().length < 3) throw new Error('Enter the payment reference (at least 3 characters).');
    await post(`/channel/statements/${s.id}/mark-paid`, { reference: ref.value.trim(), paid_on: on.value || null, note: note.value.trim() || null });
    toast('Marked as paid. Waiting for the reseller to confirm.', 'ok'); m.close(); await reload();
  } })] });
}

function disputeModal(s, reload) {
  const why = area({ rows: 3, maxlength: 500, placeholder: 'For example: nothing reached our bKash account' });
  const m = modal({ title: 'Tell the owner it did not arrive', body: [field('What happened?', why, 'The owner will see this and can pay again.')],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Send', { kind: 'danger', onClick: async () => {
      if (why.value.trim().length < 3) throw new Error('Please write a few words about what happened.');
      await post(`/channel/statements/${s.id}/dispute`, { reason: why.value.trim() });
      toast('The owner has been told.', 'ok'); m.close(); await reload();
    } })] });
}

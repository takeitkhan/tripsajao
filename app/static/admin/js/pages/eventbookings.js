// Seat bookings on events, made through the API. The customer pays by hand and sends a screenshot; the business checks the money here.
import { get, post } from '../api.js';
import { h, raw, btn, field, inp, area, modal, tabs, table, badge, pageHead, money, fmtDateTime, fmtDate, toast, confirmDialog, debounce } from '../ui.js';
import { withDocs } from '../docs.js';

const STATUS = [['PAYMENT_SUBMITTED', 'Payment to check'], ['HOLD', 'Seats held'], ['CONFIRMED', 'Confirmed'], ['CANCELLED', 'Cancelled'], ['EXPIRED', 'Expired'], ['', 'All']];
const label = (s) => (STATUS.find((x) => x[0] === s) || [0, s])[1];

function decide(b, p, action, canManage, done) {
  const isVerify = action === 'verify';
  const amount = inp({ type: 'number', min: 0.01, step: '0.01', value: p.amount });
  const reason = area({ rows: 2, maxlength: 300, placeholder: 'Tell the customer what is wrong' });
  const m = modal({
    title: isVerify ? 'Money received' : 'Reject this payment',
    body: [h('p', {}, raw(`${b.booking_ref} - ${b.customer_info_json.name}`)),
      isVerify ? field('Amount you received', amount) : field('Reason', reason),
      h('p', { class: 'muted' }, isVerify ? 'Confirming adds this amount to the booking and credits the partner commission.' : 'The customer gets 10 minutes to send the payment again.')],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn(isVerify ? 'Confirm payment' : 'Reject payment', { kind: isVerify ? 'primary' : 'danger', onClick: async () => {
      await post(`/event-bookings/${b.id}/payments/${p.id}/${action}`, isVerify ? { amount: amount.value } : { reason: reason.value.trim() || null });
      toast(isVerify ? 'Payment confirmed' : 'Payment rejected', 'ok'); m.close(); done();
    } })],
  });
}

async function open(id, canManage, changed) {
  const m = modal({ title: 'Event booking', wide: true, body: h('div', { class: 'spinner' }) });
  async function draw() {
    const b = await get(`/event-bookings/${id}`);
    const c = b.customer_info_json || {};
    const reload = () => { draw().catch((e) => toast(e.message, 'bad')); changed(); };
    const open_ = !['CANCELLED', 'EXPIRED'].includes(b.status);
    m.setBody([
      h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('h3', { style: { margin: 0 } }, raw(b.booking_ref)), badge(b.status, label(b.status))),
      h('dl', { class: 'facts' },
        h('dt', {}, 'Event'), h('dd', {}, raw(b.event_title || '-'), b.event_starts_on ? raw(` (${fmtDate(b.event_starts_on)})`) : null),
        h('dt', {}, 'Customer'), h('dd', {}, raw(c.name || '-')),
        h('dt', {}, 'Phone'), h('dd', {}, raw(c.phone || '-')),
        h('dt', {}, 'Email'), h('dd', {}, raw(c.email || '-')),
        c.address ? [h('dt', {}, 'Address'), h('dd', {}, raw(c.address))] : null,
        c.emergency_contact ? [h('dt', {}, 'Emergency contact'), h('dd', {}, raw(c.emergency_contact))] : null,
        (c.guest_names || []).length ? [h('dt', {}, 'Other travellers'), h('dd', {}, raw(c.guest_names.join(', ')))] : null,
        c.notes ? [h('dt', {}, 'Note'), h('dd', {}, raw(c.notes))] : null,
        h('dt', {}, 'Seats'), h('dd', {}, raw(String(b.seats))),
        h('dt', {}, 'Total'), h('dd', {}, money(b.total_amount, b.currency)),
        h('dt', {}, 'Paid'), h('dd', {}, money(b.paid_amount, b.currency)),
        h('dt', {}, 'Still due'), h('dd', {}, money(Number(b.total_amount) - Number(b.paid_amount), b.currency)),
        b.partner_name ? [h('dt', {}, 'Sold by partner'), h('dd', {}, raw(b.partner_name), raw(` - commission ${money(b.commission_amount, b.currency)}`))] : null,
        b.hold_expires_at && b.status === 'HOLD' ? [h('dt', {}, 'Seats held until'), h('dd', {}, fmtDateTime(b.hold_expires_at))] : null,
        b.cancel_reason ? [h('dt', {}, 'Cancelled because'), h('dd', {}, raw(b.cancel_reason))] : null),
      h('h3', { style: { margin: '18px 0 8px' } }, 'Payments'),
      b.payments_json.length ? table([
        { label: 'Sent', render: (p) => fmtDateTime(p.submitted_at) },
        { label: 'How', render: (p) => h('span', {}, raw(p.method), p.trx_id ? raw(` - ${p.trx_id}`) : null, p.sender ? h('div', { class: 'muted' }, raw(p.sender)) : null) },
        { label: 'Amount', class: 'num', render: (p) => money(p.status === 'VERIFIED' ? p.verified_amount : p.amount, b.currency) },
        { label: 'Screenshot', render: (p) => h('div', { class: 'chips' }, (p.proofs || []).map((u, i) => h('a', { href: u, target: '_blank', rel: 'noopener' }, h('img', { src: u, alt: 'Payment screenshot', style: { height: '44px', borderRadius: '6px', border: '1px solid var(--line)' } })))) },
        { label: 'Status', render: (p) => h('div', {}, badge(p.status === 'SUBMITTED' ? 'PAYMENT_SUBMITTED' : p.status, p.status === 'SUBMITTED' ? 'To check' : undefined), p.reason ? h('div', { class: 'muted' }, raw(p.reason)) : null) },
        { label: '', render: (p) => canManage && p.status === 'SUBMITTED' && b.status !== 'CANCELLED' ? h('div', { class: 'actions' },
          btn('Money received', { kind: 'sm primary', onClick: () => decide(b, p, 'verify', canManage, reload) }),
          btn('Reject', { kind: 'sm danger', onClick: () => decide(b, p, 'reject', canManage, reload) })) : null },
      ], b.payments_json) : h('p', { class: 'muted' }, b.status === 'HOLD' ? 'The customer has not sent a payment yet.' : 'No payments.'),
    ]);
    m.setActions([btn('Close', { onClick: () => m.close() }),
      canManage && open_ ? btn('Cancel this booking', { kind: 'danger', onClick: async () => {
        if (!(await confirmDialog('The seats are freed and any partner commission is reversed. Money already received is not refunded automatically.', { confirmText: 'Cancel booking', danger: true, title: 'Cancel this booking?' }))) return;
        await post(`/event-bookings/${b.id}/cancel`, { reason: 'Cancelled by the business' }); toast('Booking cancelled', 'ok'); reload();
      } }) : null]);
  }
  try { await draw(); } catch (e) { m.setBody(h('div', { class: 'callout bad' }, e.message)); }
}

export function render(ctx) {
  const canManage = ctx.can('event_bookings:manage');
  return h('div', {}, pageHead('Event bookings', 'Seats booked on your events through the API. Check each payment, then confirm it.'), withDocs('event_bookings', () => manage(canManage)));
}

async function manage(canManage) {
  let q = '';
  const search = inp({ type: 'search', placeholder: 'Search name, phone, email or booking code', maxlength: 100 });
  const t = tabs(STATUS.map(([id, text]) => ({
    id: id || 'ALL', label: text,
    render: async () => {
      const page = await get('/event-bookings', { status: id, q, limit: 200 });
      const reload = () => t.refresh();
      return table([
        { label: 'Booked', render: (b) => fmtDateTime(b.created_at) },
        { label: 'Code', render: (b) => h('b', {}, raw(b.booking_ref)) },
        { label: 'Customer', render: (b) => h('div', {}, raw(b.customer_info_json.name || '-'), h('div', { class: 'muted' }, raw(b.customer_info_json.phone || ''))) },
        { label: 'Event', render: (b) => raw(b.event_title || '-') },
        { label: 'Seats', class: 'num', render: (b) => raw(String(b.seats)) },
        { label: 'Paid / total', class: 'num', render: (b) => raw(`${money(b.paid_amount, b.currency)} / ${money(b.total_amount, b.currency)}`) },
        { label: 'Status', render: (b) => badge(b.status, label(b.status)) },
      ], page.items, { onRowClick: (b) => open(b.id, canManage, reload), empty: id === 'PAYMENT_SUBMITTED' ? 'No payments are waiting. Bookings from your website appear here.' : 'No bookings here.' });
    },
  })), { initial: 'PAYMENT_SUBMITTED' });
  search.addEventListener('input', debounce(() => { q = search.value.trim(); t.refresh(); }, 300));
  return h('div', {}, h('div', { class: 'toolbar' }, search), t);
}

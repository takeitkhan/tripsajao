// Partner portal: what a sales / MoU partner sees after signing in.
import { get, post } from '../api.js';
import { h, btn, field, inp, area, sel, modal, tabs, table, badge, pageHead, figures, money, fmtDate, fmtDateTime, humanize, toast, copyBtn } from '../ui.js';
import { detailsText } from './payouts.js';

let portalTabs;

export function render() {
  portalTabs = tabs([
    { id: 'overview', label: 'Overview', render: overview },
    { id: 'bookings', label: 'Bookings', render: bookings },
    { id: 'ledger', label: 'Statement', render: ledger },
    { id: 'payouts', label: 'Payouts', render: payouts },
  ]);
  return h('div', {}, pageHead('My dashboard', 'Your bookings, commission and payouts.'), portalTabs);
}

async function overview() {
  const d = await get('/partners/me/dashboard');
  return h('div', { class: 'stack' },
    figures([{ value: d.confirmed_bookings, label: 'Confirmed bookings' }, { value: money(d.gross_sales), label: 'Sales' }, { value: money(d.commission_earned), label: 'Commission earned' },
      { value: money(d.paid_out), label: 'Paid out' }, { value: money(d.available_for_payout), label: 'Available to withdraw' }]),
    h('div', { class: 'callout' }, h('b', {}, 'Your short link. '), 'Guests who open it and book are credited to you for 30 days.',
      h('div', { class: 'secret', style: { marginTop: '10px' } }, h('span', {}, d.short_link), copyBtn(d.short_link))),
    h('p', { class: 'muted' }, `You can request a payout once ${money(d.min_payout)} or more is available. Amounts already requested are set aside: ${money(d.reserved_for_payouts)}.`));
}

async function bookings() {
  const page = await get('/partners/me/bookings', { limit: 100 });
  return table([
    { label: 'Reference', render: (b) => h('b', {}, b.booking_ref) },
    { label: 'Stay', render: (b) => `${fmtDate(b.check_in)} to ${fmtDate(b.check_out)}` },
    { label: 'Total', class: 'num', render: (b) => money(b.total_amount) },
    { label: 'Paid', class: 'num', render: (b) => money(b.paid_amount) },
    { label: 'Your commission', class: 'num', render: (b) => money(b.commission_amount) },
    { label: 'Status', render: (b) => badge(b.status) },
  ], page.items, { empty: 'No bookings yet. Share your short link to start earning.' });
}

async function ledger() {
  const s = await get('/partners/me/ledger', { limit: 200 });
  return h('div', { class: 'stack' },
    figures([{ value: money(s.total_credit), label: 'Earned' }, { value: money(s.total_debit), label: 'Paid or reversed' }, { value: money(s.closing_balance), label: 'Balance' }]),
    table([
      { label: 'Date', render: (e) => fmtDateTime(e.created_at) }, { label: 'Type', render: (e) => humanize(e.transaction_type) }, { label: 'Note', render: (e) => e.note || '-' },
      { label: 'Credit', class: 'num', render: (e) => (Number(e.credit) ? money(e.credit) : '') }, { label: 'Debit', class: 'num', render: (e) => (Number(e.debit) ? money(e.debit) : '') },
      { label: 'Balance', class: 'num', render: (e) => money(e.balance) },
    ], s.entries, { empty: 'Your statement is empty until a booking you referred is paid.' }));
}

function requestModal(available, onDone) {
  const amount = inp({ type: 'number', min: '0.01', step: '0.01', value: available });
  const method = sel([['BANK', 'Bank transfer'], ['MOBILE_WALLET', 'Mobile wallet'], ['MANUAL', 'Other']], 'BANK');
  const holder = inp({ maxlength: 200 }); const number = inp({ maxlength: 60 }); const bank = inp({ maxlength: 120 }); const routing = inp({ maxlength: 60 }); const note = area({ rows: 2, maxlength: 300 });
  const m = modal({
    title: 'Request a payout',
    body: [h('div', { class: 'form-grid' }, field('Amount', amount, `Available: ${money(available)}`), field('Method', method), field('Account holder', holder), field('Account or wallet number', number), field('Bank name', bank), field('Routing code', routing)), field('Note', note)],
    actions: [btn('Cancel', { onClick: () => m.close() }),
      btn('Send request', { kind: 'primary', onClick: async () => {
        await post('/payouts', { amount: Number(amount.value).toFixed(2), payout_details: { method: method.value, account_name: holder.value.trim(), account_number: number.value.trim(), ...(bank.value.trim() ? { bank_name: bank.value.trim() } : {}), ...(routing.value.trim() ? { routing_code: routing.value.trim() } : {}), ...(note.value.trim() ? { note: note.value.trim() } : {}) } });
        toast('Payout requested', 'ok'); m.close(); onDone();
      } })],
  });
}

async function payouts() {
  const [d, page] = await Promise.all([get('/partners/me/dashboard'), get('/payouts', { limit: 100 })]);
  const root = h('div', { class: 'stack' });
  root.append(
    h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('span', {}, 'Available to withdraw: ', h('b', {}, money(d.available_for_payout))),
      btn('Request payout', { kind: 'primary', onClick: () => requestModal(d.available_for_payout, () => portalTabs.refresh()) })),
    table([
      { label: 'Requested', render: (p) => fmtDateTime(p.created_at) }, { label: 'Amount', class: 'num', render: (p) => money(p.amount) },
      { label: 'Pay to', render: (p) => detailsText(p.payout_details) }, { label: 'Status', render: (p) => badge(p.status) }, { label: 'Note', render: (p) => p.review_note || '' },
    ], page.items, { empty: 'No payout requests yet.' }));
  return root;
}

import { t } from '../i18n.js';
// Partner rooms: the reseller's desk. Find free rooms of the businesses you sell for, hold one, record the guest's payment.
import { get, post } from '../api.js';
import {
  h, btn, field, inp, area, sel, modal, table, tabs, badge, emptyState, pageHead, toast, humanize, fmtDate, money, today, addDays, nightsBetween, reportError, facilityChip,
} from '../ui.js';
import { withDocs } from '../docs.js';

const commissionText = (type, value) => (type === 'PERCENT' ? `${Number(value)}% per night` : `${Number(value)} per night`);

export function render(ctx) {
  return h('div', {}, pageHead('Partner rooms', 'Sell rooms of the businesses that let you. The guest pays the owner; you earn the commission.'), withDocs('channel', () => manage(ctx)));
}

async function manage(ctx) {
  const t = tabs([
    { id: 'find', label: 'Find rooms', render: () => findTab(ctx, () => t.show('mine')) },
    { id: 'mine', label: 'My bookings', render: () => bookingsTab(ctx) },
  ]);
  return t;
}

// ------------------------------------------------------------ find rooms
async function findTab(ctx, afterBook) {
  const props = await get('/channel/properties');
  if (!props.length) return emptyState('No rooms to sell yet. Ask a business to let you sell its rooms under Resellers.', h('a', { class: 'btn primary', href: '#/resellers' }, 'Go to Resellers'));
  const key = (p) => `${p.agreement_id}|${p.property_id}`;
  const saved = sessionStorage.getItem('kt.pr.prop');
  const prop = sel(props.map((p) => [key(p), `${p.name} - ${p.owner}`]), props.some((p) => key(p) === saved) ? saved : key(props[0]));
  const ci = inp({ type: 'date', value: today(), min: today() });
  const co = inp({ type: 'date', value: addDays(today(), 1) });
  const guests = inp({ type: 'number', min: 1, max: 100, value: 2 });
  const info = h('div', {});
  const results = h('div', {});
  const current = () => props.find((p) => key(p) === prop.value);
  function drawInfo() {
    const p = current();
    info.replaceChildren(h('div', { class: 'muted' }, [p.location, `Your commission: ${commissionText(p.commission_type, p.commission_value)}`].filter(Boolean).join(' - ')),
      p.description ? h('p', { style: { margin: '6px 0 0' } }, p.description) : null);
  }
  async function search() {
    if (co.value <= ci.value) { toast('Check-out must be after check-in.', 'error'); return; }
    sessionStorage.setItem('kt.pr.prop', prop.value);
    const p = current();
    results.replaceChildren(h('div', { class: 'spinner' }));
    const units = await get('/channel/availability', { agreement_id: p.agreement_id, property_id: p.property_id, check_in: ci.value, check_out: co.value, guests: guests.value });
    results.replaceChildren(units.length ? h('div', { class: 'stack-sm' }, units.map((u) => h('div', { class: 'panel' },
      h('div', { class: 'panel-head' }, h('h3', {}, u.unit_name), h('b', {}, money(u.total, u.currency))),
      h('div', { class: 'muted' }, `${humanize(u.unit_type)}, up to ${u.capacity} guests, ${u.nights} night${u.nights === 1 ? '' : 's'}`),
      u.facilities?.length ? h('div', { class: 'chips' }, u.facilities.slice(0, 8).map(facilityChip)) : null,
      h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('span', { class: 'muted' }, `Your commission: ${money(u.your_commission, u.currency)}`),
        ctx.can('channel:book') ? btn('Book this room', { kind: 'primary', onClick: () => bookModal(p, u, ci.value, co.value, Number(guests.value), () => { search().catch(reportError); afterBook?.(); }) }) : null))))
      : emptyState('No free rooms for those dates. Try other dates or another property.'));
  }
  prop.addEventListener('change', () => { drawInfo(); results.replaceChildren(); });
  drawInfo();
  return h('div', { class: 'stack' },
    h('div', { class: 'toolbar' }, field('Property', prop), field('Check-in', ci), field('Check-out', co), field('Guests', guests), btn('Search', { kind: 'primary', icon: 'search', onClick: search })),
    info, results);
}

// ------------------------------------------------------------ booking dialog: guest details -> 10-minute hold -> payment
function bookModal(p, u, checkIn, checkOut, guestCount, done) {
  const name = inp({ maxlength: 200, autocomplete: 'off' });
  const email = inp({ type: 'email' });
  const phone = inp({ type: 'tel', maxlength: 40 });
  const notes = area({ rows: 2, maxlength: 1000 });
  let timer = null; let holdInfo = null;
  const stop = () => { clearInterval(timer); timer = null; };
  const m = modal({ title: `Book ${u.unit_name} - ${p.name}`, wide: true, onClose: stop, body: [], actions: [] });

  const stayLine = h('div', { class: 'callout' }, `${fmtDate(checkIn)} to ${fmtDate(checkOut)}, ${nightsBetween(checkIn, checkOut)} night${nightsBetween(checkIn, checkOut) === 1 ? '' : 's'}, ${guestCount} guest${guestCount === 1 ? '' : 's'}. Price ${money(u.total, u.currency)} (set by ${p.owner}).`);

  function step1() {
    m.setBody([stayLine, h('div', { class: 'form-grid' }, field('Guest name', name), field('Guest email', email), field('Guest phone', phone)), field('Notes (optional)', notes),
      h('p', { class: 'muted', style: { margin: 0 } }, 'Next, the room is held for 10 minutes while the guest pays the owner.')]);
    m.setActions([btn('Cancel', { onClick: () => m.close() }), btn('Hold this room', { kind: 'primary', onClick: async () => {
      holdInfo = await post('/channel/hold', { agreement_id: p.agreement_id, property_id: p.property_id, unit_id: u.unit_id, check_in: checkIn, check_out: checkOut, guests: guestCount,
        customer: { name: name.value.trim(), email: email.value.trim(), phone: phone.value.trim() || null, notes: notes.value.trim() || null } });
      step2();
    } })]);
  }

  function step2() {
    const h0 = holdInfo;
    const left = h('b', {});
    const deadline = Date.now() + h0.seconds_remaining * 1000;
    const tick = () => {
      const s = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      left.textContent = t(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`);
      if (s === 0) { stop(); m.setBody(h('div', { class: 'callout bad' }, 'The hold ran out and the room is free again. Start again if the guest still wants it.')); m.setActions([btn('Close', { onClick: () => { m.close(); done(); } })]); }
    };
    tick(); timer = setInterval(tick, 1000);
    const mode = sel([['FULL', `Full payment (${money(h0.total_amount, h0.currency)})`], ['PARTIAL', `Deposit (${money(h0.deposit_amount, h0.currency)})`]], 'FULL');
    const amount = inp({ type: 'number', min: 0, step: '0.01', value: h0.total_amount });
    mode.addEventListener('change', () => { amount.value = mode.value === 'FULL' ? h0.total_amount : h0.deposit_amount; });
    const ref = inp({ maxlength: 100, placeholder: 'e.g. the bKash or bank transaction id' });
    m.setBody([h('div', { class: 'callout warn' }, 'Room held for ', left, '. Reference ', h('b', {}, h0.booking_ref), '.'),
      h('p', { style: { margin: 0 } }, `Ask the guest to pay ${p.owner} directly. Once the owner has the money, enter the payment details below to confirm the booking.`),
      h('div', { class: 'form-grid' }, field('Payment', mode), field('Amount paid to the owner', amount), field('Payment reference', ref, 'Used to avoid recording the same payment twice'))]);
    m.setActions([btn('Give up this hold', { onClick: async () => { stop(); try { await post(`/channel/bookings/${h0.booking_id}/release?agreement_id=${p.agreement_id}`); } catch { /* already gone */ } m.close(); done(); } }),
      btn('Confirm booking', { kind: 'primary', onClick: async () => {
        const r = await post('/channel/confirm', { agreement_id: p.agreement_id, booking_id: h0.booking_id, payment_mode: mode.value, amount: Number(amount.value), payment_reference: ref.value.trim() });
        stop();
        m.setBody([h('div', { class: 'callout' }, `Booking ${r.booking_ref} is confirmed. ${r.payment_state === 'PAID' ? 'Paid in full.' : `Balance due: ${money(r.balance_due, h0.currency)}, to be paid to the owner.`}`),
          h('p', { class: 'muted', style: { margin: 0 } }, `Your commission is ${money(u.your_commission, u.currency)}. It becomes payable after the guest checks out.`)]);
        m.setActions([btn('Done', { kind: 'primary', onClick: () => { m.close(); done(); } })]);
      } })]);
  }
  step1();
}

// ------------------------------------------------------------ my bookings
async function bookingsTab(ctx) {
  const status = sel([['', 'All'], ['CONFIRMED', 'Confirmed'], ['HOLD', 'On hold'], ['CANCELLED', 'Cancelled']], '');
  const holder = h('div', {});
  const PAGE = 25; let offset = 0;
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const page = await get('/channel/bookings', { status: status.value, limit: PAGE, offset });
    holder.replaceChildren(
      page.unavailable.length ? h('div', { class: 'callout warn' }, `Bookings of ${page.unavailable.join(', ')} cannot be shown right now because that business is not active.`) : null,
      table([
        { label: 'Reference', render: (b) => h('b', {}, b.booking_ref) },
        { label: 'Guest', render: (b) => h('div', {}, b.customer?.name || '-', h('div', { class: 'muted' }, b.customer?.phone || b.customer?.email || '')) },
        { label: 'Where', render: (b) => h('div', {}, `${b.unit} - ${b.property}`, h('div', { class: 'muted' }, b.owner)) },
        { label: 'Stay', render: (b) => `${fmtDate(b.check_in)} (${b.nights} night${b.nights === 1 ? '' : 's'})` },
        { label: 'Total', class: 'num', render: (b) => money(b.total_amount, b.currency) },
        { label: 'Owner has', class: 'num', render: (b) => money(b.paid_amount, b.currency) },
        { label: 'Your commission', class: 'num', render: (b) => money(b.your_commission, b.currency) },
        { label: 'Status', render: (b) => h('div', {}, badge(b.status), cancelNote(b)) },
        { label: '', render: (b) => (ctx.can('channel:book') && b.status === 'CONFIRMED' && b.check_in >= today() && b.cancellation?.status !== 'REQUESTED'
          ? btn('Cancel...', { kind: 'sm', onClick: () => cancelModal(b, load) }) : null) },
      ], page.items, { empty: 'No bookings yet. Find a room, hold it, and confirm when the guest has paid the owner.' }),
      h('div', { class: 'pager' }, h('span', {}, page.total ? `${offset + 1}-${Math.min(offset + PAGE, page.total)} of ${page.total}` : ''),
        h('div', { class: 'row' }, btn('Previous', { kind: 'sm', onClick: () => { offset = Math.max(0, offset - PAGE); return load(); } }),
          btn('Next', { kind: 'sm', onClick: () => { if (offset + PAGE < page.total) { offset += PAGE; return load(); } } }))));
  }
  status.addEventListener('change', () => { offset = 0; load().catch(reportError); });
  await load();
  return h('div', {}, h('div', { class: 'toolbar' }, field('Show', status)), holder);
}


const cancelNote = (b) => {
  const c = b.cancellation;
  if (!c) return null;
  if (c.status === 'REQUESTED') return h('div', { class: 'muted' }, 'Cancellation requested. Waiting for the owner.');
  if (c.status === 'CONFIRMED') return h('div', { class: 'muted' }, `Owner agreed a refund of ${money(c.refund_amount, b.currency)}.`);
  if (c.status === 'DECLINED') return h('div', { class: 'muted' }, `Owner kept the booking: ${c.decision_note || ''}`);
  return null;
};

async function cancelModal(b, reload) {
  const q = await get(`/channel/bookings/${b.id}/cancel-quote`, { agreement_id: b.agreement_id });
  if (!q.can_request) { toast(q.why_not, 'error'); return; }
  const why = area({ rows: 3, maxlength: 500, placeholder: 'Why does the guest want to cancel?' });
  const m = modal({ title: `Cancel ${b.booking_ref}`, body: [
    h('p', {}, q.rule_text),
    h('p', {}, h('b', {}, `Suggested refund: ${money(q.refund_amount, q.currency)}`), ` of ${money(q.paid_amount, q.currency)} paid. The owner decides the final amount and refunds the guest directly.`),
    field('Reason', why)],
  actions: [btn('Keep the booking', { onClick: () => m.close() }), btn('Ask the owner to cancel', { kind: 'danger', onClick: async () => {
    if (why.value.trim().length < 3) throw new Error('Please write a few words about the reason.');
    await post(`/channel/bookings/${b.id}/cancel-request`, { agreement_id: b.agreement_id, reason: why.value.trim() });
    toast('Request sent to the owner.', 'ok'); m.close(); await reload();
  } })] });
}

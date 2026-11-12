import { t } from '../i18n.js';
import { get, post } from '../api.js';
import { lookups, invalidate, unitLabel } from '../data.js';
import {
  h, btn, field, inp, area, sel, modal, confirmDialog, table, badge, emptyState, pageHead, figures, money, fmtDate,
  fmtDateTime, today, addDays, nightsBetween, facilityChip, toast, humanize, reportError,
} from '../ui.js';
import { withDocs } from '../docs.js';

const PAGE = 20;

// ---------------------------------------------------------------- booking detail
export async function openBookingDetail(id, onChange) {
  const m = modal({ title: 'Booking', wide: true, body: h('div', { class: 'spinner' }) });
  async function draw() {
    const [b, lk] = await Promise.all([get(`/bookings/${id}`), lookups()]);
    const due = Number(b.total_amount) - Number(b.paid_amount);
    const partner = b.channel_name ? `Sold by ${b.channel_name} (reseller)` : b.partner_id ? lk.partners[b.partner_id]?.name || 'Partner' : 'Direct';
    const nights = b.price_breakdown?.nights || [];
    m.setBody([
      h('div', { class: 'row', style: { justifyContent: 'space-between' } },
        h('div', {}, h('h3', {}, b.booking_ref), h('div', { class: 'muted' }, unitLabel(lk, b.unit_id))),
        badge(b.status)),
      b.status === 'HOLD' && b.hold_expires_at ? h('div', { class: 'callout warn' }, 'Held until ', fmtDateTime(b.hold_expires_at), '. The unit is released automatically after that.') : null,
      b.status === 'CANCELLED' ? h('div', { class: 'callout bad' }, 'Cancelled', b.cancel_reason ? ': ' + humanize(b.cancel_reason) : '', '.') : null,
      h('dl', { class: 'kv' },
        h('dt', {}, 'Guest'), h('dd', {}, b.customer?.name || '-', b.customer?.email ? ` (${b.customer.email})` : '', b.customer?.phone ? ` ${b.customer.phone}` : ''),
        h('dt', {}, 'Stay'), h('dd', {}, `${fmtDate(b.check_in)} to ${fmtDate(b.check_out)} (${nightsBetween(b.check_in, b.check_out)} nights, ${b.guests} guests)`),
        h('dt', {}, 'Source'), h('dd', {}, partner),
        h('dt', {}, 'Total'), h('dd', {}, money(b.total_amount, b.currency)),
        h('dt', {}, 'Paid'), h('dd', {}, money(b.paid_amount, b.currency)),
        h('dt', {}, 'Balance due'), h('dd', {}, h('b', {}, money(due, b.currency))),
        b.partner_id ? [h('dt', {}, 'Partner commission'), h('dd', {}, money(b.commission_amount, b.currency))] : null,
        b.channel_name ? [h('dt', {}, 'Reseller commission'), h('dd', {}, `${money(b.channel_commission_amount, b.currency)} owed to ${b.channel_name} after check-out`)] : null,
        b.payments?.some((p) => p.recorded_by) ? [h('dt', {}, 'Payment recorded by'), h('dd', {}, b.payments.filter((p) => p.recorded_by).map((p) => p.recorded_by.replace('reseller:', '')).join(', '))] : null,
        b.customer?.notes ? [h('dt', {}, 'Notes'), h('dd', {}, b.customer.notes)] : null),
      nights.length ? h('div', {}, h('h3', { style: { marginBottom: '6px' } }, 'Price by night'),
        table([
          { label: 'Night', render: (n) => fmtDate(n.night) },
          { label: 'Rate', render: (n) => humanize(n.day_type) },
          { label: 'Adjustments', render: (n) => (n.applied_rules.length ? n.applied_rules.join(', ') : '-') },
          { label: 'Price', class: 'num', render: (n) => money(n.price, b.currency) },
        ], nights)) : null,
      b.payments?.length ? h('div', {}, h('h3', { style: { marginBottom: '6px' } }, 'Payments'),
        table([
          { label: 'When', render: (p) => fmtDateTime(p.at) },
          { label: 'Reference', render: (p) => p.reference },
          { label: 'Method', render: (p) => humanize(p.gateway) },
          { label: 'Amount', class: 'num', render: (p) => money(p.amount, b.currency) },
        ], b.payments)) : null,
    ]);
    const actions = [];
    if (b.status !== 'CANCELLED') {
      actions.push(btn('Cancel booking', { kind: 'danger', onClick: () => cancelFlow(b, m, onChange) }));
    }
    if (b.status !== 'CANCELLED' && due > 0) {
      actions.push(btn('Record payment', { kind: 'primary', icon: 'banknote', onClick: () => paymentFlow(b, async () => { await draw(); onChange?.(); }) }));
    }
    m.setActions(actions);
  }
  try { await draw(); } catch (e) { m.close(); throw e; }
}

async function cancelFlow(b, m, onChange) {
  const reason = inp({ value: 'Cancelled by staff', maxlength: 100 });
  const c = modal({
    title: `Cancel ${b.booking_ref}`,
    body: [h('p', {}, 'The unit becomes available again. Any partner commission already earned on this booking is reversed.'), field('Reason', reason)],
    actions: [
      btn('Keep booking', { onClick: () => c.close() }),
      btn('Cancel booking', { kind: 'danger', onClick: async () => {
        await post(`/bookings/${b.id}/cancel`, { reason: reason.value.trim() || 'Cancelled by staff' });
        toast('Booking cancelled'); invalidate(); c.close(); m.close(); onChange?.();
      } }),
    ],
  });
}

function paymentFlow(b, done) {
  const due = (Number(b.total_amount) - Number(b.paid_amount)).toFixed(2);
  const mode = sel([['FULL', 'Pay the full balance'], ['PARTIAL', 'Pay a deposit / part payment']], 'FULL');
  const amount = inp({ type: 'number', step: '0.01', min: '0.01', value: due });
  const method = sel([['cash', 'Cash'], ['bank', 'Bank transfer'], ['card', 'Card'], ['mobile_wallet', 'Mobile wallet'], ['manual', 'Other']], 'cash');
  const ref = inp({ value: 'PAY-' + Date.now().toString(36).toUpperCase(), maxlength: 100 });
  mode.addEventListener('change', () => { if (mode.value === 'FULL') amount.value = due; });
  const p = modal({
    title: `Record payment for ${b.booking_ref}`,
    body: [
      h('p', { class: 'muted' }, `Balance due: ${money(due, b.currency)}`),
      h('div', { class: 'form-grid' }, field('Payment type', mode), field('Amount', amount, b.status === 'HOLD' ? 'A held booking needs at least the deposit to be confirmed.' : null),
        field('Method', method), field('Reference', ref, 'Receipt or transaction number. Each reference can be used once.')),
    ],
    actions: [
      btn('Cancel', { onClick: () => p.close() }),
      btn('Save payment', { kind: 'primary', onClick: async () => {
        await post('/bookings/confirm', {
          booking_id: b.id, payment_mode: mode.value, amount: Number(amount.value).toFixed(2),
          payment_reference: ref.value.trim(), gateway: method.value,
        });
        toast('Payment saved', 'ok'); p.close(); await done();
      } }),
    ],
  });
}

// ---------------------------------------------------------------- new booking
export async function openNewBooking(opts = {}) {
  const lk = await lookups();
  const props = lk.propertyList.filter((p) => p.is_active);
  if (!props.length) { toast('Add a property first.', 'error'); return; }
  const prop = sel(props.map((p) => [p.id, p.name]), opts.propertyId && lk.properties[opts.propertyId] ? opts.propertyId : props[0].id);
  const ci = inp({ type: 'date', min: today(), value: opts.checkIn || today() });
  const co = inp({ type: 'date', min: today(), value: opts.checkOut || addDays(opts.checkIn || today(), 1) });
  const guests = inp({ type: 'number', min: 1, value: 2 });
  const results = h('div', { class: 'pick-list' });
  const name = inp({ maxlength: 200 }), email = inp({ type: 'email' }), phone = inp({ type: 'tel', maxlength: 40 }), notes = area({ rows: 2, maxlength: 1000 });
  let chosen = opts.unitId || null;
  let timer = null;

  const m = modal({ title: 'New booking', wide: true, body: [], onClose: () => clearInterval(timer) });

  async function search() {
    if (co.value <= ci.value) { toast('Check-out must be after check-in.', 'error'); return; }
    results.replaceChildren(h('div', { class: 'spinner' }));
    const list = await get('/bookings/availability', { property_id: prop.value, check_in: ci.value, check_out: co.value, guests: guests.value || 1 });
    if (!list.length) { results.replaceChildren(emptyState('No units are free for these dates. Try other dates or fewer guests.')); chosen = null; return; }
    if (!list.some((u) => u.unit_id === chosen)) chosen = list[0].unit_id;
    results.replaceChildren(...list.map((u) => h('label', { class: 'pick' },
      h('input', { type: 'radio', name: 'unit', checked: u.unit_id === chosen, onchange: () => { chosen = u.unit_id; } }),
      h('div', {}, h('b', {}, u.unit_name), h('span', { class: 'muted' }, `  ${humanize(u.unit_type)}, sleeps ${u.capacity}`),
        u.facilities.length ? h('div', { class: 'chips', style: { marginTop: '6px' } }, u.facilities.slice(0, 4).map(facilityChip)) : null),
      h('b', {}, money(u.total, u.currency)))));
  }

  async function hold() {
    if (!chosen) throw new Error('Choose a unit first.');
    if (!name.value.trim()) throw new Error('Enter the guest name.');
    if (!email.value.trim()) throw new Error('Enter the guest email.');
    const hd = await post('/bookings/hold', {
      unit_id: chosen, check_in: ci.value, check_out: co.value, guests: Number(guests.value || 1),
      customer: { name: name.value.trim(), email: email.value.trim(), ...(phone.value.trim() ? { phone: phone.value.trim() } : {}), ...(notes.value.trim() ? { notes: notes.value.trim() } : {}) },
    });
    invalidate(); opts.onDone?.();
    paymentStep(hd);
  }

  function paymentStep(hd) {
    const deadline = Date.now() + hd.seconds_remaining * 1000;
    const mode = sel([['FULL', `Full payment (${money(hd.total_amount, hd.currency)})`], ['PARTIAL', `Deposit (${money(hd.deposit_amount, hd.currency)})`]], 'FULL');
    const amount = inp({ type: 'number', step: '0.01', min: '0.01', value: hd.total_amount });
    const method = sel([['cash', 'Cash'], ['bank', 'Bank transfer'], ['card', 'Card'], ['mobile_wallet', 'Mobile wallet'], ['manual', 'Other']], 'cash');
    const ref = inp({ value: 'PAY-' + Date.now().toString(36).toUpperCase(), maxlength: 100 });
    mode.addEventListener('change', () => { amount.value = mode.value === 'FULL' ? hd.total_amount : hd.deposit_amount; });
    const clock = h('b', {});
    let confirmBtn;
    const tick = () => {
      const s = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      clock.textContent = t(s > 0 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : 'expired');
      if (s === 0) { clearInterval(timer); if (confirmBtn) confirmBtn.disabled = true; }
    };
    timer = setInterval(tick, 1000);
    m.setBody([
      h('div', { class: 'callout warn' }, 'Unit held for the guest. Time left to take payment: ', clock, '. Closing this window keeps the hold until the timer ends.'),
      h('dl', { class: 'kv' },
        h('dt', {}, 'Booking'), h('dd', {}, hd.booking_ref),
        h('dt', {}, 'Stay'), h('dd', {}, `${fmtDate(hd.check_in)} to ${fmtDate(hd.check_out)} (${hd.nights} nights)`),
        h('dt', {}, 'Total'), h('dd', {}, h('b', {}, money(hd.total_amount, hd.currency)))),
      h('div', { class: 'form-grid' }, field('Payment type', mode), field('Amount received', amount), field('Method', method), field('Reference', ref)),
    ]);
    confirmBtn = btn('Confirm booking', { kind: 'primary', icon: 'check', onClick: async () => {
      await post('/bookings/confirm', { booking_id: hd.booking_id, payment_mode: mode.value, amount: Number(amount.value).toFixed(2), payment_reference: ref.value.trim(), gateway: method.value });
      toast('Booking confirmed', 'ok'); invalidate(); opts.onDone?.(); m.close();
    } });
    m.setActions([
      btn('Release hold', { onClick: async () => {
        if (!(await confirmDialog('Release this hold and free the unit?', { confirmText: 'Release hold', danger: true }))) return;
        await post(`/bookings/${hd.booking_id}/cancel`, { reason: 'HOLD_RELEASED_BY_STAFF' });
        invalidate(); opts.onDone?.(); m.close();
      } }),
      confirmBtn,
    ]);
    tick();
  }

  m.setBody([
    h('div', { class: 'form-grid' }, field('Property', prop), field('Check-in', ci), field('Check-out', co), field('Guests', guests)),
    h('div', {}, btn('Find available units', { icon: 'search', onClick: search })),
    results,
    h('h3', {}, 'Guest'),
    h('div', { class: 'form-grid' }, field('Full name', name), field('Email', email), field('Phone', phone), field('Notes', notes)),
  ]);
  m.setActions([btn('Cancel', { onClick: () => m.close() }), btn('Hold unit and take payment', { kind: 'primary', onClick: hold })]);
  search().catch(reportError);
}

// ---------------------------------------------------------------- page
export function render() {
  return h('div', {}, pageHead('Bookings', 'Stays booked by staff, your website and partners.'), withDocs('bookings', manage));
}

async function manage() {
  const root = h('div');
  const status = sel([['', 'All statuses'], ['CONFIRMED', 'Confirmed'], ['HOLD', 'On hold'], ['CANCELLED', 'Cancelled']], '');
  const holder = h('div');
  let offset = 0;

  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const [page, lk] = await Promise.all([get('/bookings', { status: status.value, limit: PAGE, offset }), lookups()]);
    const live = page.items.filter((b) => b.status === 'CONFIRMED');
    holder.replaceChildren(
      table([
        { label: 'Reference', render: (b) => h('b', {}, b.booking_ref) },
        { label: 'Guest', render: (b) => b.customer?.name || '-' },
        { label: 'Unit', render: (b) => unitLabel(lk, b.unit_id) },
        { label: 'Stay', render: (b) => `${fmtDate(b.check_in)} (${nightsBetween(b.check_in, b.check_out)} nights)` },
        { label: 'Total', class: 'num', render: (b) => money(b.total_amount, b.currency) },
        { label: 'Paid', class: 'num', render: (b) => money(b.paid_amount, b.currency) },
        { label: 'Source', render: (b) => (b.channel_name ? `Reseller: ${b.channel_name}` : b.partner_id ? lk.partners[b.partner_id]?.name || 'Partner' : 'Direct') },
        { label: 'Status', render: (b) => badge(b.status) },
      ], page.items, { onRowClick: (b) => openBookingDetail(b.id, load), empty: 'No bookings match. New bookings from your website and from staff appear here.' }),
      h('div', { class: 'pager' },
        h('span', {}, page.total ? `${offset + 1}-${Math.min(offset + PAGE, page.total)} of ${page.total}` : ''),
        h('div', { class: 'row' },
          btn('Previous', { kind: 'sm', onClick: () => { offset = Math.max(0, offset - PAGE); return load(); } }),
          btn('Next', { kind: 'sm', onClick: () => { if (offset + PAGE < page.total) { offset += PAGE; return load(); } } }))));
  }
  status.addEventListener('change', () => { offset = 0; load().catch(reportError); });
  root.append(
    h('div', { class: 'toolbar' }, h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Show'), status),
      h('div', { style: { marginLeft: 'auto' } }, btn('New booking', { kind: 'primary', icon: 'plus', onClick: () => openNewBooking({ onDone: load }) }))),
    holder);
  await load();
  return root;
}

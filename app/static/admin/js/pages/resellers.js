import { t } from '../i18n.js';
// Resellers: businesses that sell your rooms (you are the owner), and businesses whose rooms you sell (you are the reseller).
import { get, post, put } from '../api.js';
import {
  h, btn, field, inp, area, sel, modal, confirmDialog, table, tabs, badge, emptyState, pageHead, toast, humanize, fmtDate, money,
} from '../ui.js';
import { withDocs } from '../docs.js';

const commissionText = (type, value) => (value === null || value === undefined ? '-' : type === 'PERCENT' ? `${Number(value)}% per night` : `${Number(value)} per night`);
const STATUS = { REQUESTED: 'warn', INVITED: 'warn', ACTIVE: 'ok', PAUSED: 'info', DECLINED: 'bad', ENDED: '' };
const statusBadge = (a) => h('span', { class: 'badge ' + (STATUS[a.status] || '') }, a.status === 'REQUESTED' ? 'Asked to sell' : a.status === 'INVITED' ? 'Invited' : humanize(a.status));
const propChips = (a) => h('div', { class: 'chips' }, a.properties.map((p) => h('span', { class: 'chip', title: p.is_default ? 'Default commission' : 'Own commission' },
  p.name, h('span', { class: 'muted' }, ` ${commissionText(p.commission_type, p.commission_value)}`))));

export function render(ctx) {
  return h('div', {}, pageHead('Resellers', 'Let other businesses sell your rooms, or sell rooms for other businesses.'), withDocs('channel', () => manage(ctx)));
}

async function manage(ctx) {
  const canManage = ctx.can('channel:manage');
  const t = tabs([
    { id: 'owner', label: 'Selling my rooms', render: () => ownerTab(canManage, () => t.refresh()) },
    { id: 'reseller', label: 'Rooms I sell', render: () => resellerTab(canManage, () => t.refresh()) },
  ], { initial: sessionStorage.getItem('kt.resellers.tab') || 'owner' });
  t.addEventListener('click', (e) => { const b = e.target.closest('[role=tab]'); if (b) sessionStorage.setItem('kt.resellers.tab', b.textContent.startsWith('Rooms') ? 'reseller' : 'owner'); });
  return t;
}

// ------------------------------------------------------------ owner side
async function ownerTab(canManage, reload) {
  const all = await get('/channel/agreements', { role: 'OWNER' });
  const waiting = all.filter((a) => a.status === 'REQUESTED');
  const sent = all.filter((a) => a.status === 'INVITED');
  const running = all.filter((a) => ['ACTIVE', 'PAUSED'].includes(a.status));
  const past = all.filter((a) => ['DECLINED', 'ENDED'].includes(a.status));
  const run = (fn, ok) => async () => { await fn(); if (ok) toast(ok, 'ok'); await reload(); };
  const cancels = await get('/channel/cancellations', { role: 'OWNER' });
  const policy = await get('/channel/cancellation-policy');
  const open = cancels.filter((c) => c.status === 'REQUESTED');
  const decided = cancels.filter((c) => c.status !== 'REQUESTED');
  return h('div', { class: 'stack' },
    open.length ? h('div', {}, h('h2', { class: 'section' }, 'Cancellation requests'), h('div', { class: 'stack-sm' }, open.map((c) => h('div', { class: 'panel' },
      h('div', { class: 'panel-head' }, h('h3', {}, `${c.booking_ref}: ${c.guest || 'Guest'}`), h('span', { class: 'muted' }, `${c.counterpart} asks to cancel`)),
      h('p', { class: 'muted' }, `${c.property}, ${fmtDate(c.check_in)} to ${fmtDate(c.check_out)}. Reason: ${c.reason}`),
      h('p', {}, `The guest paid ${money(c.paid_amount, c.currency)}. By your rules (${c.days_before} days before check-in: ${Number(c.refund_percent)}%) the refund is `, h('b', {}, money(c.suggested_refund, c.currency)), '.'),
      canManage ? h('div', { class: 'row' }, btn('Cancel and refund', { kind: 'primary', onClick: () => confirmCancelModal(c, reload) }),
        btn('Keep the booking', { onClick: () => declineCancelModal(c, reload) })) : null)))) : null,
    h('div', { class: 'row', style: { justifyContent: 'space-between' } },
      h('p', { class: 'muted', style: { margin: 0, maxWidth: '640px' } }, 'A reseller sells the properties you allow, at your prices. The guest pays you directly. You set the commission per night.'),
      canManage ? btn('Invite a reseller', { kind: 'primary', icon: 'user-plus', onClick: () => termsModal({ title: 'Invite a reseller', domainLabel: 'Reseller sign-in domain', onSave: async (t, domain) => { await post('/channel/agreements/invite', { reseller_domain: domain, ...t }); toast('Invitation sent', 'ok'); await reload(); } }) }) : null),
    waiting.length ? h('div', {}, h('h2', { class: 'section' }, 'Asking to sell your rooms'), h('div', { class: 'stack-sm' }, waiting.map((a) => h('div', { class: 'panel' },
      h('div', { class: 'panel-head' }, h('h3', {}, a.counterpart), statusBadge(a)),
      a.note ? h('p', { class: 'muted', style: { margin: 0 } }, `"${a.note}"`) : null,
      canManage ? h('div', { class: 'row' },
        btn('Accept and set terms', { kind: 'primary', onClick: () => termsModal({ title: `Let ${a.counterpart} sell your rooms`, onSave: async (t) => { await post(`/channel/agreements/${a.id}/accept`, t); toast('Accepted', 'ok'); await reload(); } }) }),
        btn('Decline', { onClick: run(() => post(`/channel/agreements/${a.id}/decline`), 'Declined') })) : null)))) : null,
    h('div', {}, h('h2', { class: 'section' }, 'Reseller agreements'),
      table([
        { label: 'Reseller', render: (a) => h('b', {}, a.counterpart) },
        { label: 'Status', render: statusBadge },
        { label: 'Properties and commission', render: propChips },
        { label: 'You pay', render: (a) => (a.settlement_mode === 'PER_BOOKING' ? `Within ${a.settlement_day} days of check-out` : `Monthly, by day ${a.settlement_day}`) },
        { label: '', render: (a) => (canManage ? h('div', { class: 'row' },
          btn('Edit terms', { kind: 'sm', onClick: () => termsModal({ title: `Terms for ${a.counterpart}`, current: a, onSave: async (t) => { await put(`/channel/agreements/${a.id}/terms`, t); toast('Terms saved. They apply to new bookings.', 'ok'); await reload(); } }) }),
          a.status === 'ACTIVE' ? btn('Pause', { kind: 'sm', onClick: run(() => post(`/channel/agreements/${a.id}/pause`), 'Paused') }) : btn('Resume', { kind: 'sm', onClick: run(() => post(`/channel/agreements/${a.id}/resume`), 'Resumed') }),
          btn('End', { kind: 'sm danger', onClick: async () => { if (await confirmDialog(`${a.counterpart} will not be able to make new bookings. Bookings already made stay, and so does the commission owed on them.`, { confirmText: 'End agreement', danger: true })) { await post(`/channel/agreements/${a.id}/end`); toast('Agreement ended'); await reload(); } } })) : null) },
      ], running, { empty: 'No reseller sells your rooms yet. Invite one, or wait for a request.' })),
    sent.length ? h('div', {}, h('h2', { class: 'section' }, 'Invitations sent'), table([
      { label: 'Invited', render: (a) => h('b', {}, a.counterpart) }, { label: 'Properties and commission', render: propChips },
      { label: '', render: (a) => (canManage ? btn('Take back', { kind: 'sm', onClick: run(() => post(`/channel/agreements/${a.id}/withdraw`), 'Invitation taken back') }) : null) }], sent)) : null,
    h('div', {}, h('h2', { class: 'section' }, 'Cancellation and refund rules'),
      h('p', { class: 'muted' }, 'When a reseller asks to cancel a booking it sold, the refund is worked out from these rules. You still decide, and you pay the guest yourself.'),
      h('ul', {}, policy.rules.map((r, i) => h('li', {}, i === 0 ? `${r.days_before} or more days before check-in: ${Number(r.refund_percent)}% back` : `${r.days_before} or more days: ${Number(r.refund_percent)}% back`))),
      h('p', { class: 'muted' }, ['Closer to check-in than the last rule: no refund.', policy.is_default ? ' (These are the standard rules. Change them to suit you.)' : null]),
      canManage ? btn('Change rules', { kind: 'sm', onClick: () => policyModal(policy, reload) }) : null),
    decided.length ? h('details', {}, h('summary', { class: 'muted' }, `Earlier cancellation requests (${decided.length})`), table([
      { label: 'Booking', render: (c) => c.booking_ref }, { label: 'Reseller', render: (c) => c.counterpart },
      { label: 'Result', render: (c) => (c.status === 'CONFIRMED' ? `Cancelled, refund ${money(c.refund_amount, c.currency)}` : c.status === 'DECLINED' ? 'Kept' : 'Taken back') },
      { label: 'When', render: (c) => fmtDate(c.decided_at || c.created_at) }], decided)) : null,
    past.length ? h('details', {}, h('summary', { class: 'muted' }, `Earlier agreements (${past.length})`), table([
      { label: 'Reseller', render: (a) => a.counterpart }, { label: 'Status', render: statusBadge }, { label: 'Last change', render: (a) => fmtDate(a.updated_at) }], past)) : null);
}

// ------------------------------------------------------------ reseller side
async function resellerTab(canManage, reload) {
  const all = await get('/channel/agreements', { role: 'RESELLER' });
  const invites = all.filter((a) => a.status === 'INVITED');
  const asked = all.filter((a) => a.status === 'REQUESTED');
  const running = all.filter((a) => ['ACTIVE', 'PAUSED'].includes(a.status));
  const past = all.filter((a) => ['DECLINED', 'ENDED'].includes(a.status));
  const run = (fn, ok) => async () => { await fn(); if (ok) toast(ok, 'ok'); await reload(); };
  return h('div', { class: 'stack' },
    h('div', { class: 'row', style: { justifyContent: 'space-between' } },
      h('p', { class: 'muted', style: { margin: 0, maxWidth: '640px' } }, 'Sell rooms of other businesses to your own guests, at the owner\'s prices. The guest pays the owner directly, and you earn the commission the owner set.'),
      canManage ? btn('Ask to sell for a business', { kind: 'primary', icon: 'handshake', onClick: askModal(reload) }) : null),
    invites.length ? h('div', {}, h('h2', { class: 'section' }, 'Invitations for you'), h('div', { class: 'stack-sm' }, invites.map((a) => h('div', { class: 'panel' },
      h('div', { class: 'panel-head' }, h('h3', {}, a.counterpart), h('span', { class: 'muted' }, `Default commission ${commissionText(a.commission_type, a.commission_value)}. Paid ${a.settlement_mode === 'PER_BOOKING' ? `within ${a.settlement_day} days of check-out` : `monthly, by day ${a.settlement_day}`}.`)), propChips(a),
      canManage ? h('div', { class: 'row' }, btn('Accept', { kind: 'primary', onClick: run(() => post(`/channel/agreements/${a.id}/accept`), 'You can now sell these rooms') }), btn('Decline', { onClick: run(() => post(`/channel/agreements/${a.id}/decline`), 'Declined') })) : null)))) : null,
    h('div', {}, h('h2', { class: 'section' }, 'Businesses you sell for'),
      table([
        { label: 'Owner', render: (a) => h('b', {}, a.counterpart) }, { label: 'Status', render: statusBadge },
        { label: 'Properties and commission', render: propChips },
        { label: '', render: (a) => h('div', { class: 'row' }, a.status === 'ACTIVE' ? h('a', { class: 'btn sm primary', href: '#/partner-rooms' }, 'Find rooms') : h('span', { class: 'muted' }, 'Paused by the owner'),
          canManage ? btn('Stop selling', { kind: 'sm', onClick: async () => { if (await confirmDialog('You will not be able to make new bookings for this business. Bookings already made stay, and so does your commission.', { confirmText: 'Stop selling', danger: true })) { await post(`/channel/agreements/${a.id}/end`); await reload(); } } }) : null) },
      ], running, { empty: 'You do not sell for any business yet. Ask one to let you sell its rooms.' })),
    asked.length ? h('div', {}, h('h2', { class: 'section' }, 'Waiting for an answer'), table([{ label: 'Asked', render: (a) => h('b', {}, a.counterpart) }, { label: 'Your note', render: (a) => a.note || '-' },
      { label: '', render: (a) => (canManage ? btn('Take back', { kind: 'sm', onClick: run(() => post(`/channel/agreements/${a.id}/withdraw`), 'Request taken back') }) : null) }], asked)) : null,
    past.length ? h('details', {}, h('summary', { class: 'muted' }, `Earlier agreements (${past.length})`), table([
      { label: 'Owner', render: (a) => a.counterpart }, { label: 'Status', render: statusBadge }, { label: 'Last change', render: (a) => fmtDate(a.updated_at) }], past)) : null);
}

const askModal = (reload) => () => {
  const domain = inp({ placeholder: 'their-business.com', autocapitalize: 'none' });
  const note = area({ rows: 3, maxlength: 500, placeholder: 'Who you are and what you sell (optional)' });
  const m = modal({ title: 'Ask to sell for a business', body: [field('Their sign-in domain', domain, 'Ask the owner for it. It is the domain they use to sign in.'), field('Message', note)],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Send request', { kind: 'primary', onClick: async () => { await post('/channel/agreements/request', { owner_domain: domain.value.trim().toLowerCase(), note: note.value.trim() || null }); toast('Request sent', 'ok'); m.close(); await reload(); } })] });
};

// ------------------------------------------------------------ terms form (owner)
async function termsModal({ title, current, domainLabel, onSave }) {
  const props = (await get('/properties', { limit: 200 })).items.filter((p) => p.is_active);
  if (!props.length) { toast('Add a property first, then you can let others sell it.', 'error'); return; }
  const domain = domainLabel ? inp({ placeholder: 'their-business.com', autocapitalize: 'none' }) : null;
  const type = sel([['PERCENT', 'Percent of the night\'s price'], ['FLAT', 'Fixed amount per night']], current?.commission_type || 'PERCENT');
  const value = inp({ type: 'number', min: 0, step: '0.01', value: current?.commission_value ?? '' });
  const note = area({ rows: 2, maxlength: 500, value: current?.note || '' });
  const mode = sel([['MONTHLY', 'Once a month, by a day of the month'], ['PER_BOOKING', 'Each booking, some days after check-out']], current?.settlement_mode || 'MONTHLY');
  const day = inp({ type: 'number', min: 1, max: 60, step: 1, value: current?.settlement_day ?? 10 });
  const dayField = field('', day);
  const dayLabel = () => { const l = dayField.querySelector('.field-label'); if (l) l.textContent = t(mode.value === 'MONTHLY' ? 'Pay by this day of the month (1 to 28)' : 'Pay within this many days after check-out'); };
  dayLabel();
  mode.addEventListener('change', () => { if (current?.settlement_mode !== mode.value) day.value = mode.value === 'MONTHLY' ? 10 : 7; dayLabel(); });
  const held = Object.fromEntries((current?.properties || []).map((p) => [p.property_id, p]));
  const rows = props.map((p) => {
    const g = held[p.id];
    const on = h('input', { type: 'checkbox', checked: !!g });
    const own = h('input', { type: 'checkbox', checked: !!g && !g.is_default });
    const ot = sel([['PERCENT', '%'], ['FLAT', 'amount']], g && !g.is_default ? g.commission_type : 'PERCENT');
    const ov = inp({ type: 'number', min: 0, step: '0.01', value: g && !g.is_default ? g.commission_value : '' });
    const detail = h('div', { class: 'row', style: { marginLeft: '28px' } }, h('label', { class: 'check' }, own, 'Different commission for this property'), ot, ov);
    const sync = () => { detail.hidden = !on.checked; ot.disabled = ov.disabled = !own.checked; };
    on.addEventListener('change', sync); own.addEventListener('change', sync); sync();
    return { p, on, own, ot, ov, el: h('div', { class: 'pick-row' }, h('label', { class: 'check' }, on, h('b', {}, p.name), h('span', { class: 'muted' }, `  ${humanize(p.type)}`)), detail) };
  });
  const m = modal({ title, wide: true,
    body: [domain ? field(domainLabel, domain, 'The domain they use to sign in. Ask them for it.') : null,
      h('div', { class: 'form-grid' }, field('Commission', type), field('Amount or percent', value, 'Paid to the reseller for each night booked, after the guest checks out.')),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Properties they may sell'), h('div', { class: 'stack-sm' }, rows.map((r) => r.el))),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'When you pay the commission'), h('div', { class: 'form-grid' }, field('Payment schedule', mode, 'You pay the reseller yourself. Late statements are flagged. Changes apply to new statements only.'), dayField)),
      field('Note (optional)', note)],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Save', { kind: 'primary', onClick: async () => {
      const chosen = rows.filter((r) => r.on.checked).map((r) => ({ property_id: r.p.id, ...(r.own.checked ? { commission_type: r.ot.value, commission_value: r.ov.value === '' ? null : Number(r.ov.value) } : {}) }));
      if (!chosen.length) throw new Error('Choose at least one property.');
      if (value.value === '') throw new Error('Enter the commission.');
      if (mode.value === 'MONTHLY' && (Number(day.value) < 1 || Number(day.value) > 28)) throw new Error('For a monthly schedule choose a day from 1 to 28.');
      await onSave({ commission_type: type.value, commission_value: Number(value.value), properties: chosen, note: note.value.trim() || null, settlement_mode: mode.value, settlement_day: Number(day.value) || null }, domain?.value.trim().toLowerCase());
      m.close();
    } })] });
}


function confirmCancelModal(c, reload) {
  const amount = inp({ type: 'number', min: 0, max: Number(c.paid_amount), step: '0.01', value: c.suggested_refund });
  const note = area({ rows: 2, maxlength: 500 });
  const m = modal({ title: `Cancel ${c.booking_ref}`, body: [
    h('p', {}, `The room is released at once and can be sold again. Pay the refund to the guest yourself (the guest paid ${money(c.paid_amount, c.currency)}).`),
    field('Refund to the guest', amount, `Suggested by your rules: ${money(c.suggested_refund, c.currency)}`), field('Note for the reseller (optional)', note)],
  actions: [btn('Back', { onClick: () => m.close() }), btn('Cancel the booking', { kind: 'danger', onClick: async () => {
    await post(`/channel/cancellations/${c.id}/confirm`, { refund_amount: amount.value === '' ? null : Number(amount.value), note: note.value.trim() || null });
    toast('Booking cancelled.', 'ok'); m.close(); await reload();
  } })] });
}

function declineCancelModal(c, reload) {
  const note = area({ rows: 3, maxlength: 500, placeholder: 'Tell the reseller why the booking stays' });
  const m = modal({ title: 'Keep the booking', body: [field('Reason', note)],
    actions: [btn('Back', { onClick: () => m.close() }), btn('Send', { kind: 'primary', onClick: async () => {
      if (note.value.trim().length < 3) throw new Error('Please write a few words for the reseller.');
      await post(`/channel/cancellations/${c.id}/decline`, { note: note.value.trim() });
      toast('The reseller has been told.', 'ok'); m.close(); await reload();
    } })] });
}

function policyModal(policy, reload) {
  const rows = [];
  const box = h('div', { class: 'stack-sm' });
  const add = (r = { days_before: '', refund_percent: '' }) => {
    const d = inp({ type: 'number', min: 0, max: 365, step: 1, value: r.days_before, 'aria-label': 'Days before check-in' });
    const p = inp({ type: 'number', min: 0, max: 100, step: 1, value: r.refund_percent, 'aria-label': 'Percent refunded' });
    const row = { d, p, el: h('div', { class: 'row' }, h('span', {}, 'If cancelled at least'), d, h('span', {}, 'days before check-in, refund'), p, h('span', {}, '%'),
      btn('Remove', { kind: 'sm', onClick: () => { rows.splice(rows.indexOf(row), 1); row.el.remove(); } })) };
    rows.push(row); box.append(row.el);
  };
  policy.rules.forEach(add);
  const m = modal({ title: 'Cancellation and refund rules', wide: true, body: [
    h('p', { class: 'muted' }, 'The refund is a percent of what the guest paid. Cancelling closer to check-in than your last rule means no refund.'), box,
    btn('Add a rule', { kind: 'sm', onClick: () => add() })],
  actions: [btn('Cancel', { onClick: () => m.close() }), btn('Save rules', { kind: 'primary', onClick: async () => {
    const list = rows.map((r) => ({ days_before: Number(r.d.value), refund_percent: Number(r.p.value) }));
    if (!list.length || rows.some((r) => r.d.value === '' || r.p.value === '')) throw new Error('Fill in the days and the percent for every rule.');
    await put('/channel/cancellation-policy', { rules: list });
    toast('Rules saved. They apply to new requests.', 'ok'); m.close(); await reload();
  } })] });
}

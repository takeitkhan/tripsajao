import { get, post, patch } from '../api.js';
import { invalidate } from '../data.js';
import { h, btn, field, inp, sel, check, modal, table, badge, pageHead, figures, money, fmtDate, fmtDateTime, humanize, toast, copyBtn } from '../ui.js';
import { withDocs } from '../docs.js';

const commissionText = (p) => (p.commission_type === 'PERCENT' ? `${Number(p.commission_value)}% of each booking` : `${Number(p.commission_value).toFixed(2)} flat per booking`);

function openPartnerModal(p, onSaved) {
  const name = inp({ value: p?.name || '', maxlength: 200 });
  const email = inp({ type: 'email', value: p?.email || '', disabled: !!p });
  const pass = inp({ type: 'password', minlength: 10, autocomplete: 'new-password' });
  const type = sel([['B2B', 'Sales partner (B2B)'], ['MOU', 'MoU partner']], p?.partner_type || 'B2B', { disabled: !!p });
  const ctype = sel([['PERCENT', 'Percent of booking total'], ['FLAT', 'Fixed amount per booking']], p?.commission_type || 'PERCENT');
  const cval = inp({ type: 'number', min: 0, step: '0.01', value: p?.commission_value ?? 10 });
  const code = inp({ value: p?.vanity_code || '', maxlength: 32, placeholder: 'Leave blank for a random code' });
  const active = p ? check('Partner can sign in and earn commission', p.is_active) : null;
  const m = modal({
    title: p ? `Edit ${p.name}` : 'New partner',
    body: [
      h('div', { class: 'form-grid' }, field('Name', name), field('Email', email, p ? 'Email cannot change.' : null), p ? null : field('Temporary password', pass, 'At least 10 characters. Share it with the partner.'),
        field('Partner type', type), field('Commission', ctype), field('Commission value', cval, 'Applies to future bookings only.'), field('Short link code', code, 'Letters, numbers, - and _ (4 to 32). Visitors never see the partner name.')),
      active,
    ],
    actions: [
      btn('Cancel', { onClick: () => m.close() }),
      btn(p ? 'Save changes' : 'Create partner', { kind: 'primary', onClick: async () => {
        if (p) await patch(`/partners/${p.id}`, { name: name.value.trim(), commission_type: ctype.value, commission_value: Number(cval.value).toFixed(2), vanity_code: code.value.trim() || undefined, is_active: active.querySelector('input').checked });
        else await post('/partners', { name: name.value.trim(), email: email.value.trim(), password: pass.value, partner_type: type.value, commission_type: ctype.value, commission_value: Number(cval.value).toFixed(2), ...(code.value.trim() ? { vanity_code: code.value.trim() } : {}) });
        invalidate(); toast(p ? 'Partner saved' : 'Partner created', 'ok'); m.close(); onSaved?.();
      } }),
    ],
  });
}

async function openLedger(p) {
  const m = modal({ title: `${p.name} - ledger`, wide: true, body: h('div', { class: 'spinner' }) });
  try {
    const s = await get(`/partners/${p.id}/ledger`, { limit: 200 });
    m.setBody([
      figures([
        { value: money(s.total_credit), label: 'Commission earned' }, { value: money(s.total_debit), label: 'Paid out or reversed' },
        { value: money(s.closing_balance), label: 'Balance' }, { value: money(s.available_for_payout), label: 'Available for payout' }]),
      table([
        { label: 'Date', render: (e) => fmtDateTime(e.created_at) },
        { label: 'Type', render: (e) => humanize(e.transaction_type) },
        { label: 'Note', render: (e) => e.note || '-' },
        { label: 'Credit', class: 'num', render: (e) => (Number(e.credit) ? money(e.credit) : '') },
        { label: 'Debit', class: 'num', render: (e) => (Number(e.debit) ? money(e.debit) : '') },
        { label: 'Balance', class: 'num', render: (e) => money(e.balance) },
      ], s.entries, { empty: 'No ledger entries yet. Commission appears when a booking from this partner is paid.' }),
    ]);
  } catch (e) { m.close(); throw e; }
}

export function render() {
  return h('div', {}, pageHead('Partners', 'Sales and MoU partners, their short links and what you owe them.'), withDocs('partners', manage));
}

async function manage() {
  const root = h('div');
  const holder = h('div');
  async function load() {
    const page = await get('/partners', { limit: 200 });
    holder.replaceChildren(table([
      { label: 'Partner', render: (p) => h('div', {}, h('b', {}, p.name), h('div', { class: 'muted' }, p.email)) },
      { label: 'Type', render: (p) => (p.partner_type === 'MOU' ? 'MoU' : 'Sales (B2B)') },
      { label: 'Commission', render: (p) => commissionText(p) },
      { label: 'Short link', render: (p) => h('div', { class: 'row' }, h('code', {}, `/go/${p.vanity_code}`), copyBtn(p.short_link, 'Copy link')) },
      { label: 'Status', render: (p) => badge(p.is_active ? 'PUBLISHED' : 'DRAFT', p.is_active ? 'Active' : 'Disabled') },
      { label: '', render: (p) => h('div', { class: 'actions' }, btn('Ledger', { kind: 'sm', onClick: () => openLedger(p) }), btn('Edit', { kind: 'sm', onClick: () => openPartnerModal(p, load) })) },
    ], page.items, { empty: 'No partners yet. Add one and share their short link. Bookings that follow the link are credited to them automatically.' }));
  }
  root.append(
    h('div', { class: 'callout', style: { marginBottom: '18px' } }, 'A short link sets a private tracking cookie, then sends the visitor to a clean page with no tracking code in the address. The booking they make later is credited to the partner automatically.'),
    h('div', { class: 'toolbar' }, h('div', { style: { marginLeft: 'auto' } }, btn('New partner', { kind: 'primary', icon: 'plus', onClick: () => openPartnerModal(null, load) }))), holder);
  await load();
  return root;
}

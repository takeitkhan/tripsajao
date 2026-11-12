// The business profile: who the business is, licence and tax numbers, where money is paid, and the rules for holding seats.
import { get, put } from '../api.js';
import { mediaField } from '../media.js';
import { h, raw, btn, field, fieldBox, inp, area, sel, check, pageHead, toast, confirmDialog } from '../ui.js';
import { withDocs } from '../docs.js';

const TYPES = ['', 'Travel agency', 'Tour operator', 'Resort', 'Hotel', 'Houseboat', 'Other'];
const PROVIDERS = ['bKash', 'Nagad', 'Rocket', 'Upay', 'Other'];
const section = (title, hint, ...kids) => h('section', { class: 'card stack', style: { padding: '18px' } }, h('div', {}, h('h3', { style: { margin: 0 } }, title), hint ? h('div', { class: 'muted' }, hint) : null), ...kids);
const req = (text) => h('span', {}, text, ' ', h('b', { class: 'req', style: { color: 'var(--bad)', fontWeight: 600, fontSize: '12px' } }, '(Required)'));

/** A list of accounts the owner can add to and remove from. `make(item)` returns { el, get() }. */
function listEditor(items, make, addLabel, blank) {
  const rows = []; const box = h('div', { class: 'stack' });
  const add = (item) => {
    const r = make(item); const wrap = h('div', { class: 'card', style: { padding: '12px', background: 'var(--paper-2, transparent)' } }, r.el,
      h('div', { style: { marginTop: '8px' } }, btn('Remove', { kind: 'sm ghost danger', icon: 'trash-2', onClick: () => { rows.splice(rows.indexOf(entry), 1); wrap.remove(); } })));
    const entry = { r, wrap }; rows.push(entry); box.append(wrap);
  };
  items.forEach(add);
  return { el: h('div', { class: 'stack' }, box, h('div', {}, btn(addLabel, { kind: 'sm', icon: 'plus', onClick: () => add(blank) }))), get: () => rows.map((x) => x.r.get()) };
}

function bankRow(a = {}) {
  const f = { bank: inp({ value: a.bank_name || '', maxlength: 120, placeholder: 'For example: City Bank' }), branch: inp({ value: a.branch || '', maxlength: 120 }),
    name: inp({ value: a.account_name || '', maxlength: 160 }), no: inp({ value: a.account_number || '', maxlength: 40 }), routing: inp({ value: a.routing_no || '', maxlength: 20 }),
    swift: inp({ value: a.swift || '', maxlength: 20 }), main: check('Main account', !!a.is_primary), show: check('Show to customers who pay by hand', a.show_to_customers !== false) };
  return { el: h('div', { class: 'stack' }, h('div', { class: 'form-grid' }, field('Bank', f.bank), field('Branch', f.branch), field('Account name', f.name), field('Account number', f.no), field('Routing number', f.routing), field('SWIFT code', f.swift)), h('div', { class: 'row' }, f.main, f.show)),
    get: () => ({ bank_name: f.bank.value.trim(), branch: f.branch.value.trim() || null, account_name: f.name.value.trim(), account_number: f.no.value.trim(), routing_no: f.routing.value.trim() || null, swift: f.swift.value.trim() || null,
      is_primary: f.main.querySelector('input').checked, show_to_customers: f.show.querySelector('input').checked }) };
}

function mfsRow(a = {}) {
  const f = { provider: sel(PROVIDERS, a.provider || 'bKash'), type: sel(['Personal', 'Agent', 'Merchant'], a.account_type || 'Personal'), no: inp({ value: a.number || '', maxlength: 20, placeholder: '01XXXXXXXXX' }),
    name: inp({ value: a.account_name || '', maxlength: 160 }), main: check('Main account', !!a.is_primary), show: check('Show to customers who pay by hand', a.show_to_customers !== false) };
  return { el: h('div', { class: 'stack' }, h('div', { class: 'form-grid' }, field('Service', f.provider), field('Account type', f.type), field('Number', f.no), field('Account name', f.name)), h('div', { class: 'row' }, f.main, f.show)),
    get: () => ({ provider: f.provider.value, account_type: f.type.value, number: f.no.value.trim(), account_name: f.name.value.trim() || null, is_primary: f.main.querySelector('input').checked, show_to_customers: f.show.querySelector('input').checked }) };
}

async function manage(canWrite) {
  const b = await get('/business');
  const dis = { disabled: !canWrite };
  const f = {
    name: inp({ value: b.name || '', maxlength: 200, ...dis }), legal: inp({ value: b.legal_name || '', maxlength: 200, ...dis }), type: sel(TYPES.map((x) => [x, x || 'Choose']), b.business_type || '', dis),
    year: inp({ type: 'number', min: 1900, max: 2100, value: b.established_year || '', ...dis }),
    logo: mediaField({ kind: 'image', value: b.logo_url || '' }), photo: mediaField({ kind: 'image', value: b.owner_photo || '' }),
    owner: inp({ value: b.owner_name || '', maxlength: 200, ...dis }), ownerPhone: inp({ value: b.owner_phone || '', maxlength: 40, ...dis }), ownerEmail: inp({ type: 'email', value: b.owner_email || '', maxlength: 320, ...dis }),
    license: inp({ value: b.license_no || '', maxlength: 60, ...dis }), expiry: inp({ type: 'date', value: b.license_expiry || '', ...dis }),
    tin: inp({ value: b.tin || '', maxlength: 40, ...dis }), bin: inp({ value: b.bin || '', maxlength: 40, ...dis }), other: inp({ value: b.other_registration || '', maxlength: 120, ...dis }),
    whatsapp: inp({ value: b.whatsapp || '', maxlength: 40, ...dis }), website: inp({ value: b.website || '', maxlength: 300, placeholder: 'https://', ...dis }), hours: inp({ value: b.office_hours || '', maxlength: 200, placeholder: 'For example: Sat-Thu 10am-7pm', ...dis }),
    hold: inp({ type: 'number', min: 1, max: 120, value: b.hold_minutes, ...dis }), evhold: inp({ type: 'number', min: 1, max: 120, value: b.event_hold_minutes, ...dis }), dep: inp({ type: 'number', min: 1, max: 100, value: b.deposit_percent, ...dis }),
    terms: area({ rows: 4, maxlength: 4000, value: b.terms || '', ...dis }), cancel: area({ rows: 4, maxlength: 4000, value: b.cancellation_policy || '', ...dis }),
  };
  const banks = listEditor(b.bank_accounts, bankRow, 'Add a bank account', {});
  const mfs = listEditor(b.mfs_accounts, mfsRow, 'Add a mobile banking account', {});
  const status = h('div', {});
  const paint = () => { status.replaceChildren(...(b.missing.length ? [h('div', { class: 'callout warn' }, `To complete your profile, add: ${b.missing.join(', ')}.`)] : [])); };
  paint();
  const logoBox = fieldBox(req('Business logo'), f.logo.el, 'Shown in the top bar, on quotations and on your website.');
  const photoBox = fieldBox(req("Owner's photo"), f.photo.el, 'A clear photo of the company owner.');
  const save = async () => {
    const lacking = [!f.logo.get() && 'Business logo', !f.photo.get() && "Owner's photo", !f.name.value.trim() && 'Business name'].filter(Boolean);
    if (lacking.length) throw new Error(`Please add: ${lacking.join(', ')}.`);
    const v = (el) => el.value.trim() || null;
    const body = { name: f.name.value.trim(), legal_name: v(f.legal), business_type: f.type.value || null, established_year: f.year.value ? Number(f.year.value) : null, logo_url: f.logo.get(), owner_name: v(f.owner), owner_photo: f.photo.get(),
      owner_phone: v(f.ownerPhone), owner_email: v(f.ownerEmail), license_no: v(f.license), license_expiry: f.expiry.value || null, tin: v(f.tin), bin: v(f.bin), other_registration: v(f.other),
      whatsapp: v(f.whatsapp), website: v(f.website), office_hours: v(f.hours), bank_accounts: banks.get(), mfs_accounts: mfs.get(),
      hold_minutes: Number(f.hold.value || 10), event_hold_minutes: Number(f.evhold.value || 10), deposit_percent: Number(f.dep.value || 50), terms: v(f.terms), cancellation_policy: v(f.cancel) };
    const r = await put('/business', body);
    b.missing = r.missing; paint(); toast('Business profile saved', 'ok');
    document.dispatchEvent(new CustomEvent('kt:company', { detail: { name: r.name, logo: r.logo_url } }));
  };
  return h('div', { class: 'stack', style: { maxWidth: '860px' } }, status,
    section('Business', 'The name here is shown in the top bar and on your website.',
      h('div', { class: 'form-grid' }, field('Business name', f.name), field('Registered name', f.legal), field('Kind of business', f.type), field('Year started', f.year)), logoBox),
    section('Owner', null, photoBox, h('div', { class: 'form-grid' }, field('Owner name', f.owner), field('Owner phone', f.ownerPhone), field('Owner email', f.ownerEmail))),
    section('Licence and tax', 'TIN and BIN are optional.',
      h('div', { class: 'form-grid' }, field('Licence number', f.license), field('Licence valid until', f.expiry), field('TIN', f.tin), field('BIN', f.bin), field('Other registration', f.other))),
    section('Contact', null, h('div', { class: 'form-grid' }, field('WhatsApp', f.whatsapp), field('Website', f.website), field('Office hours', f.hours))),
    section('Bank accounts', 'Accounts marked "Show to customers" can be shown on your website for customers who pay by hand.', banks.el),
    section('Mobile banking (bKash, Nagad ...)', null, mfs.el),
    section('Booking rules', 'Used when customers book through your website.',
      h('div', { class: 'form-grid' }, field('Room hold (minutes)', f.hold, 'How long a room is kept while the customer pays.'), field('Event seat hold (minutes)', f.evhold, 'How long event seats are kept.'), field('Minimum advance (%)', f.dep, 'For part payments.'))),
    section('Terms', null, field('Booking terms', f.terms), field('Cancellation policy', f.cancel)),
    canWrite ? h('div', {}, btn('Save business profile', { kind: 'primary', onClick: save })) : h('div', { class: 'callout' }, 'Only an admin can change the business profile.'));
}

export function render(ctx) {
  return h('div', {}, pageHead('Business profile', 'Licence, owner, tax numbers, payment accounts and booking rules.'), withDocs('business', () => manage(ctx.can('business:manage'))));
}

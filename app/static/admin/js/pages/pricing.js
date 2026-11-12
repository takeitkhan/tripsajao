import { get, put, post } from '../api.js';
import { invalidate } from '../data.js';
import {
  h, btn, field, inp, sel, check, modal, table, emptyState, pageHead, money, fmtDate, today, addDays, toast, icon, humanize, reportError,
} from '../ui.js';
import { withDocs } from '../docs.js';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const KINDS = [['SURCHARGE_PERCENT', 'Add percent'], ['SURCHARGE_FLAT', 'Add fixed amount'], ['OVERRIDE', 'Replace price']];

function ruleRow(r = {}) {
  const name = inp({ value: r.name || '', placeholder: 'Name, e.g. Eid week', maxlength: 80, 'aria-label': 'Rule name' });
  const cat = sel([['SEASON', 'Season'], ['HOLIDAY', 'Holiday']], r.category || 'SEASON', { 'aria-label': 'Category' });
  const start = inp({ type: 'date', value: r.start_date || '', 'aria-label': 'From' });
  const end = inp({ type: 'date', value: r.end_date || '', 'aria-label': 'To (inclusive)' });
  const kind = sel(KINDS, r.kind || 'SURCHARGE_PERCENT', { 'aria-label': 'Adjustment' });
  const value = inp({ type: 'number', min: 0, step: '0.01', value: r.value ?? '', placeholder: 'Value', 'aria-label': 'Value' });
  const applies = sel([['ALL', 'Every night'], ['WEEKDAY', 'Weekdays only'], ['WEEKEND', 'Weekends only']], r.applies_to || 'ALL', { 'aria-label': 'Applies to' });
  const prio = inp({ type: 'number', value: r.priority ?? 0, 'aria-label': 'Priority' });
  const row = h('div', { class: 'rule-row' },
    h('div', { class: 'wide' }, field('Name', name)), field('Type', cat), field('From', start), field('To (included)', end),
    h('div', { style: { alignSelf: 'end' } }, h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Remove rule', onclick: () => row.remove() }, icon('trash-2'))),
    h('div', { class: 'wide' }, field('Adjustment', kind)), field('Value', value), field('Nights', applies), field('Priority', prio, 'Replace price only'));
  row.get = () => {
    if (!name.value.trim() && !start.value) return null;
    if (!name.value.trim() || !start.value || !end.value || value.value === '') throw new Error('Each seasonal rule needs a name, both dates and a value.');
    return { name: name.value.trim(), category: cat.value, start_date: start.value, end_date: end.value, kind: kind.value, value: String(value.value), applies_to: applies.value, priority: Number(prio.value || 0) };
  };
  return row;
}

/** Edit weekday / weekend / seasonal pricing for one unit (optionally copy to its siblings). */
export async function openPricingEditor(unit, siblings, onSaved) {
  const cur = await get(`/pricing/units/${unit.id}`).catch(() => null);
  const seasonal = cur?.seasonal || {};
  const wd = inp({ type: 'number', min: 0, step: '0.01', value: cur?.weekday_price ?? '' });
  const we = inp({ type: 'number', min: 0, step: '0.01', value: cur?.weekend_price ?? '' });
  const cc = inp({ value: cur?.currency || 'USD', maxlength: 3 });
  const days = (seasonal.weekend_days ?? [4, 5]);
  const dayBoxes = DAYS.map((d, i) => check(d, days.includes(i), { 'data-day': i }));
  const rules = h('div');
  (seasonal.rules || []).forEach((r) => rules.append(ruleRow(r)));
  const all = siblings && siblings.length > 1 ? check(`Apply to all ${siblings.length} units in this property`, false) : null;
  const m = modal({
    title: `Pricing for ${unit.unit_name}`, wide: true,
    body: [
      h('div', { class: 'form-grid' }, field('Weekday price per night', wd), field('Weekend price per night', we), field('Currency', cc, 'Three letters, e.g. USD, BDT, INR')),
      h('div', {}, h('div', { class: 'field-label', style: { marginBottom: '6px' } }, 'Nights priced at the weekend rate'), h('div', { class: 'days' }, dayBoxes),
        h('p', { class: 'hint', style: { marginTop: '6px' } }, 'A night counts by the day the guest sleeps over. Friday and Saturday nights are the default.')),
      h('div', {}, h('h3', { style: { marginBottom: '4px' } }, 'Seasonal and holiday pricing'),
        h('p', { class: 'hint' }, 'Percent and fixed surcharges stack. If several "Replace price" rules cover a night, the highest priority wins. End date is included.'), rules,
        btn('Add rule', { kind: 'sm', icon: 'plus', onClick: () => { rules.append(ruleRow()); } })),
      all,
    ],
    actions: [
      btn('Cancel', { onClick: () => m.close() }),
      btn('Save pricing', { kind: 'primary', onClick: async () => {
        if (wd.value === '' || we.value === '') throw new Error('Enter both the weekday and weekend price.');
        const body = {
          weekday_price: Number(wd.value).toFixed(2), weekend_price: Number(we.value).toFixed(2), currency: cc.value.trim().toUpperCase(),
          seasonal: { weekend_days: dayBoxes.map((b, i) => (b.querySelector('input').checked ? i : -1)).filter((i) => i >= 0), rules: [...rules.children].map((r) => r.get()).filter(Boolean) },
        };
        const targets = all?.querySelector('input').checked ? siblings : [unit];
        for (const u of targets) await put(`/pricing/units/${u.id}`, body);
        toast(targets.length > 1 ? `Pricing saved for ${targets.length} units` : 'Pricing saved', 'ok'); m.close(); onSaved?.();
      } }),
    ],
  });
}

export function render() {
  return h('div', {}, pageHead('Pricing', 'Weekday, weekend, seasonal and holiday rates for every unit.'), withDocs('pricing', manage));
}

async function manage() {
  const props = (await get('/properties', { limit: 200 })).items.filter((p) => p.is_active);
  if (!props.length) return emptyState('Add a property and its units first, then set their prices here.', h('a', { class: 'btn primary', href: '#/properties' }, 'Add a property'));
  const prop = sel(props.map((p) => [p.id, p.name]), props[0].id);
  const holder = h('div');
  const quoteBox = h('div');
  let units = [];

  async function load() {
    units = (await get(`/properties/${prop.value}/units`, { limit: 200 })).items;
    const prices = await Promise.all(units.map((u) => get(`/pricing/units/${u.id}`).catch(() => null)));
    const rows = units.map((u, i) => ({ u, p: prices[i] }));
    holder.replaceChildren(table([
      { label: 'Unit', render: ({ u }) => h('b', {}, u.unit_name) },
      { label: 'Weekday', class: 'num', render: ({ p }) => (p ? money(p.weekday_price, p.currency) : h('span', { class: 'muted' }, 'Not set')) },
      { label: 'Weekend', class: 'num', render: ({ p }) => (p ? money(p.weekend_price, p.currency) : '-') },
      { label: 'Seasonal rules', class: 'num', render: ({ p }) => p?.seasonal?.rules?.length || 0 },
      { label: '', render: ({ u }) => h('div', { class: 'actions' }, btn('Edit pricing', { kind: 'sm', onClick: () => openPricingEditor(u, units, load) })) },
    ], rows, { empty: 'This property has no units yet.' }));
    buildQuote();
  }

  function buildQuote() {
    if (!units.length) { quoteBox.replaceChildren(); return; }
    const unit = sel(units.map((u) => [u.id, u.unit_name]), units[0].id);
    const ci = inp({ type: 'date', value: today() });
    const co = inp({ type: 'date', value: addDays(today(), 3) });
    const out = h('div');
    quoteBox.replaceChildren(
      h('div', { class: 'section' }, h('h2', {}, 'Price a stay')),
      h('p', { class: 'muted' }, 'Check what a guest would pay, night by night, before you publish a rate.'),
      h('div', { class: 'toolbar' }, field('Unit', unit), field('Check-in', ci), field('Check-out', co),
        btn('Get price', { kind: 'primary', onClick: async () => {
          const q = await post('/pricing/quote', { unit_id: unit.value, check_in: ci.value, check_out: co.value });
          out.replaceChildren(table([
            { label: 'Night', render: (n) => fmtDate(n.night) },
            { label: 'Rate', render: (n) => humanize(n.day_type) },
            { label: 'Base', class: 'num', render: (n) => money(n.base_price, q.currency) },
            { label: 'Adjustments', render: (n) => (n.applied_rules.length ? n.applied_rules.join(', ') : '-') },
            { label: 'Price', class: 'num', render: (n) => money(n.price, q.currency) },
          ], q.nights), h('p', { style: { textAlign: 'right', marginTop: '10px', fontSize: '18px' } }, 'Total ', h('b', {}, money(q.total, q.currency))));
        } })),
      out);
  }

  prop.addEventListener('change', () => load().catch(reportError));
  const root = h('div', {}, h('div', { class: 'toolbar' }, field('Property', prop)), holder, quoteBox);
  await load();
  return root;
}

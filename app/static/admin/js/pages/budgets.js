// Event budget calculator: build a cost estimate from vendor rates, add your margin, save it, and print a quotation for the customer.
import { get, post, patch, del } from '../api.js';
import { perms } from '../data.js';
import { h, raw, btn, field, inp, area, sel, modal, table, badge, pageHead, confirmDialog, money, fmtDate, toast, reportError, debounce, humanize } from '../ui.js';
import { t } from '../i18n.js';
import { withDocs } from '../docs.js';
import { KINDS, kindName, unitName } from './vendors.js';

const STATUS = [['DRAFT', 'Draft'], ['SENT', 'Sent to customer'], ['WON', 'Accepted'], ['LOST', 'Not accepted']];
const BADGE = { DRAFT: 'DRAFT', SENT: 'PENDING', WON: 'CONFIRMED', LOST: 'CANCELLED' };
const statusName = (s) => (STATUS.find((x) => x[0] === s) || [0, humanize(s)])[1];
const cents = (x) => Math.round((Number(x) + Number.EPSILON) * 100) / 100;

/** Same arithmetic as the server (the server's answer is what gets saved). */
export function work(lines, people, margin) {
  const rows = lines.map((l) => ({ ...l, total: cents((Number(l.qty) || 0) * (Number(l.unit_price) || 0) * (l.per_person ? people : 1)) }));
  const cost = cents(rows.reduce((s, r) => s + r.total, 0));
  const extra = cents(cost * (Number(margin) || 0) / 100); const sell = cents(cost + extra);
  return { rows, cost, extra, sell, perPerson: cents(sell / Math.max(people, 1)), costPerPerson: cents(cost / Math.max(people, 1)) };
}

// ---------- quotation (printed on the agency's own paper details; costs and margin are never shown)
function quoteNode(b, calc, co) {
  const lineText = (l) => `${l.label}${Number(l.qty) !== 1 || l.unit ? ` (${[Number(l.qty) !== 1 ? `x ${l.qty}` : '', l.unit ? t(l.unit) : ''].filter(Boolean).join(' ')})` : ''}`;
  return h('div', { class: 'quote' },
    h('div', { class: 'quote-head' },
      co.logo_url ? h('img', { src: co.logo_url, alt: '', class: 'quote-logo' }) : null,
      h('div', {}, h('div', { class: 'quote-co' }, raw(co.name || '')), co.tagline ? h('div', { class: 'muted' }, raw(co.tagline)) : null,
        h('div', { class: 'quote-addr' }, raw([co.address, co.phone, co.email].filter(Boolean).join('\n'))))),
    h('h2', { class: 'quote-title' }, 'Quotation'),
    h('div', { class: 'quote-meta' },
      h('div', {}, h('div', { class: 'muted' }, 'For'), h('b', {}, raw(b.client_name || '-')), b.client_phone ? h('div', {}, raw(b.client_phone)) : null),
      h('div', {}, h('div', { class: 'muted' }, 'Date'), h('b', {}, fmtDate(new Date().toISOString().slice(0, 10)))),
      h('div', {}, h('div', { class: 'muted' }, 'People'), h('b', {}, b.people))),
    h('h3', { class: 'quote-trip' }, raw(b.title)),
    h('div', { class: 'muted' }, 'What is included'),
    h('ul', { class: 'quote-list' }, b.lines.filter((l) => l.label.trim()).map((l) => h('li', {}, raw(lineText(l))))),
    h('div', { class: 'quote-price' },
      h('div', {}, h('div', { class: 'muted' }, 'Price per person'), h('b', { class: 'quote-big' }, money(calc.perPerson, b.currency))),
      h('div', {}, h('div', { class: 'muted' }, 'Total price'), h('b', { class: 'quote-big' }, money(calc.sell, b.currency)))),
    b.notes ? h('p', { class: 'quote-notes' }, raw(b.notes)) : null);
}

/** Prints through the browser's print dialog (choose "Save as PDF" there). Only the quotation is shown on paper. */
function printNode(node) {
  const root = h('div', { id: 'quote-root' }, node.cloneNode(true));
  document.body.append(root); document.body.classList.add('quote-print');
  const clean = () => { document.body.classList.remove('quote-print'); root.remove(); window.removeEventListener('afterprint', clean); };
  window.addEventListener('afterprint', clean);
  try { window.print(); } finally { setTimeout(clean, 1500); }
}

async function openQuote(b, calc) {
  let co = {};
  try { co = await get('/budgets/company'); } catch { /* the quotation can still be printed without company details */ }
  const node = quoteNode(b, calc, co);
  const m = modal({ title: 'Quotation', wide: true, body: [
    (!co.logo_url || !co.address) ? h('div', { class: 'callout', style: { marginBottom: '12px' } }, 'Add your logo and address under Website content > Company, and they will appear at the top of this quotation.') : null,
    h('div', { class: 'quote-preview' }, node)],
  actions: [btn('Close', { onClick: () => m.close() }), btn('Print or save as PDF', { kind: 'primary', icon: 'printer', onClick: () => printNode(node) })] });
}

// ---------- picking rates from the vendor list
function pickRates(currency, onAdd) {
  const q = inp({ type: 'search', placeholder: 'Search a rate or vendor', 'aria-label': 'Search rates' }); const place = sel([['', 'All places']], ''); const kind = sel([['', 'All kinds'], ...KINDS], '');
  const list = h('div');
  async function load() {
    list.replaceChildren(h('div', { class: 'spinner' }));
    const page = await get('/rates', { q: q.value.trim() || undefined, location: place.value || undefined, category: kind.value || undefined, limit: 100 });
    list.replaceChildren(table([
      { label: 'Rate', render: (r) => h('div', {}, h('b', {}, raw(r.item)), h('div', { class: 'muted' }, raw(`${r.vendor_name} - ${kindName(r.category)} - ${r.location}`))) },
      { label: 'Price', class: 'num', render: (r) => `${money(r.price, r.currency)} ${unitName(r.unit)}` },
      { label: '', render: (r) => btn('Add', { kind: 'sm', icon: 'plus', onClick: () => {
        if (r.currency !== currency()) { toast(`This rate is in ${r.currency} but the budget is in ${currency()}.`, 'error'); return; }
        onAdd({ label: `${r.vendor_name} - ${r.item}`, vendor_id: r.vendor_id, vendor_name: r.vendor_name, unit: unitName(r.unit), qty: 1, unit_price: r.price, per_person: r.unit === 'PER_PERSON' });
        toast('Added to the budget', 'ok');
      } }) },
    ], page.items, { empty: 'No rates match. Add vendors and their rates first, or add a line by hand.' }));
  }
  get('/vendors/locations').then((ps) => place.append(...ps.map((p) => h('option', { value: p }, raw(p))))).catch(() => {});
  const again = () => load().catch(reportError);
  q.addEventListener('input', debounce(again, 300)); [place, kind].forEach((s) => s.addEventListener('change', again));
  const m = modal({ title: 'Add from your vendor rates', wide: true, body: [h('div', { class: 'toolbar' }, h('div', { class: 'field', style: { minWidth: '220px' } }, h('span', { class: 'field-label' }, 'Search'), q), field('Place', place), field('Kind', kind)), list],
    actions: [btn('Done', { kind: 'primary', onClick: () => m.close() })] });
  again();
}

// ---------- the builder
export async function renderBuilder(ctx) {
  const id = ctx.params.id; const isNew = id === 'new'; const canWrite = perms.can('budgets:write');
  const [pk, ev] = await Promise.all([get('/packages', { limit: 200 }).catch(() => ({ items: [] })), get('/events', { limit: 200 }).catch(() => ({ items: [] }))]);
  const saved = isNew ? null : await get(`/budgets/${id}`);
  const b = saved ? { ...saved, margin: saved.margin_percent, lines: saved.lines.map((l) => ({ ...l })) }
    : { title: '', client_name: '', client_phone: '', people: 2, currency: 'BDT', margin: 15, notes: '', status: 'DRAFT', package_id: null, event_id: null, lines: [] };
  const f = {
    title: inp({ value: b.title, maxlength: 300, placeholder: 'For example: Sajek for the Rahman family', disabled: !canWrite }), client: inp({ value: b.client_name || '', maxlength: 200, disabled: !canWrite }),
    phone: inp({ value: b.client_phone || '', maxlength: 60, disabled: !canWrite }), people: inp({ type: 'number', min: 1, value: b.people, disabled: !canWrite }),
    cur: inp({ value: b.currency, maxlength: 3, disabled: !canWrite }), margin: inp({ type: 'number', min: 0, max: 500, step: '0.5', value: b.margin, disabled: !canWrite }),
    status: sel(STATUS, b.status, { disabled: !canWrite }), notes: area({ value: b.notes || '', rows: 3, placeholder: 'Shown on the quotation, such as payment terms', disabled: !canWrite }),
    trip: (() => {
      const o = (v, label) => h('option', { value: v }, label);
      const el = h('select', { class: 'input', disabled: !canWrite }, o('', 'Not linked'),
        ...ev.items.map((e) => o(`e:${e.id}`, raw(`${t('Event')}: ${e.title} (${fmtDate(e.starts_on)})`))), ...pk.items.map((p) => o(`p:${p.id}`, raw(`${t('Package')}: ${p.title}`))));
      el.value = b.event_id ? `e:${b.event_id}` : b.package_id ? `p:${b.package_id}` : '';
      return el;
    })(),
  };
  const body = h('div'); const totals = h('div', { class: 'panel' });
  const people = () => Math.max(1, Math.floor(Number(f.people.value) || 1));
  const state = () => ({ ...b, title: f.title.value.trim(), client_name: f.client.value.trim(), client_phone: f.phone.value.trim(), people: people(), currency: (f.cur.value || 'BDT').toUpperCase(), margin: f.margin.value, notes: f.notes.value.trim(), status: f.status.value });

  function recalc() {
    const s = state(); const c = work(b.lines, s.people, s.margin);
    b.lines.forEach((_, i) => { const cell = body.querySelector(`[data-total="${i}"]`); if (cell) cell.textContent = money(c.rows[i].total, s.currency); });
    totals.replaceChildren(
      h('div', { class: 'kv' }, h('span', {}, 'Your cost'), h('b', {}, money(c.cost, s.currency))),
      h('div', { class: 'kv' }, h('span', {}, `Margin (${Number(s.margin) || 0}%)`), h('b', {}, money(c.extra, s.currency))),
      h('div', { class: 'kv big' }, h('span', {}, 'Selling price'), h('b', {}, money(c.sell, s.currency))),
      h('div', { class: 'kv' }, h('span', {}, 'Selling price per person'), h('b', {}, money(c.perPerson, s.currency))),
      h('div', { class: 'kv' }, h('span', {}, 'Cost per person'), h('b', {}, money(c.costPerPerson, s.currency))));
    return c;
  }
  const numIn = (l, key, attrs) => { const i = inp({ type: 'number', min: 0, step: '0.01', value: l[key], disabled: !canWrite, ...attrs }); i.addEventListener('input', () => { l[key] = i.value; recalc(); }); return i; };
  function drawLines() {
    body.replaceChildren(table([
      { label: 'Item', render: (l) => { const i = inp({ value: l.label, maxlength: 200, disabled: !canWrite, 'aria-label': 'Item' }); i.addEventListener('input', () => { l.label = i.value; }); return h('div', {}, i, l.vendor_name ? h('div', { class: 'muted' }, raw(l.vendor_name)) : null); } },
      { label: 'Quantity', render: (l) => numIn(l, 'qty', { 'aria-label': 'Quantity' }) },
      { label: 'Price each', render: (l) => numIn(l, 'unit_price', { 'aria-label': 'Price each' }) },
      { label: 'Times people', render: (l) => { const c = h('input', { type: 'checkbox', checked: !!l.per_person, disabled: !canWrite, 'aria-label': 'Multiply by the number of people' }); c.addEventListener('change', () => { l.per_person = c.checked; recalc(); }); return c; } },
      { label: 'Total', class: 'num', render: (l) => h('span', { 'data-total': b.lines.indexOf(l) }) },
      canWrite ? { label: '', render: (l) => btn('Remove', { kind: 'sm', onClick: () => { b.lines.splice(b.lines.indexOf(l), 1); drawLines(); } }) } : null,
    ].filter(Boolean), b.lines, { empty: 'No lines yet. Add rates from your vendors, or type a line by hand.' }));
    recalc();
  }
  [f.people, f.cur, f.margin].forEach((i) => i.addEventListener('input', recalc));

  async function save() {
    const s = state();
    if (!s.title) throw new Error('Give the budget a name.');
    const [kind, link] = f.trip.value ? f.trip.value.split(':') : [null, null];
    const payload = { title: s.title, client_name: s.client_name || null, client_phone: s.client_phone || null, people: s.people, currency: s.currency, margin_percent: s.margin || '0', notes: s.notes || null, status: s.status,
      event_id: kind === 'e' ? link : null, package_id: kind === 'p' ? link : null,
      lines: b.lines.filter((l) => String(l.label).trim()).map((l) => ({ label: String(l.label).trim(), vendor_id: l.vendor_id || null, vendor_name: l.vendor_name || null, unit: l.unit || null, qty: String(l.qty || 0), unit_price: String(l.unit_price || 0), per_person: !!l.per_person, note: l.note || null })) };
    const r = isNew ? await post('/budgets', payload) : await patch(`/budgets/${id}`, payload);
    toast('Budget saved', 'ok');
    if (isNew) location.hash = `#/budgets/${r.id}`;
  }

  const root = h('div', {},
    h('p', {}, h('a', { href: '#/budgets' }, 'All budgets')),
    pageHead(isNew ? 'New budget' : raw(b.title), 'Add what the trip costs from your vendor rates, set your margin, and see the price per person.',
      !isNew && canWrite ? btn('Make a copy', { icon: 'copy', onClick: async () => { const c = await post(`/budgets/${id}/copy`); toast('Copy made', 'ok'); location.hash = `#/budgets/${c.id}`; } }) : null,
      btn('Quotation', { icon: 'file-text', onClick: () => { const s = state(); openQuote({ ...s, lines: b.lines }, work(b.lines, s.people, s.margin)).catch(reportError); } }),
      canWrite ? btn('Save budget', { kind: 'primary', icon: 'save', onClick: () => save().catch(reportError) }) : null),
    h('div', { class: 'form-grid' }, field('Budget name', f.title), field('Customer', f.client), field('Customer phone', f.phone), field('For trip', f.trip), field('Status', f.status)),
    h('div', { class: 'form-grid', style: { marginTop: '12px' } }, field('Number of people', f.people), field('Currency', f.cur), field('Your margin on top of cost (%)', f.margin)),
    h('div', { class: 'row', style: { justifyContent: 'space-between', margin: '20px 0 8px' } }, h('h3', { style: { margin: 0 } }, 'What it costs'),
      canWrite ? h('div', { class: 'row' }, btn('Add from vendor rates', { icon: 'list-plus', onClick: () => pickRates(() => (f.cur.value || 'BDT').toUpperCase(), (l) => { b.lines.push(l); drawLines(); }) }),
        btn('Add a line by hand', { icon: 'plus', onClick: () => { b.lines.push({ label: '', qty: 1, unit_price: 0, per_person: false }); drawLines(); } })) : null),
    body, h('div', { style: { maxWidth: '420px', marginLeft: 'auto', marginTop: '16px' } }, totals), field('Notes for the quotation', f.notes),
    !isNew && canWrite ? h('div', { style: { marginTop: '20px' } }, btn('Delete this budget', { onClick: async () => { if (await confirmDialog(`Delete ${b.title}?`, { confirmText: 'Delete', danger: true })) { await del(`/budgets/${id}`); toast('Deleted', 'ok'); location.hash = '#/budgets'; } } })) : null);
  drawLines();
  return root;
}

// ---------- the list
async function manage() {
  const root = h('div'); const holder = h('div'); const canWrite = perms.can('budgets:write');
  const q = inp({ type: 'search', placeholder: 'Search by name or customer', 'aria-label': 'Search budgets' }); const st = sel([['', 'Any status'], ...STATUS], '');
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const page = await get('/budgets', { q: q.value.trim() || undefined, status: st.value || undefined, limit: 100 });
    holder.replaceChildren(table([
      { label: 'Budget', render: (x) => h('div', {}, h('b', {}, raw(x.title)), h('div', { class: 'muted' }, raw(x.client_name || ''))) },
      { label: 'People', class: 'num', render: (x) => x.people }, { label: 'Your cost', class: 'num', render: (x) => money(x.cost_total, x.currency) },
      { label: 'Selling price', class: 'num', render: (x) => money(x.sell_total, x.currency) }, { label: 'Margin', class: 'num', render: (x) => `${Number(x.margin_percent)}%` },
      { label: 'Status', render: (x) => badge(BADGE[x.status], statusName(x.status)) }, { label: 'Changed', render: (x) => fmtDate(x.updated_at) },
    ], page.items, { onRowClick: (x) => { location.hash = `#/budgets/${x.id}`; }, empty: 'No saved budgets yet. Start one, and it stays here for next time.' }));
  }
  const again = () => load().catch(reportError); q.addEventListener('input', debounce(again, 300)); st.addEventListener('change', again);
  root.append(h('div', { class: 'toolbar' }, h('div', { class: 'field', style: { minWidth: '220px' } }, h('span', { class: 'field-label' }, 'Search'), q), field('Status', st),
    canWrite ? h('div', { style: { marginLeft: 'auto' } }, btn('New budget', { kind: 'primary', icon: 'plus', onClick: () => { location.hash = '#/budgets/new'; } })) : null), holder);
  await load();
  return root;
}

export function render() {
  return h('div', {}, pageHead('Budgets and quotations', 'Work out what an event costs, add your margin, keep it for later, and print a quotation for the customer.'), withDocs('budgets', manage));
}

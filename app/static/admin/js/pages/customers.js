// Customers: everyone who booked or wrote in, with tags and notes, a download for Excel, and filters to pick a group.
import { get, post, patch, download } from '../api.js';
import { perms } from '../data.js';
import { h, raw, btn, field, inp, area, sel, modal, table, badge, pageHead, figures, money, fmtDate, toast, reportError, debounce } from '../ui.js';
import { withDocs } from '../docs.js';

const PAGE = 50;
const SEGMENTS = [['', 'All customers'], ['repeat', 'Repeat guests (2 or more stays)'], ['never', 'Never stayed'], ['lapsed180', 'Stayed, but not in the last 6 months'], ['lapsed365', 'Stayed, but not in the last year']];
const SOURCES = [['', 'Anywhere'], ['BOOKING', 'From a booking'], ['CONTACT', 'From the website contact form'], ['MANUAL', 'Added by hand']];
const SORTS = [['recent', 'Newest first'], ['spent', 'Most spent'], ['stays', 'Most stays'], ['name', 'Name']];
const sourceText = (s) => ({ BOOKING: 'Booking', CONTACT: 'Website contact', MANUAL: 'Added by hand' }[s] || s);
const tagList = (v) => v.split(',').map((x) => x.trim()).filter(Boolean);
const chips = (tags) => h('div', { class: 'chips' }, tags.map((t) => h('span', { class: 'chip' }, raw(t))));

function segmentParams(seg) {
  if (seg === 'repeat') return { min_stays: 2 };
  if (seg === 'never') return { max_stays: 0 };
  if (seg === 'lapsed180') return { inactive_days: 180 };
  if (seg === 'lapsed365') return { inactive_days: 365 };
  return {};
}

async function openCustomer(id, onChanged) {
  const m = modal({ title: 'Customer', wide: true, body: h('div', { class: 'spinner' }) });
  try {
    const c = await get(`/customers/${id}`);
    const canEdit = perms.can('customers:manage');
    const name = inp({ value: c.name, maxlength: 200, disabled: !canEdit });
    const phone = inp({ value: c.phone || '', maxlength: 40, disabled: !canEdit });
    const tags = inp({ value: c.tags.join(', '), placeholder: 'For example: vip, eid guest', disabled: !canEdit });
    const notes = area({ value: c.notes || '', rows: 3, maxlength: 2000, disabled: !canEdit });
    m.setBody([
      figures([{ value: c.stays, label: 'Confirmed stays' }, { value: money(c.total_spent, c.currency), label: 'Total spent' },
        { value: c.last_stay ? fmtDate(c.last_stay) : '-', label: 'Last stay' }, { value: c.next_stay ? fmtDate(c.next_stay) : '-', label: 'Next stay' }]),
      h('div', { class: 'form-grid' }, field('Name', name), field('Email', inp({ value: c.email, disabled: true })), field('Phone', phone),
        field('Where from', inp({ value: sourceText(c.source), disabled: true }))),
      field('Tags', tags, 'Separate with commas. Use them to pick a group later.'),
      field('Notes', notes),
      h('h3', { style: { margin: '18px 0 8px' } }, 'Bookings'),
      table([
        { label: 'Reference', render: (b) => h('b', {}, b.booking_ref || '-') },
        { label: 'Where', render: (b) => raw(`${b.unit} - ${b.property}`) },
        { label: 'Stay', render: (b) => `${fmtDate(b.check_in)} to ${fmtDate(b.check_out)}` },
        { label: 'Total', class: 'num', render: (b) => money(b.total_amount, b.currency) },
        { label: 'Status', render: (b) => badge(b.status) },
      ], c.bookings, { empty: 'No bookings yet.' }),
    ]);
    m.setActions([
      btn('Close', { onClick: () => m.close() }),
      canEdit ? btn('Save changes', { kind: 'primary', onClick: async () => {
        await patch(`/customers/${id}`, { name: name.value.trim(), phone: phone.value.trim(), tags: tagList(tags.value), notes: notes.value.trim() });
        toast('Saved', 'ok'); m.close(); onChanged();
      } }) : null,
    ]);
  } catch (e) { m.close(); throw e; }
}

function openAdd(onChanged) {
  const name = inp({ maxlength: 200 }); const email = inp({ type: 'email' }); const phone = inp({ maxlength: 40 }); const tags = inp({ placeholder: 'For example: walk-in' });
  const m = modal({ title: 'Add a customer', body: [h('div', { class: 'form-grid' }, field('Full name', name), field('Email', email), field('Phone', phone), field('Tags', tags, 'Separate with commas.'))],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Add customer', { kind: 'primary', onClick: async () => {
      if (!name.value.trim()) throw new Error('Enter the guest name.');
      if (!email.value.trim()) throw new Error('Enter the guest email.');
      await post('/customers', { name: name.value.trim(), email: email.value.trim(), phone: phone.value.trim() || null, tags: tagList(tags.value) });
      toast('Customer added', 'ok'); m.close(); onChanged();
    } })] });
}

function openBulk(count, scopeText, run, existingTags) {
  const tag = inp({ placeholder: 'Tag name', maxlength: 30, list: 'kt-tags' });
  const list = h('datalist', { id: 'kt-tags' }, existingTags.map((t) => h('option', { value: t })));
  const mode = sel([['add', 'Add this tag'], ['remove', 'Remove this tag']], 'add');
  const m = modal({ title: 'Tag customers', body: [h('p', {}, `${scopeText}`), h('div', { class: 'form-grid' }, field('Action', mode), field('Tag', tag)), list],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Apply', { kind: 'primary', onClick: async () => {
      const t = tag.value.trim();
      if (!t) throw new Error('Enter a tag.');
      const r = await run(mode.value === 'add' ? { add: [t] } : { remove: [t] });
      toast(`${r.changed} customers updated`, 'ok'); m.close();
    } })] });
}

export function render() {
  return h('div', {}, pageHead('Customers', 'Everyone who has booked or written to you, in one list. Pick a group, tag it, and download it for Excel.'), withDocs('customers', manage));
}

async function manage() {
  const root = h('div'); const holder = h('div'); const bar = h('div');
  const q = inp({ type: 'search', placeholder: 'Search name, email or phone', 'aria-label': 'Search customers' });
  const seg = sel(SEGMENTS, ''); const tag = sel([['', 'Any tag']], ''); const src = sel(SOURCES, ''); const sort = sel(SORTS, 'recent');
  let offset = 0; let page = null; const picked = new Set(); let allMatching = false; let knownTags = [];

  const filters = () => ({ q: q.value.trim() || undefined, tag: tag.value || undefined, source: src.value || undefined, sort: sort.value, ...segmentParams(seg.value) });

  async function loadTags() {
    try {
      const rows = await get('/customers/tags'); knownTags = rows.map((r) => r.tag);
      tag.replaceChildren(h('option', { value: '' }, 'Any tag'), ...rows.map((r) => h('option', { value: r.tag }, raw(`${r.tag} (${r.customers})`))));
    } catch { /* tags are optional */ }
  }
  function drawBar() {
    const n = allMatching ? page.total : picked.size;
    bar.replaceChildren(...(n ? [h('div', { class: 'callout row', style: { marginBottom: '12px' } },
      h('b', {}, `${n} selected`),
      !allMatching && picked.size === page.items.length && page.total > page.items.length ? btn(`Select all ${page.total} that match`, { kind: 'sm', onClick: () => { allMatching = true; drawBar(); } }) : null,
      perms.can('customers:manage') ? btn('Tag...', { kind: 'sm', icon: 'tag', onClick: () => openBulk(n, allMatching ? `All ${page.total} customers that match your filters.` : `${picked.size} selected customers.`,
        async (change) => { const r = await post('/customers/tags/apply', { ...(allMatching ? { filters: filters() } : { ids: [...picked] }), ...change }); picked.clear(); allMatching = false; await load(); await loadTags(); return r; }, knownTags) }) : null,
      btn('Clear', { kind: 'sm', onClick: () => { picked.clear(); allMatching = false; load().catch(reportError); } }))] : []));
  }
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    page = await get('/customers', { ...filters(), limit: PAGE, offset });
    const all = h('input', { type: 'checkbox', 'aria-label': 'Select everyone on this page', checked: page.items.length > 0 && page.items.every((c) => picked.has(c.id) || allMatching),
      onchange: (e) => { page.items.forEach((c) => (e.target.checked ? picked.add(c.id) : picked.delete(c.id))); allMatching = false; load().catch(reportError); } });
    const money0 = (c) => money(c.total_spent, c.currency);
    holder.replaceChildren(
      ...(page.total ? [h('div', { class: 'hint', style: { marginBottom: '8px' } }, `${page.total} customers`)] : []),
      table([
        { label: all, render: (c) => h('input', { type: 'checkbox', 'aria-label': `Select ${c.name}`, checked: picked.has(c.id) || allMatching,
          onchange: (e) => { if (e.target.checked) picked.add(c.id); else { picked.delete(c.id); allMatching = false; } drawBar(); } }) },
        { label: 'Customer', render: (c) => h('div', {}, h('b', {}, raw(c.name)), h('div', { class: 'muted' }, raw([c.email, c.phone].filter(Boolean).join(' - ')))) },
        { label: 'Stays', class: 'num', render: (c) => c.stays + (c.cancelled ? ` (${c.cancelled} cancelled)` : '') },
        { label: 'Total spent', class: 'num', render: money0 },
        { label: 'Last stay', render: (c) => (c.last_stay ? fmtDate(c.last_stay) : '-') },
        { label: 'Next stay', render: (c) => (c.next_stay ? fmtDate(c.next_stay) : '-') },
        { label: 'Tags', render: (c) => chips(c.tags) },
        { label: 'Where from', render: (c) => sourceText(c.source) },
      ], page.items, { onRowClick: (c) => openCustomer(c.id, async () => { await load(); await loadTags(); }).catch(reportError), empty: 'No customers match. Guests appear here when they book, or when they write through your website.' }),
      h('div', { class: 'pager' },
        h('span', {}, page.total ? `${offset + 1}-${Math.min(offset + PAGE, page.total)} of ${page.total}` : ''),
        h('div', { class: 'row' },
          btn('Previous', { kind: 'sm', onClick: () => { offset = Math.max(0, offset - PAGE); return load().catch(reportError); } }),
          btn('Next', { kind: 'sm', onClick: () => { if (offset + PAGE < page.total) { offset += PAGE; return load().catch(reportError); } } }))));
    drawBar();
  }
  const refilter = () => { offset = 0; picked.clear(); allMatching = false; load().catch(reportError); };
  q.addEventListener('input', debounce(refilter, 300));
  [seg, tag, src, sort].forEach((s) => s.addEventListener('change', refilter));
  root.append(
    h('div', { class: 'toolbar' },
      h('div', { class: 'field', style: { minWidth: '240px' } }, h('span', { class: 'field-label' }, 'Search'), q),
      h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Group'), seg), h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Tag'), tag),
      h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Where from'), src), h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Order'), sort),
      h('div', { class: 'row', style: { marginLeft: 'auto' } },
        perms.can('customers:export') ? btn('Download for Excel', { icon: 'download', onClick: async () => { await download('/customers/export', filters(), 'customers.csv'); } }) : null,
        perms.can('customers:manage') ? btn('Add customer', { kind: 'primary', icon: 'plus', onClick: () => openAdd(() => { load().catch(reportError); }) }) : null)),
    bar, holder);
  await loadTags(); await load();
  return root;
}

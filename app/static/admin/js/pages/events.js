// Events: packages (ready-made trips with a "starting from" price) and the dated events made from them.
import { get, post, patch, del } from '../api.js';
import { perms } from '../data.js';
import { h, raw, btn, field, fieldBox, inp, area, sel, check, modal, table, tabs, badge, pageHead, confirmDialog, money, fmtDate, toast, reportError, slugify, today, addDays } from '../ui.js';
import { t } from '../i18n.js';
import { renderDocs } from '../docs.js';
import { openPicker } from '../media.js';

const lines = (s) => String(s || '').split('\n').map((x) => x.trim()).filter(Boolean);
const STATUS = { DRAFT: 'Draft', PUBLISHED: 'Published', CLOSED: 'Closed' };
const KIND = { DRAFT: 'DRAFT', PUBLISHED: 'PUBLISHED', CLOSED: 'CANCELLED' };

/** Day-by-day plan editor. get() gives the days in order, numbered from 1. */
export function itineraryEditor(days) {
  const box = h('div', { class: 'itin' });
  const rows = [];
  function add(d = {}) {
    const title = inp({ value: d.title || '', placeholder: 'For example: Dhaka to Sajek', maxlength: 200, 'aria-label': 'Day title' });
    const details = area({ value: d.details || '', rows: 2, placeholder: 'What happens on this day', maxlength: 3000, 'aria-label': 'Day details' });
    const row = h('div', { class: 'itin-row' }, h('b', { class: 'itin-n' }), h('div', { class: 'itin-body' }, title, details),
      btn('Remove', { kind: 'sm', onClick: () => { rows.splice(rows.indexOf(r), 1); row.remove(); number(); } }));
    const r = { row, title, details }; rows.push(r); box.append(row); number();
  }
  const number = () => rows.forEach((r, i) => { r.row.querySelector('.itin-n').textContent = t(`Day ${i + 1}`); });
  (days || []).forEach(add);
  const root = h('div', {}, box, btn('Add a day', { kind: 'sm', icon: 'plus', onClick: () => add() }));
  root.get = () => rows.filter((r) => r.title.value.trim()).map((r, i) => ({ day: i + 1, title: r.title.value.trim(), details: r.details.value.trim() || null }));
  return root;
}

const TRIP_TYPES = ['Relax', 'Trekking', 'Adventure', 'Family', 'Honeymoon', 'Friends group', 'Religious', 'Educational', 'Corporate'];
const BUSES = ['AC bus', 'Non-AC bus', 'AC sleeper coach', 'Mini bus', 'Microbus', 'Private car'];
const TRANSPORT = ['CNG', 'Jeep', 'Chander gari', 'Boat', 'Launch', 'Train', 'Flight', 'Rickshaw', 'Local bus', 'Motorbike'];
const PAYMENTS = ['bKash', 'Nagad', 'Rocket', 'Bank transfer', 'Card', 'Cash'];

/** Ticks for the usual choices, and a box for anything else (typed with commas). get() lists everything chosen. */
export function multiPick(options, selected = [], { other = 'Other, separated by commas' } = {}) {
  const boxes = options.map((o) => ({ o, c: h('input', { type: 'checkbox', checked: selected.includes(o) }) }));
  const extra = inp({ value: selected.filter((x) => !options.includes(x)).join(', '), placeholder: other, 'aria-label': other });
  const root = h('div', { class: 'mp-wrap' }, h('div', { class: 'mp' }, boxes.map(({ o, c }) => h('label', { class: 'check' }, c, o))), extra);
  root.get = () => [...boxes.filter((x) => x.c.checked).map((x) => x.o), ...extra.value.split(',').map((x) => x.trim()).filter(Boolean)];
  return root;
}

/** Photos for a card or an event: choose from the library (upload there too), put the best one first. */
export function photosField(initial = []) {
  let urls = [...initial]; const grid = h('div', { class: 'photos' });
  const draw = () => {
    grid.replaceChildren(...urls.map((u, i) => h('div', { class: 'photo' }, h('img', { src: u, alt: '' }),
      h('div', { class: 'photo-bar' }, i ? btn('First', { kind: 'sm', title: 'Use as the main photo', onClick: () => { urls.unshift(...urls.splice(i, 1)); draw(); } }) : h('span', { class: 'chip' }, 'Main photo'),
        btn('Remove', { kind: 'sm', onClick: () => { urls.splice(i, 1); draw(); } })))));
  };
  const add = btn('Add photos', { icon: 'images', onClick: async () => { const r = await openPicker({ kind: 'image', multiple: true }); (r || []).forEach((a) => { if (!urls.includes(a.url)) urls.push(a.url); }); draw(); } });
  draw();
  const root = h('div', {}, grid, add); root.get = () => urls;
  return root;
}

/** Everything about a trip that a package and an event share. */
function tripFields(src) {
  const f = {
    summary: inp({ value: src.summary || '', maxlength: 600 }), place: inp({ value: src.location || '', maxlength: 200, placeholder: 'For example: Sajek' }),
    details: area({ value: src.description || '', rows: 5 }), pickup: inp({ value: src.pickup_location || '', maxlength: 300, placeholder: 'For example: Kallyanpur bus counter, Dhaka' }),
    stay: area({ value: src.accommodation || '', rows: 3, maxlength: 3000, placeholder: 'Where the guests will stay' }),
    types: multiPick(TRIP_TYPES, src.trip_types || []), transport: multiPick(TRANSPORT, src.other_transport || []),
    bus: inp({ value: src.bus_type || '', maxlength: 80, list: 'kt-buses', placeholder: 'Choose or type' }),
    inc: area({ value: (src.inclusions || []).join('\n'), rows: 4, placeholder: 'One per line' }), exc: area({ value: (src.exclusions || []).join('\n'), rows: 4, placeholder: 'One per line' }),
    health: area({ value: (src.health_rules || []).join('\n'), rows: 4, placeholder: 'One per line' }), warn: area({ value: (src.warnings || []).join('\n'), rows: 4, placeholder: 'One per line' }),
    need: area({ value: (src.essentials || []).join('\n'), rows: 4, placeholder: 'One per line' }),
  };
  const plan = itineraryEditor(src.itinerary); const photos = photosField(src.photos?.length ? src.photos : (src.cover_image ? [src.cover_image] : []));
  const nodes = [
    h('datalist', { id: 'kt-buses' }, BUSES.map((b) => h('option', { value: b }))),
    field('Short line for the website', f.summary), field('Trip details', f.details),
    h('div', { class: 'form-grid' }, field('Pickup location', f.pickup), field('Place', f.place), field('Bus type', f.bus)),
    fieldBox('Type of trip', f.types), fieldBox('Other transport on the trip', f.transport), field('Where guests stay', f.stay),
    h('h3', { style: { margin: '14px 0 6px' } }, 'Day by day'), plan,
    h('div', { class: 'form-grid', style: { marginTop: '14px' } }, field('What the budget includes', f.inc, 'One per line.'), field('What the budget does not include', f.exc, 'One per line.')),
    h('div', { class: 'form-grid' }, field('Health rules', f.health, 'One per line.'), field('Warnings', f.warn, 'One per line.'), field('What to bring', f.need, 'One per line.')),
    fieldBox('Photos', photos)];
  const get = () => { const ph = photos.get(); return {
    summary: f.summary.value.trim() || null, description: f.details.value.trim() || null, location: f.place.value.trim() || null, pickup_location: f.pickup.value.trim() || null,
    accommodation: f.stay.value.trim() || null, trip_types: f.types.get(), other_transport: f.transport.get(), bus_type: f.bus.value.trim() || null, itinerary: plan.get(),
    inclusions: lines(f.inc.value), exclusions: lines(f.exc.value), health_rules: lines(f.health.value), warnings: lines(f.warn.value), essentials: lines(f.need.value), photos: ph, cover_image: ph[0] || null }; };
  return { nodes, get, place: f.place };
}

function openPackage(pk, done) {
  const edit = !!pk;
  const f = { title: inp({ value: pk?.title || '', maxlength: 300 }), days: inp({ type: 'number', min: 1, max: 60, value: pk?.duration_days || 3 }),
    price: inp({ type: 'number', min: 0, step: '0.01', value: pk?.starting_price || '' }), cur: inp({ value: pk?.currency || 'BDT', maxlength: 3 }), pub: check('Show this package on the website', !!pk?.is_published) };
  const trip = tripFields(pk || {});
  const m = modal({ title: edit ? 'Edit package' : 'New package', wide: true, body: [
    h('div', { class: 'form-grid' }, field('Package name', f.title), field('How many days', f.days), field('Starting from (per person)', f.price), field('Currency', f.cur)), ...trip.nodes, f.pub],
  actions: [btn('Cancel', { onClick: () => m.close() }), btn(edit ? 'Save changes' : 'Create package', { kind: 'primary', onClick: async () => {
    if (!f.title.value.trim()) throw new Error('Enter the package name.');
    const body = { title: f.title.value.trim(), duration_days: Number(f.days.value) || 1, starting_price: f.price.value || '0', currency: (f.cur.value || 'BDT').toUpperCase(), is_published: f.pub.querySelector('input').checked, ...trip.get() };
    if (edit) await patch(`/packages/${pk.id}`, body); else await post('/packages', body);
    toast(edit ? 'Saved' : 'Package created', 'ok'); m.close(); done();
  } })] });
}

/** One form for an event. For a new event from a package it arrives filled in; add the seats, dates, payments and photos, then publish. */
function openEvent(ev, done, { create = false, packageId = null } = {}) {
  const f = {
    title: inp({ value: ev.title, maxlength: 300 }), start: inp({ type: 'date', value: ev.starts_on }), end: inp({ type: 'date', value: ev.ends_on }),
    price: inp({ type: 'number', min: 0, step: '0.01', value: ev.price }), seats: inp({ type: 'number', min: 1, value: ev.seats || '', placeholder: 'How many people can join' }),
    status: sel(Object.entries(STATUS), ev.status),
  };
  const days = ev._days || 1; let endTouched = !create;
  f.end.addEventListener('input', () => { endTouched = true; });
  f.start.addEventListener('input', () => { if (!endTouched && f.start.value) f.end.value = addDays(f.start.value, days - 1); });
  const pay = multiPick(PAYMENTS, ev.payment_methods || [], { other: 'Other ways to pay, separated by commas' });
  const trip = tripFields(ev);
  const m = modal({ title: create ? 'New event' : 'Edit event', wide: true, body: [
    create ? h('div', { class: 'callout', style: { marginBottom: '12px' } }, 'Everything from the package is filled in below. Add the seats, dates, payment ways and photos, then publish.') : null,
    h('div', { class: 'form-grid' }, field('Event name', f.title), field('Journey starts', f.start), field('Journey ends', f.end), field('Price per person', f.price), field('Number of seats', f.seats, 'One person or many. Leave empty for no limit.'),
      field('Status', f.status, 'Only published events appear on the website.')),
    fieldBox('Payment ways', pay), ...trip.nodes],
  actions: [btn('Cancel', { onClick: () => m.close() }), btn(create ? 'Publish event' : 'Save changes', { kind: 'primary', onClick: async () => {
    if (!f.title.value.trim()) throw new Error('Enter the event name.');
    if (!f.start.value) throw new Error('Choose the start date.');
    const body = { title: f.title.value.trim(), starts_on: f.start.value, ends_on: f.end.value || f.start.value, price: f.price.value || '0', seats: f.seats.value ? Number(f.seats.value) : null,
      status: f.status.value, payment_methods: pay.get(), ...trip.get() };
    if (create) await post('/events', { ...body, package_id: packageId }); else await patch(`/events/${ev.id}`, body);
    toast(create ? 'Event created' : 'Saved', 'ok'); m.close(); done();
  } })] });
}

const fromPackage = (pk, done) => openEvent({ ...pk, title: pk.title, starts_on: addDays(today(), 14), ends_on: addDays(today(), 14 + pk.duration_days - 1), price: pk.starting_price, seats: null,
  status: 'PUBLISHED', payment_methods: [], _days: pk.duration_days }, done, { create: true, packageId: pk.id });

async function eventsTab(canWrite) {
  const root = h('div'); const holder = h('div'); let when = 'upcoming';
  const filter = sel([['upcoming', 'Coming up'], ['all', 'All events'], ['DRAFT', 'Drafts'], ['CLOSED', 'Closed']], when);
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const params = { limit: 200, ...(when === 'upcoming' ? { upcoming: true } : when === 'all' ? {} : { status: when }) };
    const page = await get('/events', params);
    holder.replaceChildren(table([
      { label: 'Event', render: (e) => h('div', {}, h('b', {}, raw(e.title)), h('div', { class: 'muted' }, raw(e.location || ''))) },
      { label: 'Dates', render: (e) => `${fmtDate(e.starts_on)} to ${fmtDate(e.ends_on)}` },
      { label: 'Price per person', class: 'num', render: (e) => money(e.price, e.currency) },
      { label: 'Seats left', class: 'num', render: (e) => (e.seats == null ? '-' : raw(`${e.seats_left ?? e.seats} / ${e.seats}`)) },
      { label: 'Status', render: (e) => badge(KIND[e.status], STATUS[e.status]) },
      canWrite ? { label: '', render: (e) => h('div', { class: 'actions' },
        btn('Edit', { kind: 'sm', onClick: () => openEvent(e, () => load().catch(reportError)) }),
        e.status === 'PUBLISHED' ? btn('Close', { kind: 'sm', onClick: async () => { await patch(`/events/${e.id}`, { status: 'CLOSED' }); toast('Event closed', 'ok'); await load(); } })
          : btn('Publish', { kind: 'sm', onClick: async () => { await patch(`/events/${e.id}`, { status: 'PUBLISHED' }); toast('Event published', 'ok'); await load(); } }),
        btn('Delete', { kind: 'sm', onClick: async () => { if (await confirmDialog(`Delete ${e.title}?`, { confirmText: 'Delete', danger: true })) { await del(`/events/${e.id}`); toast('Deleted', 'ok'); await load(); } } })) } : null,
    ].filter(Boolean), page.items, { empty: 'No events here. Open the Packages tab and publish one from a package.' }));
  }
  filter.addEventListener('change', () => { when = filter.value; load().catch(reportError); });
  root.append(h('div', { class: 'toolbar' }, field('Show', filter)), holder);
  await load();
  return root;
}

async function packagesTab(canWrite, goEvents) {
  const root = h('div'); const holder = h('div');
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const page = await get('/packages', { limit: 200 });
    holder.replaceChildren(table([
      { label: 'Package', render: (p) => h('div', {}, h('b', {}, raw(p.title)), h('div', { class: 'muted' }, p.location ? raw(p.location + ' - ') : null, p.duration_days === 1 ? '1 day' : `${p.duration_days} days`)) },
      { label: 'Starting from', class: 'num', render: (p) => money(p.starting_price, p.currency) },
      { label: 'Website', render: (p) => badge(p.is_published ? 'PUBLISHED' : 'DRAFT', p.is_published ? 'Shown' : 'Hidden') },
      canWrite ? { label: '', render: (p) => h('div', { class: 'actions' },
        btn('Publish an event', { kind: 'sm', icon: 'calendar-plus', onClick: () => fromPackage(p, goEvents) }),
        btn('Edit', { kind: 'sm', onClick: () => openPackage(p, () => load().catch(reportError)) }),
        btn('Delete', { kind: 'sm', onClick: async () => { if (await confirmDialog(`Delete ${p.title}? Events already made from it stay.`, { confirmText: 'Delete', danger: true })) { await del(`/packages/${p.id}`); toast('Deleted', 'ok'); await load(); } } })) } : null,
    ].filter(Boolean), page.items, { empty: 'No packages yet. A package holds the plan and a starting price, so a new event is one date away.' }));
  }
  root.append(canWrite ? h('div', { class: 'toolbar' }, h('div', { style: { marginLeft: 'auto' } }, btn('New package', { kind: 'primary', icon: 'plus', onClick: () => openPackage(null, () => load().catch(reportError)) }))) : null, holder);
  await load();
  return root;
}

export function render() {
  const canWrite = perms.can('events:write');
  let t;
  t = tabs([
    { id: 'events', label: 'Events', render: () => eventsTab(canWrite) },
    { id: 'packages', label: 'Packages', render: () => packagesTab(canWrite, () => t.show('events')) },
    { id: 'docs', label: 'API documentation', render: async () => h('div', {}, await renderDocs('packages'), h('hr'), await renderDocs('events')) },
  ]);
  return h('div', {}, pageHead('Events', 'Keep ready-made packages, and publish a dated event from one in a few clicks. Your website reads both through the API.'), t);
}

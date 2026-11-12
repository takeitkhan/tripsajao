import { get, post, put, patch, del } from '../api.js';
import { invalidate } from '../data.js';
import {
  h, btn, field, inp, area, sel, check, modal, confirmDialog, table, badge, emptyState, pageHead, facilityChip,
  money, humanize, slugify, toast, reportError,
} from '../ui.js';
import { facilityEditor, mediaEditor } from '../components.js';
import { withDocs } from '../docs.js';
import { openPricingEditor } from './pricing.js';

const PROPERTY_TYPES = [['RESORT', 'Resort'], ['HOTEL', 'Hotel'], ['HOUSEBOAT', 'Houseboat']];
const unitTypesFor = (pt) => (pt === 'HOUSEBOAT' ? [['CABIN', 'Cabin'], ['WHOLE_BOAT', 'Whole-boat charter']] : [['ROOM', 'Room'], ['COTTAGE', 'Cottage'], ['DUPLEX', 'Duplex']]);
const num = (el) => (el.value === '' ? undefined : Number(el.value));

let presetCache = null;
const presets = async () => (presetCache ||= await get('/properties/facility-presets').catch(() => []));

// ---------------------------------------------------------------- property modal
export async function openPropertyModal(prop, onSaved) {
  const meta = prop?.metadata || {};
  const type = sel(PROPERTY_TYPES, prop?.type || 'RESORT', { disabled: !!prop });
  const name = inp({ value: prop?.name || '', maxlength: 200 });
  const slug = inp({ value: prop?.slug || '', maxlength: 100, placeholder: 'auto from the name' });
  let slugTouched = !!prop;
  slug.addEventListener('input', () => { slugTouched = true; });
  name.addEventListener('input', () => { if (!slugTouched) slug.value = slugify(name.value); });
  const location = inp({ value: prop?.location || '', maxlength: 300 });
  const address = inp({ value: meta.address || '' });
  const desc = area({ rows: 3, value: meta.description || '' });
  const amen = facilityEditor(meta.amenities || [], await presets());
  const media = mediaEditor(meta.media || []);
  const m = modal({
    title: prop ? 'Edit property' : 'New property', wide: true,
    body: [
      h('div', { class: 'form-grid' }, field('Type', type, prop ? 'The type cannot change after creation.' : null), field('Name', name), field('Web address name', slug, 'Used in links like /properties/lotus-houseboat'), field('Location', location), field('Address', address)),
      field('Description', desc),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Property-wide amenities'), amen.el),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Photos and videos'), media.el),
    ],
    actions: [
      btn('Cancel', { onClick: () => m.close() }),
      btn(prop ? 'Save changes' : 'Create property', { kind: 'primary', onClick: async () => {
        const body = {
          name: name.value.trim(), slug: slug.value.trim() || slugify(name.value), location: location.value.trim() || null,
          metadata: { ...meta, description: desc.value.trim() || null, address: address.value.trim() || null, amenities: amen.get(), media: media.get() },
        };
        const saved = prop ? await patch(`/properties/${prop.id}`, body) : await post('/properties', { type: type.value, ...body });
        invalidate(); toast(prop ? 'Property saved' : 'Property created', 'ok'); m.close(); onSaved?.(saved);
      } }),
    ],
  });
}

// ---------------------------------------------------------------- unit modal
export async function openUnitModal(prop, unit, onSaved) {
  const grid = prop.type !== 'HOUSEBOAT';
  const lay = unit?.layout || {};
  const name = inp({ value: unit?.unit_name || '', maxlength: 120 });
  const type = sel(unitTypesFor(prop.type), unit?.type || unitTypesFor(prop.type)[0][0], { disabled: !!unit });
  const cap = inp({ type: 'number', min: 1, max: 100, value: unit?.capacity ?? 2 });
  const status = unit ? sel([['AVAILABLE', 'Available for booking'], ['MAINTENANCE', 'Under maintenance']], unit.status) : null;
  const L = {};
  const layoutFields = grid
    ? [['floor', 'Floor', 1], ['row', 'Row', 0], ['col', 'Column', 0], ['row_span', 'Rows spanned', 1], ['col_span', 'Columns spanned', 1]]
    : [['x', 'Left (x)', null], ['y', 'Top (y)', null], ['w', 'Width', null], ['h', 'Height', null]];
  layoutFields.forEach(([k, label, def]) => { L[k] = inp({ type: 'number', min: 0, step: 'any', value: lay[k] ?? (unit ? '' : def ?? '') }); });
  const fac = facilityEditor(unit?.facilities || [], await presets());
  const media = mediaEditor(unit?.media || []);
  const m = modal({
    title: unit ? `Edit ${unit.unit_name}` : 'Add unit', wide: true,
    body: [
      h('div', { class: 'form-grid' }, field('Name', name), field('Type', type), field('Sleeps', cap), status ? field('Status', status) : null),
      h('div', {}, h('h3', { style: { marginBottom: '4px' } }, 'Position on the live board'),
        h('p', { class: 'hint' }, grid ? 'Row and column place the room in the building grid. Leave blank to fill automatically.' : 'Leave blank to arrange cabins along the boat automatically.'),
        h('div', { class: 'form-grid' }, layoutFields.map(([k, label]) => field(label, L[k])))),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Amenities'), fac.el),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Photos and videos'), media.el),
    ],
    actions: [
      btn('Cancel', { onClick: () => m.close() }),
      btn(unit ? 'Save changes' : 'Add unit', { kind: 'primary', onClick: async () => {
        const layout = Object.fromEntries(layoutFields.map(([k]) => [k, num(L[k])]).filter(([, v]) => v !== undefined));
        const body = { unit_name: name.value.trim(), capacity: Number(cap.value), facilities: fac.get(), media: media.get(), layout: Object.keys(layout).length ? layout : null };
        if (unit) await patch(`/properties/units/${unit.id}`, { ...body, status: status.value });
        else await post(`/properties/${prop.id}/units`, { ...body, type: type.value });
        invalidate(); toast(unit ? 'Unit saved' : 'Unit added', 'ok'); m.close(); onSaved?.();
      } }),
    ],
  });
}

// ---------------------------------------------------------------- add several units
function openBulkModal(prop, onSaved) {
  const grid = prop.type !== 'HOUSEBOAT';
  const type = sel(unitTypesFor(prop.type), unitTypesFor(prop.type)[0][0]);
  const prefix = inp({ value: grid ? 'Room ' : 'Cabin ', maxlength: 100 });
  const start = inp({ type: 'number', min: 0, value: 1 });
  const count = inp({ type: 'number', min: 1, max: 60, value: 8 });
  const cap = inp({ type: 'number', min: 1, value: 2 });
  const floor = inp({ type: 'number', min: 0, value: 1 });
  const cols = inp({ type: 'number', min: 1, max: 12, value: 4 });
  const m = modal({
    title: 'Add several units',
    body: [
      h('p', { class: 'muted' }, 'Creates numbered units in one go, for example Room 1, Room 2, Room 3. You can edit each one afterwards.'),
      h('div', { class: 'form-grid' }, field('Type', type), field('Name starts with', prefix), field('First number', start), field('How many', count), field('Sleeps', cap),
        grid ? field('Floor', floor) : null, grid ? field('Rooms per row', cols) : null),
    ],
    actions: [
      btn('Cancel', { onClick: () => m.close() }),
      btn('Add units', { kind: 'primary', onClick: async () => {
        const n = Number(count.value); const failures = [];
        for (let i = 0; i < n; i++) {
          const body = { unit_name: `${prefix.value}${Number(start.value) + i}`.trim(), type: type.value, capacity: Number(cap.value) };
          if (grid) body.layout = { floor: Number(floor.value), row: Math.floor(i / Number(cols.value)), col: i % Number(cols.value) };
          try { await post(`/properties/${prop.id}/units`, body); } catch (e) { failures.push(`${body.unit_name}: ${e.message}`); }
        }
        invalidate(); m.close(); onSaved?.();
        if (failures.length) toast(`Added ${n - failures.length} of ${n}. ${failures[0]}`, 'error'); else toast(`Added ${n} units`, 'ok');
      } }),
    ],
  });
}

// ---------------------------------------------------------------- list page
export function renderList() {
  return h('div', {}, pageHead('Properties', 'Resorts, hotels and houseboats, with their rooms and cabins.'), withDocs('properties', manageList));
}

async function manageList() {
  const root = h('div');
  const holder = h('div');
  async function load() {
    const page = await get('/properties', { limit: 200, include_inactive: true });
    const counts = await Promise.all(page.items.map((p) => get(`/properties/${p.id}/units`, { limit: 1 }).then((r) => r.total).catch(() => '-')));
    const rows = page.items.map((p, i) => ({ ...p, units: counts[i] }));
    holder.replaceChildren(table([
      { label: 'Name', render: (p) => h('a', { href: `#/properties/${p.id}` }, h('b', {}, p.name)) },
      { label: 'Type', render: (p) => humanize(p.type) },
      { label: 'Location', render: (p) => p.location || '-' },
      { label: 'Units', class: 'num', render: (p) => p.units },
      { label: 'Status', render: (p) => badge(p.is_active ? 'PUBLISHED' : 'DRAFT', p.is_active ? 'Active' : 'Hidden') },
    ], rows, { empty: 'No properties yet. Add your first resort, hotel or houseboat.' }));
  }
  root.append(h('div', { class: 'toolbar' }, h('div', { style: { marginLeft: 'auto' } }, btn('New property', { kind: 'primary', icon: 'plus', onClick: () => openPropertyModal(null, (p) => { location.hash = `#/properties/${p.id}`; }) }))), holder);
  await load();
  return root;
}

// ---------------------------------------------------------------- detail page
export async function renderDetail(ctx) {
  const root = h('div');
  const body = h('div');
  async function load() {
    const prop = await get(`/properties/${ctx.params.id}`);
    const units = (await get(`/properties/${prop.id}/units`, { limit: 200 })).items;
    const prices = await Promise.all(units.map((u) => get(`/pricing/units/${u.id}`).catch(() => null)));
    const priceOf = Object.fromEntries(units.map((u, i) => [u.id, prices[i]]));
    const meta = prop.metadata || {};
    root.replaceChildren(
      h('p', {}, h('a', { href: '#/properties' }, 'All properties')),
      pageHead(prop.name, `${humanize(prop.type)}${prop.location ? ' in ' + prop.location : ''}`,
        btn('Edit property', { icon: 'pencil', onClick: () => openPropertyModal(prop, load) }),
        btn(prop.is_active ? 'Hide from website' : 'Show on website', { onClick: async () => { await patch(`/properties/${prop.id}`, { is_active: !prop.is_active }); invalidate(); toast(prop.is_active ? 'Hidden from website' : 'Visible on website'); await load(); } })),
      meta.amenities?.length ? h('div', { class: 'chips', style: { marginBottom: '18px' } }, meta.amenities.map(facilityChip)) : null,
      h('div', { class: 'section' }, h('h2', {}, prop.type === 'HOUSEBOAT' ? 'Cabins' : 'Rooms'),
        h('div', { class: 'row' }, btn('Add several', { icon: 'layers', onClick: () => openBulkModal(prop, load) }), btn('Add unit', { kind: 'primary', icon: 'plus', onClick: () => openUnitModal(prop, null, load) }))),
      table([
        { label: 'Name', render: (u) => h('b', {}, u.unit_name) },
        { label: 'Type', render: (u) => humanize(u.type) },
        { label: 'Sleeps', class: 'num', render: (u) => u.capacity },
        { label: 'Amenities', render: (u) => h('div', { class: 'chips' }, u.facilities.slice(0, 3).map(facilityChip), u.facilities.length > 3 ? h('span', { class: 'muted' }, `+${u.facilities.length - 3}`) : null) },
        { label: 'Weekday / weekend', render: (u) => { const p = priceOf[u.id]; return p ? `${money(p.weekday_price, p.currency)} / ${money(p.weekend_price, p.currency)}` : h('span', { class: 'muted' }, 'Not priced'); } },
        { label: 'Status', render: (u) => badge(u.status === 'MAINTENANCE' ? 'MAINTENANCE' : 'AVAILABLE', u.status === 'MAINTENANCE' ? 'Maintenance' : 'Active') },
        { label: '', render: (u) => h('div', { class: 'actions' },
          btn('Price', { kind: 'sm', onClick: () => openPricingEditor(u, units, load) }),
          btn('Edit', { kind: 'sm', onClick: () => openUnitModal(prop, u, load) }),
          btn('Remove', { kind: 'sm danger', onClick: async () => {
            if (!(await confirmDialog(`Remove ${u.unit_name}? It disappears from the board and website. Past bookings stay in your records.`, { confirmText: 'Remove', danger: true }))) return;
            await del(`/properties/units/${u.id}`); invalidate(); toast('Unit removed'); await load();
          } })) },
      ], units, { empty: `No ${prop.type === 'HOUSEBOAT' ? 'cabins' : 'rooms'} yet. Use Add several to create them quickly.` }));
  }
  await load();
  return root;
}

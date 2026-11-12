// Vendors by place (resorts, restaurants, guides, chander gari, jeep, CNG ...) and the rates each one charges.
import { get, post, patch, del } from '../api.js';
import { perms } from '../data.js';
import { h, raw, btn, field, inp, area, sel, check, modal, table, badge, pageHead, confirmDialog, money, toast, reportError, debounce } from '../ui.js';
import { withDocs } from '../docs.js';

export const KINDS = [['RESORT', 'Resort'], ['RESTAURANT', 'Restaurant'], ['GUIDE', 'Guide'], ['CHANDER_GARI', 'Chander gari'], ['JEEP', 'Jeep'], ['CNG', 'CNG'], ['BOAT', 'Boat'], ['OTHER', 'Other']];
export const UNITS = [['PER_NIGHT', 'per night'], ['PER_PERSON', 'per person'], ['PER_DAY', 'per day'], ['PER_TRIP', 'per trip'], ['PER_MEAL', 'per meal'], ['PER_ROOM', 'per room'], ['PER_UNIT', 'each']];
export const kindName = (k) => (KINDS.find((x) => x[0] === k) || [0, k])[1];
export const unitName = (u) => (UNITS.find((x) => x[0] === u) || [0, u])[1];

function openRate(vendorId, rate, done) {
  const item = inp({ value: rate?.item || '', maxlength: 200, placeholder: 'For example: Double cottage' });
  const unit = sel(UNITS, rate?.unit || 'PER_NIGHT'); const price = inp({ type: 'number', min: 0, step: '0.01', value: rate?.price || '' });
  const cur = inp({ value: rate?.currency || 'BDT', maxlength: 3 }); const notes = inp({ value: rate?.notes || '', maxlength: 500 });
  const m = modal({ title: rate ? 'Edit rate' : 'Add a rate', body: [h('div', { class: 'form-grid' }, field('What it is', item), field('Charged', unit), field('Price', price), field('Currency', cur), field('Note', notes))],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Save rate', { kind: 'primary', onClick: async () => {
      if (!item.value.trim()) throw new Error('Enter what the rate is for.');
      if (price.value === '') throw new Error('Enter the price.');
      const body = { item: item.value.trim(), unit: unit.value, price: price.value, currency: (cur.value || 'BDT').toUpperCase(), notes: notes.value.trim() || null };
      if (rate) await patch(`/rates/${rate.id}`, body); else await post(`/vendors/${vendorId}/rates`, body);
      toast('Saved', 'ok'); m.close(); done();
    } })] });
}

async function openVendor(id, canWrite, changed) {
  const m = modal({ title: 'Vendor', wide: true, body: h('div', { class: 'spinner' }) });
  async function draw() {
    try {
      const v = await get(`/vendors/${id}`);
      const f = { kind: sel(KINDS, v.category, { disabled: !canWrite }), name: inp({ value: v.name, maxlength: 200, disabled: !canWrite }), place: inp({ value: v.location, maxlength: 200, disabled: !canWrite }),
        phone: inp({ value: v.phone || '', maxlength: 60, disabled: !canWrite }), email: inp({ value: v.email || '', maxlength: 320, disabled: !canWrite }), address: inp({ value: v.address || '', maxlength: 400, disabled: !canWrite }),
        notes: area({ value: v.notes || '', rows: 2, disabled: !canWrite }), on: check('Offer this vendor in the budget calculator', v.is_active, { disabled: !canWrite }) };
      const reload = () => { draw(); changed(); };
      m.setBody([
        h('div', { class: 'form-grid' }, field('Kind', f.kind), field('Name', f.name), field('Place', f.place), field('Phone', f.phone), field('Email', f.email), field('Address', f.address)),
        field('Notes', f.notes), f.on,
        h('div', { class: 'row', style: { justifyContent: 'space-between', margin: '18px 0 8px' } }, h('h3', { style: { margin: 0 } }, 'Rates'),
          canWrite ? btn('Add a rate', { kind: 'sm', icon: 'plus', onClick: () => openRate(v.id, null, reload) }) : null),
        table([
          { label: 'What', render: (r) => h('div', {}, h('b', {}, raw(r.item)), r.notes ? h('div', { class: 'muted' }, raw(r.notes)) : null) },
          { label: 'Charged', render: (r) => unitName(r.unit) }, { label: 'Price', class: 'num', render: (r) => money(r.price, r.currency) },
          canWrite ? { label: '', render: (r) => h('div', { class: 'actions' }, btn('Edit', { kind: 'sm', onClick: () => openRate(v.id, r, reload) }),
            btn('Delete', { kind: 'sm', onClick: async () => { if (await confirmDialog(`Delete the rate "${r.item}"?`, { confirmText: 'Delete', danger: true })) { await del(`/rates/${r.id}`); reload(); } } })) } : null,
        ].filter(Boolean), v.rates, { empty: 'No rates yet. Add what this vendor charges, so the budget calculator can use it.' })]);
      m.setActions([
        canWrite ? btn('Delete vendor', { onClick: async () => { if (await confirmDialog(`Delete ${v.name} and all its rates?`, { confirmText: 'Delete', danger: true })) { await del(`/vendors/${v.id}`); toast('Deleted', 'ok'); m.close(); changed(); } } }) : null,
        btn('Close', { onClick: () => m.close() }),
        canWrite ? btn('Save changes', { kind: 'primary', onClick: async () => {
          if (!f.name.value.trim() || !f.place.value.trim()) throw new Error('Enter the name and the place.');
          await patch(`/vendors/${v.id}`, { category: f.kind.value, name: f.name.value.trim(), location: f.place.value.trim(), phone: f.phone.value.trim() || null, email: f.email.value.trim() || null,
            address: f.address.value.trim() || null, notes: f.notes.value.trim() || null, is_active: f.on.querySelector('input').checked });
          toast('Saved', 'ok'); m.close(); changed();
        } }) : null]);
    } catch (e) { m.close(); reportError(e); }
  }
  await draw();
}

function openAdd(done) {
  const kind = sel(KINDS, 'RESORT'); const name = inp({ maxlength: 200 }); const place = inp({ maxlength: 200, placeholder: 'For example: Sajek' }); const phone = inp({ maxlength: 60 });
  const m = modal({ title: 'Add a vendor', body: [h('div', { class: 'form-grid' }, field('Kind', kind), field('Name', name), field('Place', place), field('Phone', phone))],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Add vendor', { kind: 'primary', onClick: async () => {
      if (!name.value.trim() || !place.value.trim()) throw new Error('Enter the name and the place.');
      const v = await post('/vendors', { category: kind.value, name: name.value.trim(), location: place.value.trim(), phone: phone.value.trim() || null });
      toast('Vendor added. Now add its rates.', 'ok'); m.close(); done(v.id);
    } })] });
}

async function manage() {
  const canWrite = perms.can('vendors:write');
  const root = h('div'); const holder = h('div');
  const q = inp({ type: 'search', placeholder: 'Search name, phone or place', 'aria-label': 'Search vendors' });
  const place = sel([['', 'All places']], ''); const kind = sel([['', 'All kinds'], ...KINDS], '');
  async function loadPlaces() {
    const cur = place.value; const places = await get('/vendors/locations');
    place.replaceChildren(h('option', { value: '' }, 'All places'), ...places.map((p) => h('option', { value: p }, raw(p)))); place.value = places.includes(cur) ? cur : '';
  }
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const page = await get('/vendors', { q: q.value.trim() || undefined, category: kind.value || undefined, location: place.value || undefined, limit: 200 });
    holder.replaceChildren(
      table([
        { label: 'Vendor', render: (v) => h('div', {}, h('b', {}, raw(v.name)), h('div', { class: 'muted' }, raw(v.phone || ''))) },
        { label: 'Kind', render: (v) => kindName(v.category) }, { label: 'Place', render: (v) => raw(v.location) },
        { label: 'Rates', class: 'num', render: (v) => v.rate_count },
        { label: 'Status', render: (v) => (v.is_active ? null : badge('DRAFT', 'Switched off')) },
      ], page.items, { onRowClick: (v) => openVendor(v.id, canWrite, () => { loadPlaces().catch(() => {}); load().catch(reportError); }), empty: 'No vendors match. Add the resorts, guides and drivers you work with, place by place.' }));
  }
  const again = () => load().catch(reportError);
  q.addEventListener('input', debounce(again, 300)); [place, kind].forEach((s) => s.addEventListener('change', again));
  root.append(h('div', { class: 'toolbar' }, h('div', { class: 'field', style: { minWidth: '220px' } }, h('span', { class: 'field-label' }, 'Search'), q), field('Place', place), field('Kind', kind),
    canWrite ? h('div', { style: { marginLeft: 'auto' } }, btn('Add vendor', { kind: 'primary', icon: 'plus', onClick: () => openAdd((id) => { loadPlaces().catch(() => {}); load().catch(reportError); openVendor(id, true, () => { loadPlaces().catch(() => {}); load().catch(reportError); }); }) })) : null), holder);
  await loadPlaces(); await load();
  return root;
}

export function render() {
  return h('div', {}, pageHead('Vendors and rates', 'Everyone you buy from, place by place, with the price each one charges. The budget calculator uses these rates.'), withDocs('vendors', manage));
}

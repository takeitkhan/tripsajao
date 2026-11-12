// Reusable editors: amenities with custom icons, media lists, key/value rows.
import { h, icon, inp, sel, btn, facilityIcon, refreshIcons, debounce } from './ui.js';
import { openPicker, thumb } from './media.js';

const ICON_HINT = {
  lucide: 'Icon name, e.g. wind',
  svg: 'https://example.com/icon.svg',
  fontawesome: 'fa-solid fa-wind',
  class: 'your-icon-class',
};
const removeBtn = (onclick) => h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Remove row', onclick }, icon('trash-2'));

/** Amenity editor: each row is {name, icon, type}. Presets add common ones with one click. */
export function facilityEditor(initial = [], presets = []) {
  const list = h('div');
  const entries = [];
  const chips = h('div', { class: 'chips' });

  function addRow(f = { name: '', icon: '', type: 'lucide' }) {
    const prev = h('span', { class: 'prev' });
    const name = inp({ value: f.name, placeholder: 'Name, e.g. AC', maxlength: 60, 'aria-label': 'Amenity name' });
    const type = sel([['lucide', 'Lucide'], ['svg', 'SVG URL'], ['fontawesome', 'Font Awesome'], ['class', 'CSS class']], f.type || 'lucide', { 'aria-label': 'Icon type' });
    const icn = inp({ value: f.icon, placeholder: ICON_HINT[f.type || 'lucide'], 'aria-label': 'Icon value', maxlength: 300 });
    const entry = { get: () => ({ name: name.value.trim(), icon: icn.value.trim(), type: type.value, ...(f.category ? { category: f.category } : {}) }) };
    const row = h('div', { class: 'fac-row' }, prev, name, type, icn,
      removeBtn(() => { row.remove(); entries.splice(entries.indexOf(entry), 1); drawChips(); }));
    const drawPrev = () => { const cur = entry.get(); prev.replaceChildren(cur.icon ? facilityIcon(cur) : ''); refreshIcons(); };
    type.addEventListener('change', () => { icn.placeholder = ICON_HINT[type.value]; drawPrev(); });
    icn.addEventListener('input', debounce(drawPrev, 300));
    name.addEventListener('input', debounce(drawChips, 200));
    entries.push(entry); list.append(row); drawPrev();
  }
  function drawChips() {
    const have = new Set(entries.map((e) => e.get().name.toLowerCase()));
    chips.replaceChildren(...presets.filter((p) => !have.has(p.name.toLowerCase())).map((p) =>
      h('button', { class: 'chip', type: 'button', onclick: () => { addRow(p); drawChips(); } }, facilityIcon(p), '+ ' + p.name)));
    refreshIcons();
  }
  initial.forEach(addRow); drawChips();

  const el = h('div', {}, list,
    h('div', { class: 'row' }, btn('Add amenity', { kind: 'sm', icon: 'plus', onClick: () => { addRow(); } })),
    presets.length ? h('div', { class: 'hint', style: { margin: '12px 0 6px' } }, 'Quick add') : null, chips);
  return {
    el,
    get() {
      const out = [];
      for (const e of entries) {
        const v = e.get();
        if (!v.name && !v.icon) continue;
        if (!v.name || !v.icon) throw new Error('Each amenity needs a name and an icon.');
        out.push(v);
      }
      return out;
    },
  };
}

/** Photos and videos for a property, unit or gallery: thumbnails you can reorder, with captions.
 *  "Add from library" opens the picker; "Add by link" is for a picture or video that lives elsewhere. */
export function mediaEditor(initial = []) {
  let items = initial.map((m) => ({ ...m }));
  const grid = h('div', { class: 'media-edit' });
  const tool = (ic, label, onClick, disabled) => h('button', { class: 'icon-btn', type: 'button', 'aria-label': label, title: label, disabled, onclick: onClick }, icon(ic));
  const move = (i, d) => { const [x] = items.splice(i, 1); items.splice(i + d, 0, x); render(); };

  function card(m, i) {
    const cap = inp({ value: m.caption || '', placeholder: 'Caption (optional)', maxlength: 200, 'aria-label': `Caption for item ${i + 1}` });
    cap.addEventListener('input', () => { m.caption = cap.value; });
    let link = null;
    if (!m.asset_id) {                                   // typed-in address: let people fix it
      const url = inp({ value: m.url || '', placeholder: 'https://...', 'aria-label': `Address for item ${i + 1}` });
      const type = sel([['photo', 'Photo'], ['video', 'Video']], m.type || 'photo', { 'aria-label': 'Type' });
      url.addEventListener('input', () => { m.url = url.value; });
      url.addEventListener('change', () => render());
      type.addEventListener('change', () => { m.type = type.value; render(); });
      link = h('div', { class: 'edit-link' }, type, url);
    }
    return h('div', { class: 'edit-card' }, i === 0 ? h('span', { class: 'cover-tag' }, 'First') : null, thumb({ ...m, type: m.type || 'photo' }), link, cap,
      h('div', { class: 'edit-tools' },
        tool('arrow-left', 'Move earlier', () => move(i, -1), i === 0), tool('arrow-right', 'Move later', () => move(i, 1), i === items.length - 1),
        tool('trash-2', 'Remove', () => { items.splice(i, 1); render(); })));
  }
  function render() {
    grid.replaceChildren(...items.map(card));
    grid.hidden = !items.length;
    refreshIcons();
  }
  render();
  const fromAsset = (a) => ({ type: a.kind === 'VIDEO' ? 'video' : 'photo', url: a.url, ...(a.thumbnail_url ? { thumbnail_url: a.thumbnail_url } : {}),
    asset_id: a.id, ...(a.alt_text ? { alt: a.alt_text } : {}), caption: '' });
  return {
    el: h('div', { class: 'stack-sm' }, grid,
      h('div', { class: 'row' },
        btn('Add from library', { kind: 'sm primary', icon: 'images', onClick: async () => {
          const picked = await openPicker({ multiple: true });
          if (picked?.length) { items.push(...picked.map(fromAsset)); render(); }
        } }),
        btn('Add by link', { kind: 'sm', icon: 'link', onClick: () => { items.push({ type: 'photo', url: '', caption: '' }); render(); } }),
        h('span', { class: 'hint' }, 'The first item is shown first on your website.'))),
    get() {
      return items.filter((m) => (m.url || '').trim()).map((m) => {
        const out = { type: m.type || 'photo', url: m.url.trim() };
        if ((m.caption || '').trim()) out.caption = m.caption.trim();
        if (m.asset_id) { out.asset_id = m.asset_id; if (m.thumbnail_url) out.thumbnail_url = m.thumbnail_url; if (m.alt) out.alt = m.alt; }
        return out;
      });
    },
  };
}

/** Simple name -> value rows (social links). */
export function kvEditor(initial = {}, keyHint = 'Name', valueHint = 'https://...') {
  const list = h('div');
  const rows = [];
  function addRow(k = '', v = '') {
    const key = inp({ value: k, placeholder: keyHint, 'aria-label': keyHint });
    const val = inp({ value: v, placeholder: valueHint, 'aria-label': valueHint });
    const entry = { get: () => [key.value.trim(), val.value.trim()] };
    const row = h('div', { class: 'kv-row' }, key, val, removeBtn(() => { row.remove(); rows.splice(rows.indexOf(entry), 1); }));
    rows.push(entry); list.append(row);
  }
  Object.entries(initial).forEach(([k, v]) => addRow(k, v));
  return {
    el: h('div', {}, list, btn('Add link', { kind: 'sm', icon: 'plus', onClick: () => { addRow(); refreshIcons(); } })),
    get() { return Object.fromEntries(rows.map((r) => r.get()).filter(([k, v]) => k && v)); },
  };
}

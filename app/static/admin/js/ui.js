// Small DOM toolkit. Nothing here uses innerHTML: every value goes through textContent / attributes,
// so guest names, notes and CMS text can never inject markup.
import { t, num, locale } from './i18n.js';
const TEXT_ATTRS = new Set(['placeholder', 'title', 'aria-label', 'alt']);
const PROPS = new Set(['checked', 'disabled', 'selected', 'readOnly', 'multiple', 'required', 'open', 'hidden']);

// text that is data (names, emails, tags) and must never be translated
export const raw = (s) => document.createTextNode(String(s ?? ''));

function add(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(typeof k === 'number' ? num(String(k)) : t(String(k))));
  }
}

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  let value;
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') { for (const [p, x] of Object.entries(v)) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; } }
    else if (k === 'value') value = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (PROPS.has(k)) el[k] = true;
    else el.setAttribute(k, v === true ? '' : TEXT_ATTRS.has(k) ? t(v) : v);
  }
  add(el, kids);
  if (value !== undefined) el.value = value; // after children, so <select> options exist
  return el;
}

export function svg(tag, attrs, ...kids) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else el.setAttribute(k, v);
  }
  add(el, kids);
  return el;
}

// ---------- icons ----------
export const icon = (name) => h('i', { 'data-lucide': name, class: 'ic', 'aria-hidden': 'true' });
export function refreshIcons() { try { window.lucide?.createIcons(); } catch { /* icons are optional */ } }

export function facilityIcon(f) {
  if (f.type === 'svg') return h('img', { class: 'fac-img', src: f.icon, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
  if (f.type === 'lucide') return icon(f.icon);
  return h('i', { class: f.icon, 'aria-hidden': 'true' });
}
export const facilityChip = (f) => h('span', { class: 'chip' }, facilityIcon(f), f.name);

// ---------- feedback ----------
export function toast(msg, kind = '') {
  const box = document.getElementById('toasts') || document.body;
  const el = h('div', { class: 'toast ' + kind, role: 'status' }, msg);
  box.append(el);
  setTimeout(() => el.remove(), kind === 'error' ? 7000 : 3500);
}
export function reportError(err) { console.error(err); toast(err?.message || 'Something went wrong', 'error'); }

export const spinner = () => h('div', { class: 'spinner', role: 'progressbar', 'aria-label': 'Loading' });
export const emptyState = (msg, action) => h('div', { class: 'empty' }, h('div', {}, msg), action || null);
export function errorBox(err) {
  return h('div', { class: 'callout bad' }, h('b', {}, 'Could not load this page. '), err?.message || String(err));
}

// ---------- buttons & forms ----------
export function btn(label, { kind = '', icon: ic, onClick, type = 'button', title } = {}) {
  const b = h('button', { class: 'btn ' + kind, type, title }, ic ? icon(ic) : null, label);
  if (onClick) {
    b.addEventListener('click', async (e) => {
      if (b.disabled) return;
      b.disabled = true; b.classList.add('busy');
      try { await onClick(e, b); } catch (err) { reportError(err); } finally { b.disabled = false; b.classList.remove('busy'); }
    });
  }
  return b;
}
export const field = (label, control, hint) =>
  h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control, hint ? h('span', { class: 'hint' }, hint) : null);
/** Like field(), for controls with several buttons inside (a <label> would forward stray clicks to the first button). */
export const fieldBox = (label, control, hint) =>
  h('div', { class: 'field' }, h('span', { class: 'field-label' }, label), control, hint ? h('span', { class: 'hint' }, hint) : null);
export const inp = (attrs = {}) => h('input', { class: 'input', type: 'text', ...attrs });
export const area = (attrs = {}) => h('textarea', { class: 'input', rows: 4, ...attrs });
export const sel = (options, value, attrs = {}) =>
  h('select', { class: 'input', value, ...attrs }, options.map((o) => (Array.isArray(o) ? h('option', { value: o[0] }, o[1]) : h('option', { value: o }, o))));
export const check = (label, checked, attrs = {}) =>
  h('label', { class: 'check' }, h('input', { type: 'checkbox', checked, ...attrs }), label);

export function pageHead(title, sub, ...actions) {
  return h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, title), sub ? h('div', { class: 'sub' }, sub) : null),
    h('div', { class: 'row' }, actions));
}

// ---------- modal ----------
export function modal({ title, body, actions = [], wide = false, onClose }) {
  const prev = document.activeElement;
  const bodyEl = h('div', { class: 'modal-body' }, body);
  const footer = h('div', { class: 'modal-foot' }, actions);
  let back;
  // only the top-most dialog reacts, so Escape inside the media picker does not also close the form beneath it
  const onKey = (e) => { if (e.key === 'Escape' && [...document.querySelectorAll('.backdrop')].pop() === back) close(); };
  function close() {
    back.remove();
    document.removeEventListener('keydown', onKey);
    onClose?.();
    try { prev?.focus?.(); } catch { /* ignore */ }
  }
  const box = h('div', { class: 'modal' + (wide ? ' wide' : ''), role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('div', { class: 'modal-head' }, h('h2', {}, title), h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close', onclick: close }, icon('x'))),
    bodyEl, footer);
  back = h('div', { class: 'backdrop', onmousedown: (e) => { if (e.target === back) close(); } }, box);
  document.body.append(back);
  document.addEventListener('keydown', onKey);
  refreshIcons();
  box.querySelector('input:not([type=checkbox]):not([type=radio]),select,textarea')?.focus();
  return {
    close, body: bodyEl, footer,
    setBody(n) { bodyEl.replaceChildren(); add(bodyEl, [n]); refreshIcons(); },
    setActions(a) { footer.replaceChildren(); add(footer, [a]); refreshIcons(); },
  };
}

export function confirmDialog(message, { confirmText = 'Confirm', danger = false, title = 'Are you sure?' } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const m = modal({
      title, body: h('p', {}, message), onClose: () => finish(false),
      actions: [
        btn('Cancel', { onClick: () => m.close() }),
        btn(confirmText, { kind: danger ? 'danger' : 'primary', onClick: () => { finish(true); m.close(); } }),
      ],
    });
  });
}

// ---------- table, tabs, figures ----------
export function table(cols, rows, { onRowClick, empty = 'Nothing here yet.' } = {}) {
  if (!rows.length) return emptyState(empty);
  const open = (r, e) => { if (onRowClick && !e.target.closest('button,a,input,select')) onRowClick(r); };
  return h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, cols.map((c) => h('th', { class: c.class || '' }, c.label)))),
    h('tbody', {}, rows.map((r) => h('tr', {
      class: onRowClick ? 'click' : '', tabindex: onRowClick ? 0 : null,
      onclick: (e) => open(r, e), onkeydown: (e) => { if (e.key === 'Enter') open(r, e); },
    }, cols.map((c) => h('td', { class: c.class || '' }, c.render(r))))))));
}

export function tabs(items, { initial } = {}) {
  const bar = h('div', { class: 'tabs', role: 'tablist' });
  const panel = h('div', { class: 'tab-panel' });
  const btns = {};
  let seq = 0;
  let current = null;
  async function show(id) {
    current = id;
    const mine = ++seq;
    for (const k in btns) btns[k].setAttribute('aria-selected', String(k === id));
    panel.replaceChildren(spinner());
    try {
      const node = await items.find((i) => i.id === id).render();
      if (mine !== seq) return;
      panel.replaceChildren(node);
      refreshIcons();
    } catch (e) { if (mine === seq) panel.replaceChildren(errorBox(e)); }
  }
  for (const it of items) {
    btns[it.id] = h('button', { class: 'tab', role: 'tab', type: 'button', onclick: () => show(it.id) }, it.label);
    bar.append(btns[it.id]);
  }
  const root = h('div', {}, bar, panel);
  root.refresh = () => show(current);
  root.show = show;
  root.ready = show(initial || items[0].id);
  return root;
}

export const figures = (items) => h('div', { class: 'figures' }, items.map((f) =>
  h('div', { class: 'fig' }, h('b', {}, f.value), h('span', {}, f.color ? h('i', { class: 'dot', style: { '--st': f.color } }) : null, f.label))));

// ---------- badges ----------
const KIND = {
  CONFIRMED: 'ok', PAID: 'ok', PUBLISHED: 'ok', AVAILABLE: 'ok', HOLD: 'warn', PENDING: 'warn', ON_HOLD: 'warn',
  APPROVED: 'info', PAYMENT_SUBMITTED: 'info', EXPIRED: '', CANCELLED: 'bad', REJECTED: 'bad', BOOKED: 'bad', DRAFT: '', MAINTENANCE: '',
};
export const humanize = (s) => String(s ?? '').toLowerCase().replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
export const badge = (status, label) => h('span', { class: 'badge ' + (KIND[status] ?? '') }, label ?? humanize(status));

// ---------- formatting ----------
export function money(v, cur = 'USD') {
  const n = Number(v);
  if (!Number.isFinite(n)) return '-';
  try { return new Intl.NumberFormat(locale(), { style: 'currency', currency: cur }).format(n); } catch { return `${cur} ${n.toFixed(2)}`; }
}
export const fmtDate = (d) => (d ? new Date(d.length === 10 ? d + 'T00:00:00' : d).toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: 'numeric' }) : '-');
export const fmtDateTime = (d) => (d ? new Date(d).toLocaleString(locale(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '-');
export const isoDate = (d) => { const x = new Date(d); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`; };
export const today = () => isoDate(new Date());
export const addDays = (iso, n) => { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n); return isoDate(d); };
export const nightsBetween = (a, b) => Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000);
export const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 100);
export const toLocalInput = (iso) => { if (!iso) return ''; const d = new Date(iso); return `${isoDate(d)}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
export const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

export async function copy(text) {
  try { await navigator.clipboard.writeText(text); } catch {
    const t = h('textarea', { value: text }); document.body.append(t); t.select(); document.execCommand('copy'); t.remove();
  }
}
export const copyBtn = (text, label = 'Copy', kind = 'ghost sm') =>
  btn(label, { kind, icon: 'copy', onClick: async () => { await copy(text); toast('Copied to clipboard'); } });

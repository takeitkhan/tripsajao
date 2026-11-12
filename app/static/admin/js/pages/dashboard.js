import { t } from '../i18n.js';
// Live board: resort building elevation / houseboat hull, with real-time status.
import { get, patch, streamEvents } from '../api.js';
import { lookups, invalidate } from '../data.js';
import {
  h, svg, btn, field, inp, sel, modal, badge, emptyState, pageHead, figures, facilityChip, today, addDays, fmtDate,
  fmtDateTime, money, humanize, debounce, reportError, refreshIcons, toast,
} from '../ui.js';
import { withDocs } from '../docs.js';
import { openBookingDetail, openNewBooking } from './bookings.js';

const STATUS_NAME = { AVAILABLE: 'Available', ON_HOLD: 'On hold', BOOKED: 'Booked', MAINTENANCE: 'Maintenance' };
let activeStream = null; // only one live stream at a time (switching tabs re-renders the board)
const sleep = (ms, signal) => new Promise((res) => { const t = setTimeout(res, ms); signal?.addEventListener('abort', () => { clearTimeout(t); res(); }); });

export function render(ctx) {
  return h('div', {}, pageHead('Live board', 'Every room or cabin and whether it is free for the dates you pick.'), withDocs('dashboard', () => manage(ctx)));
}

async function manage(ctx) {
  const props = (await get('/properties', { limit: 200 })).items.filter((p) => p.is_active);
  if (!props.length) return emptyState('No properties yet. Add a property and its rooms or cabins, and they appear here.', h('a', { class: 'btn primary', href: '#/properties' }, 'Add a property'));

  const saved = sessionStorage.getItem('kt.board.property');
  const prop = sel(props.map((p) => [p.id, p.name]), props.some((p) => p.id === saved) ? saved : props[0].id);
  const ci = inp({ type: 'date', value: today() });
  const co = inp({ type: 'date', value: addDays(today(), 1) });
  const live = h('span', { class: 'live', 'data-state': 'connecting' }, h('i'), h('span', {}, 'Connecting'));
  const board = h('div', { class: 'stack' });
  const setLive = (s) => { live.dataset.state = s; live.lastChild.textContent = t({ live: 'Live updates on', offline: 'Reconnecting...', connecting: 'Connecting' }[s]); };

  let lastLayout = null;
  async function load() {
    if (co.value <= ci.value) { toast('Check-out must be after check-in.', 'error'); return; }
    sessionStorage.setItem('kt.board.property', prop.value);
    const layout = await get(`/dashboard/visual/${prop.value}`, { check_in: ci.value, check_out: co.value });
    lastLayout = layout;
    draw(layout);
  }

  function draw(layout) {
    const s = layout.summary;
    const legend = h('div', { class: 'legend' }, layout.legend.map((l) => h('span', {}, h('i', { class: 'dot', style: { '--st': l.color } }), l.label)));
    board.replaceChildren(
      figures(layout.legend.map((l) => ({ value: s[l.status] ?? 0, label: l.label, color: l.color }))),
      layout.view === 'GRID' ? gridView(layout) : boatView(layout),
      legend);
    refreshIcons();
  }

  function gridView(layout) {
    const floors = [...layout.floors].sort((a, b) => b.floor - a.floor); // top floor first
    return h('div', { class: 'building' },
      h('div', { class: 'roof' }, layout.property_name),
      h('div', { class: 'floors' }, floors.map((f) => h('div', { class: 'floor' },
        h('div', { class: 'floor-label' }, f.label),
        h('div', { class: 'floor-grid', style: { '--cols': Math.max(f.columns, 1) } }, f.cells.map((c) =>
          h('button', {
            class: 'cell', type: 'button', 'data-status': c.status, style: { '--st': c.color, gridRow: `${c.row + 1} / span ${c.row_span}`, gridColumn: `${c.col + 1} / span ${c.col_span}` },
            'aria-label': `${c.name}, ${STATUS_NAME[c.status]}`, onclick: () => openUnit(c).catch(reportError),
          }, h('b', {}, c.name), h('small', {}, humanize(c.unit_type)), h('span', { class: 'st' }, STATUS_NAME[c.status]))))))),
      h('div', { class: 'ground' }));
  }

  function boatView(layout) {
    const root = svg('svg', { class: 'hull', viewBox: layout.outline.view_box, role: 'img', 'aria-label': `${layout.property_name} cabin layout` });
    // waterline
    root.append(svg('path', { d: 'M0 108 q12 -6 24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0', fill: 'none', stroke: 'currentColor', 'stroke-opacity': '.25', 'stroke-width': '1.5' }));
    root.append(svg('path', { d: layout.outline.hull_path, fill: 'none', stroke: 'currentColor', 'stroke-width': '3', 'stroke-linejoin': 'round' }));
    for (const c of layout.cabins) {
      root.append(svg('g', { class: 'cabin', tabindex: 0, role: 'button', 'aria-label': `${c.name}, ${STATUS_NAME[c.status]}`, onclick: () => openUnit({ ...c, unit_type: 'CABIN' }).catch(reportError), onkeydown: (e) => { if (e.key === 'Enter') openUnit({ ...c, unit_type: 'CABIN' }).catch(reportError); } },
        svg('title', {}, `${c.name}: ${STATUS_NAME[c.status]}`),
        svg('rect', { x: c.x, y: c.y, width: c.w, height: c.h, rx: 2, fill: c.color, 'fill-opacity': c.status === 'AVAILABLE' ? '.2' : '.32', stroke: c.color }),
        svg('text', { x: c.x + c.w / 2, y: c.y + c.h / 2 - 1, 'text-anchor': 'middle', 'font-size': '7.5', 'font-weight': '700' }, c.name.length > 12 ? c.name.slice(0, 11) + '…' : c.name),
        svg('text', { x: c.x + c.w / 2, y: c.y + c.h / 2 + 8, 'text-anchor': 'middle', 'font-size': '5.5', 'fill-opacity': '.8' }, STATUS_NAME[c.status])));
    }
    const wrap = h('div', { class: 'hull-wrap' }, root);
    if (layout.charter) {
      const ch = layout.charter;
      wrap.append(h('div', { class: 'charter' }, h('span', { class: 'muted' }, 'Whole-boat charter'), badge(ch.status, STATUS_NAME[ch.status]),
        ch.status === 'AVAILABLE' ? btn('Book the whole boat', { kind: 'sm', onClick: () => openNewBooking({ propertyId: layout.property_id, unitId: ch.unit_id, checkIn: ci.value, checkOut: co.value, onDone: load }) }) : null));
    }
    return wrap;
  }

  async function openUnit(cell) {
    const lk = await lookups();
    const unit = lk.units[cell.unit_id];
    const actions = [];
    const body = [h('div', { class: 'row' }, badge(cell.status, STATUS_NAME[cell.status]), h('span', { class: 'muted' }, `${fmtDate(ci.value)} to ${fmtDate(co.value)}`))];
    if (unit) {
      body.push(h('div', { class: 'muted' }, `${humanize(unit.type)}, sleeps ${unit.capacity}`));
      if (unit.facilities.length) body.push(h('div', { class: 'chips' }, unit.facilities.map(facilityChip)));
    }
    if (cell.booking_id) {
      const b = await get(`/bookings/${cell.booking_id}`);
      body.push(h('dl', { class: 'kv' },
        h('dt', {}, 'Booking'), h('dd', {}, b.booking_ref),
        h('dt', {}, 'Guest'), h('dd', {}, b.customer?.name || '-'),
        h('dt', {}, 'Stay'), h('dd', {}, `${fmtDate(b.check_in)} to ${fmtDate(b.check_out)}`),
        h('dt', {}, 'Paid'), h('dd', {}, `${money(b.paid_amount, b.currency)} of ${money(b.total_amount, b.currency)}`),
        b.status === 'HOLD' ? [h('dt', {}, 'Hold ends'), h('dd', {}, fmtDateTime(b.hold_expires_at))] : null));
      actions.push(btn('Open booking', { kind: 'primary', onClick: () => { m.close(); return openBookingDetail(cell.booking_id, load); } }));
    }
    if (cell.status === 'AVAILABLE') {
      actions.push(btn('Book this unit', { kind: 'primary', icon: 'plus', onClick: () => { m.close(); return openNewBooking({ propertyId: prop.value, unitId: cell.unit_id, checkIn: ci.value, checkOut: co.value, onDone: load }); } }));
      actions.push(btn('Mark under maintenance', { onClick: async () => { await patch(`/properties/units/${cell.unit_id}`, { status: 'MAINTENANCE' }); invalidate(); m.close(); toast('Marked under maintenance'); await load(); } }));
    }
    if (cell.status === 'MAINTENANCE') {
      actions.push(btn('Return to service', { kind: 'primary', onClick: async () => { await patch(`/properties/units/${cell.unit_id}`, { status: 'AVAILABLE' }); invalidate(); m.close(); toast('Back in service'); await load(); } }));
    }
    const m = modal({ title: cell.name, body, actions });
  }

  prop.addEventListener('change', () => load().catch(reportError));
  ci.addEventListener('change', () => { if (co.value <= ci.value) co.value = addDays(ci.value, 1); load().catch(reportError); });
  co.addEventListener('change', () => load().catch(reportError));
  const root = h('div', {},
    h('div', { class: 'toolbar' }, field('Property', prop), field('Check-in', ci), field('Check-out', co), btn('Refresh', { icon: 'refresh-cw', onClick: load }), h('div', { style: { marginLeft: 'auto' } }, live)),
    board);
  await load();

  // Live updates: reload whenever a hold, booking or release happens anywhere in this tenant.
  activeStream?.abort();
  const ac = new AbortController();
  activeStream = ac;
  ctx.onLeave(() => ac.abort());
  const schedule = debounce(() => { if (!ac.signal.aborted) load().catch(() => {}); }, 400);
  (async () => {
    while (!ac.signal.aborted) {
      try {
        await get('/auth/me'); // refreshes an expired token before reconnecting
        await streamEvents(() => schedule(), ac.signal, () => setLive('live'));
      } catch { /* fall through to retry */ }
      if (ac.signal.aborted) return;
      setLive('offline');
      await sleep(5000, ac.signal);
    }
  })();
  return root;
}

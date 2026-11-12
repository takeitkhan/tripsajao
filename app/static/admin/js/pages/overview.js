import { locale } from '../i18n.js';
// Overview: the owner's quick reports - money, occupancy, arrivals, partners.
import { get } from '../api.js';
import { h, pageHead, money, fmtDate, humanize } from '../ui.js';
import { barChart, lineChart, hbars, panel } from '../charts.js';
import { withDocs } from '../docs.js';

const dayLabel = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString(locale(), { day: 'numeric', month: 'short' });

export function render() {
  return h('div', {}, pageHead('Overview', 'How the business is doing, in numbers you can act on.'), withDocs('reports', () => body()));
}

async function body() {
  const box = h('div', {});
  const saved = Number(sessionStorage.getItem('kt.ov.days')) || 30;
  const range = h('div', { class: 'seg-row', role: 'group', 'aria-label': 'Period' });
  async function load(days) {
    sessionStorage.setItem('kt.ov.days', String(days));
    for (const b of range.children) b.setAttribute('aria-pressed', String(Number(b.dataset.d) === days));
    box.replaceChildren(draw(await get('/reports/overview', { days })));
  }
  for (const d of [7, 30, 90]) range.append(h('button', { class: 'pill', type: 'button', 'data-d': d, onclick: () => load(d).catch((e) => box.replaceChildren(h('div', { class: 'callout bad' }, e.message))) }, `Last ${d} days`));
  await load(saved);
  return h('div', {}, h('div', { class: 'toolbar' }, range), box);
}

function draw(r) {
  const m = (v) => money(v, r.currency);
  const k = r.kpis;
  const tiles = h('div', { class: 'tile-row' },
    tile(k.bookings, `Bookings, last ${r.days} days`),
    tile(m(k.booked_value), 'Booked value'),
    tile(m(k.collected), 'Money collected'),
    tile(m(k.outstanding), 'Still to collect', k.outstanding > 0 && Number(k.outstanding) > 0),
    tile(`${k.occupancy_now_percent}%`, `Occupied today (${k.occupied_now} of ${k.total_units})`),
    tile(k.arrivals_7d, 'Arriving in 7 days'),
    tile(k.active_holds, 'Holds waiting for payment'),
    tile(k.cancelled, `Cancelled, last ${r.days} days`));
  const daily = lineChart(r.daily.map((d) => ({ label: dayLabel(d.day), value: Number(d.value), tip: `${dayLabel(d.day)}: ${d.bookings} booking${d.bookings === 1 ? '' : 's'}, ${m(d.value)}` })), { label: `Value of bookings made per day, last ${r.days} days` });
  const occ = barChart(r.occupancy_next_14_days.map((d) => ({ label: dayLabel(d.day), value: d.percent, tip: `${dayLabel(d.day)}: ${d.booked} of ${d.total} booked (${d.percent}%)` })), { fmt: (v) => `${Math.round(v)}%`, label: 'Occupancy for the next 14 days' });
  const sc = r.by_source;
  const total = sc.direct.bookings + sc.partners.bookings;
  const arrivals = r.arrivals.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, ['Arrives', 'Guest', 'Where', 'Nights', 'Balance', 'Reference'].map((c) => h('th', {}, c)))),
    h('tbody', {}, r.arrivals.map((a) => h('tr', {}, h('td', {}, fmtDate(a.check_in)), h('td', {}, a.guest || '-'), h('td', {}, `${a.unit} - ${a.property}`), h('td', {}, a.nights), h('td', {}, Number(a.balance) > 0 ? m(a.balance) : 'Paid'), h('td', {}, h('code', {}, a.booking_ref || '-'))))))) : h('div', { class: 'muted' }, 'No arrivals in the next 7 days.');
  return h('div', {}, tiles,
    h('div', { class: 'panels' },
      panel('Value of bookings made per day', daily, `last ${r.days} days`),
      panel('Occupancy, next 14 days', occ, 'share of rooms and cabins booked')),
    h('div', { class: 'panels' },
      panel('Most booked properties', hbars(r.by_property.map((p) => ({ label: p.name, value: p.bookings, text: `${p.bookings} booking${p.bookings === 1 ? '' : 's'}`, sub: m(p.value) })), { empty: 'No confirmed bookings in this period.' })),
      panel('Where bookings come from', hbars([
        { label: 'Direct', value: sc.direct.bookings, text: `${sc.direct.bookings} - ${m(sc.direct.value)}` },
        { label: 'Through partners', value: sc.partners.bookings, text: `${sc.partners.bookings} - ${m(sc.partners.value)}` }], { max: Math.max(total, 1) })),
      panel('Top partners', hbars(r.top_partners.map((p) => ({ label: p.name, value: Number(p.sales), text: m(p.sales), sub: `${p.bookings} booking${p.bookings === 1 ? '' : 's'}, commission ${m(p.commission)}` })), { empty: 'No partner sales in this period.' }))),
    panel('Arrivals in the next 7 days', arrivals));
}

const tile = (v, label, alert) => h('div', { class: 'tile' + (alert ? ' alert' : '') }, h('b', {}, v), h('span', {}, label));

import { locale } from './i18n.js';
// Dependency-free charts: inline SVG, one hue (the brand colour), thin marks, quiet grid.
// Every mark carries a <title> (hover tooltip + screen readers) and every chart has a text summary.
import { h, svg } from './ui.js';

const W = 640;
// Pick a tidy step (1, 2, 5 x 10^n) so the axis reads 0, 25, 50, 75, 100 and never 13.3.
const niceScale = (m, ticks = 4) => {
  if (m <= 0) return { max: ticks, step: 1 };
  const raw = m / ticks; const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((x) => x * p).find((x) => x >= raw);
  return { max: step * Math.ceil(m / step - 1e-9), step };
};
const compact = (n) => new Intl.NumberFormat(locale(), { notation: 'compact', maximumFractionDigits: 1 }).format(n);

function frame(H, top, fmt) {
  const { max, step } = niceScale(top); const ticks = Math.round(max / step);
  const L = 44, R = 8, T = 8, B = 24;
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const parts = [];
  for (let i = 0; i <= ticks; i++) {
    const v = step * i;
    parts.push(svg('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: 'var(--line)', 'stroke-width': i ? 1 : 1.5 }));
    parts.push(svg('text', { x: L - 6, y: y(v) + 4, 'text-anchor': 'end', 'font-size': 11, fill: 'var(--muted)' }, fmt(v)));
  }
  return { L, R, T, B, y, parts, plotW: W - L - R, max };
}

function wrap(H, children, label) {
  return h('figure', { class: 'chart' }, svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': label, class: 'chart-svg' }, children));
}

/** data: [{label, value, tip?}] */
export function barChart(data, { height = 200, fmt = compact, label = 'Bar chart', every } = {}) {
  const f = frame(height, Math.max(0, ...data.map((d) => d.value)), fmt);
  const slot = f.plotW / Math.max(1, data.length);
  const bw = Math.min(26, slot * 0.6);
  const step = every || Math.max(1, Math.ceil(data.length / 8));
  const kids = [...f.parts];
  data.forEach((d, i) => {
    const x = f.L + slot * i + (slot - bw) / 2;
    const yy = f.y(d.value);
    const base = f.y(0);
    const hh = Math.max(d.value > 0 ? 2 : 0, base - yy);
    kids.push(svg('rect', { x, y: base - hh, width: bw, height: hh, rx: 3, fill: 'var(--brand)' }, svg('title', {}, d.tip || `${d.label}: ${fmt(d.value)}`)));
    if (i % step === 0) kids.push(svg('text', { x: x + bw / 2, y: height - 6, 'text-anchor': 'middle', 'font-size': 11, fill: 'var(--muted)' }, d.label));
  });
  return wrap(height, kids, label);
}

/** data: [{label, value, tip?}] drawn as a line with a faint area. */
export function lineChart(data, { height = 200, fmt = compact, label = 'Line chart' } = {}) {
  const f = frame(height, Math.max(0, ...data.map((d) => d.value)), fmt);
  const n = Math.max(1, data.length - 1);
  const px = (i) => f.L + (f.plotW * i) / n;
  const pts = data.map((d, i) => [px(i), f.y(d.value)]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('');
  const kids = [...f.parts];
  if (pts.length > 1) {
    kids.push(svg('path', { d: `${line}L${pts.at(-1)[0]} ${f.y(0)}L${pts[0][0]} ${f.y(0)}Z`, fill: 'var(--brand)', opacity: 0.12 }));
    kids.push(svg('path', { d: line, fill: 'none', stroke: 'var(--brand)', 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  }
  const step = Math.max(1, Math.ceil(data.length / 7));
  data.forEach((d, i) => {
    if (i % step === 0) kids.push(svg('text', { x: px(i), y: height - 6, 'text-anchor': i === 0 ? 'start' : 'middle', 'font-size': 11, fill: 'var(--muted)' }, d.label));
    kids.push(svg('circle', { cx: px(i), cy: pts[i][1], r: 9, fill: 'transparent', class: 'hit' }, svg('title', {}, d.tip || `${d.label}: ${fmt(d.value)}`)));
  });
  return wrap(height, kids, label);
}

/** Horizontal bars as plain HTML: rows [{label, value, text?, sub?}]. */
export function hbars(rows, { max, empty = 'Nothing to show yet.' } = {}) {
  if (!rows.length) return h('div', { class: 'muted' }, empty);
  const m = max || Math.max(...rows.map((r) => r.value), 1);
  return h('div', { class: 'hbars' }, rows.map((r) => h('div', { class: 'hb' },
    h('div', { class: 'hb-top' }, h('span', { class: 'hb-label' }, r.label), h('span', { class: 'hb-val' }, r.text ?? String(r.value))),
    h('div', { class: 'bar', role: 'img', 'aria-label': `${r.label}: ${r.text ?? r.value}` }, h('i', { style: { width: `${Math.max(r.value > 0 ? 2 : 0, (r.value / m) * 100)}%` } })),
    r.sub ? h('div', { class: 'hint' }, r.sub) : null)));
}

export const panel = (title, body, sub) => h('section', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h3', {}, title), sub ? h('span', { class: 'muted' }, sub) : null), body);

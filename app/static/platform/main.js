// Super admin portal shell: sign-in, navigation, hash router.
import { auth, get, login, logout, onAuthLost } from './api.js';
import { h, svg, icon, btn, field, inp, refreshIcons, spinner, errorBox } from '/admin/js/ui.js';
import * as pages from './pages.js';

const app = document.getElementById('app');
let me = null; let view = null; let navEl = null; let seq = 0;

const ROUTES = [
  { path: '/overview', label: 'Overview', icon: 'chart-no-axes-combined', render: pages.overview },
  { path: '/tenants', label: 'Businesses', icon: 'building', render: pages.tenants },
  { path: '/tenants/:id', nav: '/tenants', render: pages.tenantDetail },
  { path: '/late-commissions', label: 'Late commissions', icon: 'hand-coins', render: pages.overdueCommissions },
  { path: '/messages', label: 'Website messages', icon: 'mail', render: pages.messages },
  { path: '/support', label: 'Support sessions', icon: 'life-buoy', render: pages.supportSessions },
  { path: '/audit', label: 'Audit log', icon: 'scroll-text', render: pages.auditLog },
];
const match = (pattern, path) => {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:[^/]+/g, (m) => { keys.push(m.slice(1)); return '([^/]+)'; }) + '$');
  const m = re.exec(path);
  return m ? Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])])) : null;
};

async function renderRoute() {
  if (!me || !view) return;
  const path = location.hash.slice(1).split('?')[0] || '/overview';
  let params = null;
  const route = ROUTES.find((r) => (params = match(r.path, path)));
  if (!route) { location.hash = '#/overview'; return; }
  for (const a of navEl.querySelectorAll('a')) a.getAttribute('href') === '#' + (route.nav || route.path) ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current');
  const mine = ++seq;
  view.replaceChildren(spinner());
  try {
    const node = await route.render({ params, go: (p) => { location.hash = '#' + p; } });
    if (mine !== seq) return;
    view.replaceChildren(node); refreshIcons();
    document.title = (route.label ? route.label + ' - ' : '') + 'Trip Sajao platform';
  } catch (e) { if (mine === seq) view.replaceChildren(errorBox(e)); }
}

const mark = () => svg('svg', { viewBox: '0 0 32 32', 'aria-hidden': 'true' },
  svg('path', { d: 'M3 18h26l-4 8H7z', fill: 'currentColor' }),
  svg('path', { d: 'M9 18v-6h14v6M13 12V8h6v4', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linejoin': 'round' }));
const brand = () => h('div', { class: 'brand' }, mark(), 'Trip Sajao');

function shell() {
  navEl = h('nav', { class: 'nav', 'aria-label': 'Main' }, ROUTES.filter((r) => r.label).map((r) => h('a', { href: '#' + r.path }, icon(r.icon), r.label)));
  view = h('main', { class: 'main', id: 'view', tabindex: '-1' });
  app.replaceChildren(h('div', { class: 'shell' }, h('aside', { class: 'rail' }, h('div', {}, brand(), h('div', { class: 'muted', style: { padding: '2px 8px 0 50px', fontSize: '13px' } }, 'Platform admin')), navEl,
    h('div', { class: 'rail-foot' }, h('span', {}, me.email), btn('Sign out', { kind: 'sm', icon: 'log-out', onClick: async () => { await logout(); showLogin(); } }))), view));
  refreshIcons();
}

function showLogin(message) {
  me = null; view = null;
  const email = inp({ type: 'email', autocomplete: 'username', required: true });
  const pass = inp({ type: 'password', autocomplete: 'current-password', required: true });
  const err = h('div', { class: 'callout bad', hidden: !message, role: 'alert' }, message || '');
  const submit = btn('Sign in', { kind: 'primary', type: 'submit' });
  const form = h('form', { onsubmit: async (e) => {
    e.preventDefault(); err.hidden = true; submit.disabled = true;
    try { await login(email.value, pass.value); await start(); } catch (ex) {
      err.textContent = ex.status === 429 ? 'Too many attempts. Wait a few minutes and try again.' : ex.status === 401 ? 'That email or password is not right.' : ex.message; err.hidden = false;
    } finally { submit.disabled = false; }
  } }, field('Email', email), field('Password', pass), err, submit);
  app.replaceChildren(h('div', { class: 'login' }, h('div', { class: 'login-box' }, brand(), h('div', {}, h('h1', {}, 'Platform sign-in'), h('p', { class: 'muted', style: { margin: '6px 0 0' } }, 'For the people who run this service. Business owners sign in at /admin/.')), form)));
  email.focus();
}

async function start() {
  try { me = await get('/auth/me'); } catch (e) { showLogin(e.status === 401 ? undefined : e.message); return; }
  shell(); await renderRoute();
}
onAuthLost(() => showLogin('Your session ended. Sign in again.'));
window.addEventListener('hashchange', () => renderRoute());
if (auth.tokens) start(); else showLogin();

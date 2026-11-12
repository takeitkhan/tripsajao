import { t, initLang, LANGS, getLang, setLang } from './i18n.js';
// App shell: sign-in, side navigation, hash router.
import { auth, api, get, post, login, logout, onAuthLost } from './api.js';
import { h, raw, svg, icon, btn, field, inp, modal, refreshIcons, spinner, errorBox, toast, reportError, fmtDateTime } from './ui.js';
import { invalidate, perms } from './data.js';
import * as overview from './pages/overview.js';
import * as dashboard from './pages/dashboard.js';
import * as bookings from './pages/bookings.js';
import * as properties from './pages/properties.js';
import * as pricing from './pages/pricing.js';
import * as partners from './pages/partners.js';
import * as payouts from './pages/payouts.js';
import * as cms from './pages/cms.js';
import * as media from './pages/media.js';
import * as resellers from './pages/resellers.js';
import * as partnerrooms from './pages/partnerrooms.js';
import * as commissions from './pages/commissions.js';
import * as access from './pages/access.js';
import * as customers from './pages/customers.js';
import * as events from './pages/events.js';
import * as eventbookings from './pages/eventbookings.js';
import * as business from './pages/business.js';
import * as vendors from './pages/vendors.js';
import * as budgets from './pages/budgets.js';
import * as team from './pages/team.js';
import * as portal from './pages/portal.js';

const app = document.getElementById('app');
let me = null;
let view = null;
let cleanups = [];
let routeSeq = 0;
let navEl = null;

const can = (scope) => !!me && (me.scopes.includes('*') || me.scopes.includes(scope));
perms.can = can;

const STAFF_ROUTES = [
  { path: '/overview', label: 'Overview', icon: 'chart-no-axes-combined', scope: 'reports:read', render: overview.render },
  { path: '/dashboard', label: 'Live board', icon: 'layout-grid', scope: 'dashboard:read', render: dashboard.render },
  { path: '/customers', label: 'Customers', icon: 'contact-round', scope: 'customers:read', render: customers.render },
  { path: '/properties', label: 'Properties', icon: 'building-2', group: 'Properties', groupIcon: 'building-2', scope: 'properties:read', render: properties.renderList },
  { path: '/bookings', label: 'Bookings', icon: 'calendar-check', group: 'Properties', groupIcon: 'building-2', scope: 'bookings:read', render: bookings.render },
  { path: '/properties/:id', nav: '/properties', scope: 'properties:read', render: properties.renderDetail },
  { path: '/events', label: 'Events', icon: 'calendar-range', group: 'Events', groupIcon: 'calendar-range', scope: 'events:read', render: events.render },
  { path: '/event-bookings', label: 'Event bookings', icon: 'ticket', group: 'Events', groupIcon: 'calendar-range', scope: 'event_bookings:read', render: eventbookings.render, badge: () => me?.channel?.event_waiting || 0 },
  { path: '/vendors', label: 'Vendors', icon: 'store', scope: 'vendors:read', render: vendors.render },
  { path: '/budgets', label: 'Budgets', icon: 'calculator', scope: 'budgets:read', render: budgets.render },
  { path: '/budgets/:id', nav: '/budgets', scope: 'budgets:read', render: budgets.renderBuilder },
  { path: '/pricing', label: 'Pricing', icon: 'tag', scope: 'pricing:read', render: pricing.render },
  { path: '/partners', label: 'Partners', icon: 'handshake', scope: 'partners:read', render: partners.render },
  { path: '/payouts', label: 'Payouts', icon: 'banknote', scope: 'payouts:read', render: payouts.render },
  { path: '/media', label: 'Media', icon: 'images', scope: 'media:read', render: media.render },
  { path: '/resellers', label: 'Resellers', icon: 'share-2', scope: 'channel:read', render: resellers.render, badge: () => me?.channel?.waiting || 0 },
  { path: '/commissions', label: 'Commissions', icon: 'wallet', scope: 'channel:read', render: commissions.render, when: () => !!me?.channel?.has_agreements },
  { path: '/partner-rooms', label: 'Partner rooms', icon: 'door-open', scope: 'channel:read', render: partnerrooms.render, when: () => !!me?.channel?.sells_for_others },
  ...cms.SECTION_LIST.map((x) => ({ path: `/content/${x.id}`, label: x.label, group: 'Website content', groupIcon: 'newspaper', icon: 'file-text', scope: 'cms:read', render: (ctx) => cms.render({ ...ctx, params: { ...ctx.params, section: x.id } }) })),
  { path: '/content', scope: 'cms:read', render: () => { location.hash = '#/content/company'; return h('div'); } },
  { path: '/business', label: 'Business profile', icon: 'badge-check', scope: 'business:read', render: business.render },
  { path: '/access', label: 'API access', icon: 'key-round', scope: 'api_keys:manage', render: access.render },
  { path: '/team', label: 'Team', icon: 'users', scope: 'staff:manage', render: team.render },
];
const PARTNER_ROUTES = [{ path: '/portal', label: 'My dashboard', icon: 'layout-dashboard', render: portal.render }];

const routes = () => (me?.kind === 'partner' ? PARTNER_ROUTES : STAFF_ROUTES.filter((r) => can(r.scope) && (!r.when || r.when())));

function match(pattern, path) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:[^/]+/g, (m) => { keys.push(m.slice(1)); return '([^/]+)'; }) + '$');
  const m = re.exec(path);
  return m ? Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])])) : null;
}

export async function renderRoute() {
  if (!me || !view) return;
  cleanups.splice(0).forEach((fn) => { try { fn(); } catch { /* ignore */ } });
  const list = routes();
  const path = location.hash.slice(1).split('?')[0] || list[0].path;
  let params = null;
  const route = list.find((r) => (params = match(r.path, path)));
  if (!route) { location.hash = '#' + list[0].path; return; }
  for (const a of navEl.querySelectorAll('a')) {
    if (a.getAttribute('href') === '#' + (route.nav || route.path)) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  for (const g of navEl.querySelectorAll('.nav-group')) if (g.querySelector('a[aria-current]')) g.querySelector('.nav-parent').setAttribute('aria-expanded', 'true');
  const mine = ++routeSeq;
  view.replaceChildren(spinner());
  const ctx = { me, can, params, onLeave: (fn) => cleanups.push(fn) };
  try {
    const node = await route.render(ctx);
    if (mine !== routeSeq) return;
    view.replaceChildren(node);
    refreshIcons();
    document.title = (route.label ? route.label + ' - ' : '') + 'Trip Sajao admin';
  } catch (e) {
    if (mine === routeSeq) view.replaceChildren(errorBox(e));
  }
}

export async function go(path) {
  const target = '#' + path;
  if (location.hash === target) return renderRoute();
  location.hash = target;
  return renderRoute(); // hashchange also fires; the sequence guard keeps only the latest render
}

// ------------------------------------------------------------------ chrome
const brandMark = () => svg('svg', { viewBox: '0 0 32 32', 'aria-hidden': 'true' },
  svg('path', { d: 'M3 18h26l-4 8H7z', fill: 'currentColor' }),
  svg('path', { d: 'M9 18v-6h14v6M13 12V8h6v4', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linejoin': 'round' }),
  svg('path', { d: 'M2 29q3-2 6 0t6 0 6 0 6 0 6 0', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.6', 'stroke-linecap': 'round', opacity: '.5' }));
const brand = () => h('div', { class: 'brand' }, brandMark(), 'Trip Sajao');

function showShell() {
  const list = routes().filter((r) => r.label);
  const link = (r) => h('a', { href: '#' + r.path }, icon(r.icon), r.label, r.badge?.() ? h('span', { class: 'nav-badge', 'aria-label': `${r.badge()} waiting` }, r.badge()) : null);
  const items = []; const groups = new Map();
  for (const r of list) {
    if (!r.group) { items.push(link(r)); continue; }
    let g = groups.get(r.group);
    if (!g) {
      const sub = h('div', { class: 'nav-sub' });
      const parent = h('button', { type: 'button', class: 'nav-parent', 'aria-expanded': 'false', onclick: () => parent.setAttribute('aria-expanded', String(parent.getAttribute('aria-expanded') !== 'true')) }, icon(r.groupIcon), r.group, icon('chevron-down'));
      g = { sub, el: h('div', { class: 'nav-group' }, parent, sub) }; groups.set(r.group, g); items.push(g.el);
    }
    g.sub.append(link(r));
  }
  navEl = h('nav', { class: 'nav', 'aria-label': 'Main' }, items);
  view = h('main', { class: 'main', id: 'view', tabindex: '-1' });
  const who = me.kind === 'partner' ? 'Partner' : humanize(me.role || 'staff');
  const rail = [btn('Change password', { kind: 'sm', icon: 'lock-keyhole', onClick: changePassword }),
    btn('Sign out', { kind: 'sm', icon: 'log-out', onClick: async () => { await logout(); invalidate(); showLogin(); } })];
  const support = me.support ? supportBanner() : null;
  if (me.support || me.kind === 'partner') rail.shift();
  app.replaceChildren(...[support, h('div', { class: 'shell' },
    h('aside', { class: 'rail' }, brand(), navEl,
      h('div', { class: 'rail-foot' }, h('span', {}, `${localStorage.getItem('kt.domain') || ''} - ${t(who)}`),
        langPicker(), ...rail)),
    h('div', { class: 'content' }, topbar(who), view))].filter(Boolean));
  refreshIcons();
}
/** The business name (and logo) across the top, so it is always clear whose account this is. */
function topbar(who) {
  const mark = h('span', { class: 'biz-logo', 'aria-hidden': 'true' });
  const name = h('b', { class: 'biz-name' });
  const draw = (n, logo) => {
    name.textContent = n || me.tenant_name || '';
    mark.replaceChildren(logo ? h('img', { src: logo, alt: '' }) : h('span', {}, (n || me.tenant_name || '?').trim().charAt(0).toUpperCase()));
  };
  draw(me.tenant_name, me.tenant_logo);
  document.addEventListener('kt:company', (e) => { me.tenant_name = e.detail.name || me.tenant_name; me.tenant_logo = e.detail.logo || null; draw(me.tenant_name, me.tenant_logo); });
  return h('header', { class: 'topbar' }, mark, h('div', { class: 'biz' }, name, h('span', { class: 'biz-sub' }, localStorage.getItem('kt.domain') || '')),
    h('div', { class: 'topbar-user' }, me.person_name ? h('b', {}, raw(me.person_name)) : null, h('span', { class: 'chip' }, t(who))));
}
function langPicker() {
  const s = h('select', { class: 'lang-pick', 'aria-label': 'Language', onchange: () => setLang(s.value) }, LANGS.map((l) => h('option', { value: l.code, selected: l.code === getLang() }, l.label)));
  return s;
}
function supportBanner() {
  return h('div', { class: 'banner', role: 'status' },
    h('span', {}, `Support session: ${me.support.admin} is signed in as this business. Every change is logged. Ends ${fmtDateTime(me.support.expires_at)}.`),
    btn('End session', { onClick: async () => {
      try { await post('/auth/support-end'); } catch { /* already ended */ }
      auth.clear(); invalidate(); me = null; view = null;
      app.replaceChildren(h('div', { class: 'login' }, h('div', { class: 'login-box' }, brand(), h('h1', {}, 'Support session ended'), h('p', { class: 'muted' }, 'You can close this tab.'))));
    } }));
}

function changePassword() {
  const cur = inp({ type: 'password', autocomplete: 'current-password' });
  const nw = inp({ type: 'password', autocomplete: 'new-password' });
  const m = modal({
    title: 'Change password',
    body: [field('Current password', cur), field('New password', nw, 'At least 10 characters. You will be signed out everywhere and sign in again.')],
    actions: [btn('Cancel', { onClick: () => m.close() }),
      btn('Change password', { kind: 'primary', onClick: async () => {
        await post('/auth/change-password', { current_password: cur.value, new_password: nw.value });
        m.close(); await logout(); invalidate(); showLogin('Password changed. Sign in with the new one.');
      } })],
  });
}

const humanize = (s) => String(s).toLowerCase().replace(/^./, (c) => c.toUpperCase());

function showLogin(message) {
  me = null; view = null;
  let principal = 'user';
  const domain = inp({ value: '', placeholder: 'yourbusiness.com (optional)', autocomplete: 'organization' });
  const email = inp({ type: 'email', autocomplete: 'username', required: true });
  const pass = inp({ type: 'password', autocomplete: 'current-password', required: true });
  const err = h('div', { class: 'callout bad', hidden: !message, role: 'alert' }, message || '');
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Account type' });
  const mk = (id, label) => { const b = h('button', { type: 'button', 'aria-pressed': String(id === principal), onclick: () => { principal = id; seg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); } }, label); return b; };
  seg.append(mk('user', 'Staff'), mk('partner', 'Partner'));
  const domainBox = field('Business domain', domain, 'Your email is used in more than one business. Enter the domain of the one you want.');
  domainBox.hidden = true;
  const submit = btn('Sign in', { kind: 'primary', type: 'submit' });
  const form = h('form', {
    onsubmit: async (e) => {
      e.preventDefault(); err.hidden = true; submit.disabled = true;
      try {
        await login(domain.value, email.value, pass.value, principal);
        await start();
      } catch (ex) { err.textContent = t(ex.status === 429 ? 'Too many attempts. Wait a few minutes and try again.' : ex.status === 401 ? (domain.value.trim() ? 'That email, password or business domain is not right.' : 'That email or password is not right.') : ex.message); err.hidden = false; if (ex.status === 409) { domainBox.hidden = false; domain.focus(); } }
      finally { submit.disabled = false; }
    },
  }, domainBox, field('Email', email), field('Password', pass), seg, err, submit);
  app.replaceChildren(h('div', { class: 'login' }, h('div', { class: 'login-box' }, brand(), h('div', {}, h('h1', {}, 'Sign in'), h('p', { class: 'muted', style: { margin: '6px 0 0' } }, 'Manage rooms, bookings, partners and your website content.')), form)));
  document.querySelector('.login-box')?.append(h('div', { class: 'login-lang' }, langPicker()));
  email.focus();
}

async function start() {
  try {
    me = await get('/auth/me');
    if (me.tenant_domain) { try { localStorage.setItem('kt.domain', me.tenant_domain); } catch { /* just not remembered */ } }
  } catch (e) { showLogin(e.status === 401 ? undefined : e.message); return; }
  showShell();
  await renderRoute();
}

onAuthLost(() => { invalidate(); showLogin('Your session ended. Sign in again.'); });
window.addEventListener('hashchange', () => renderRoute());

async function supportEntry(code) {
  history.replaceState(null, '', location.pathname + location.hash);
  try {
    const t = await api('POST', '/auth/support-exchange', { body: { code }, anonymous: true });
    auth.set({ access_token: t.access_token }); // no refresh token: a support session cannot outlive its time limit
    location.hash = '';
    await start();
  } catch (e) { showLogin(e.message); }
}

export async function boot() {
  await initLang();
  const code = new URLSearchParams(location.search).get('support');
  if (code) return supportEntry(code);
  if (auth.tokens) await start(); else showLogin();
}
boot();

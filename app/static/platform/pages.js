import { get, post, patch } from './api.js';
import {
  h, btn, field, inp, area, modal, table, badge, emptyState, pageHead, toast, humanize, refreshIcons, fmtDateTime, fmtDate, money, copyBtn, debounce,
} from '/admin/js/ui.js';
import { barChart, lineChart, hbars, panel } from '/admin/js/charts.js';

const STATUS_KIND = { ACTIVE: 'ok', PENDING: 'warn', SUSPENDED: 'bad', REJECTED: 'bad' };
const statusBadge = (s) => h('span', { class: 'badge ' + (STATUS_KIND[s] || '') }, humanize(s));
export const fmtBytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : n >= 1e3 ? `${Math.round(n / 1e3)} KB` : `${n} B`);
const monthLabel = (ym) => new Date(ym + '-01T00:00:00').toLocaleDateString(undefined, { month: 'short' });
const dayLabel = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
const tile = (v, label, alert) => h('div', { class: 'tile' + (alert ? ' alert' : '') }, h('b', {}, v), h('span', {}, label));
const revenueText = (rev) => Object.entries(rev || {}).map(([c, a]) => money(a, c)).join(' + ') || '-';
const ACTIONS = {
  login: 'Signed in', 'login.failed': 'Failed sign-in', 'tenant.create': 'Created a business', 'tenant.register': 'Business registered', 'tenant.approve': 'Approved a business',
  'tenant.reject': 'Rejected a business', 'tenant.suspend': 'Suspended a business', 'tenant.reactivate': 'Reactivated a business', 'tenant.update': 'Changed a business', 'tenant.showcase': 'Changed website featuring',
  'user.reset_password': 'Reset a password', 'support.start': 'Started a support session', 'support.end': 'Ended a support session', 'support.change': 'Change during support',
};
const actionLabel = (a) => ACTIONS[a] || humanize(a.replace('.', ' '));

// ------------------------------------------------------------------ overview
export async function overview({ go }) {
  const o = await get('/overview');
  const t = o.tenants;
  const pending = t.PENDING > 0 ? h('div', { class: 'callout', style: { marginBottom: '16px' } }, `${t.PENDING} business${t.PENDING === 1 ? ' is' : 'es are'} waiting for approval. `, h('a', { href: '#/tenants?status=PENDING' }, 'Review now')) : null;
  return h('div', {}, pageHead('Platform overview', 'All businesses on this service, at a glance.'), pending,
    h('div', { class: 'tile-row' },
      tile(t.ACTIVE, 'Active businesses'), tile(t.PENDING, 'Waiting for approval', t.PENDING > 0), tile(t.SUSPENDED, 'Suspended'),
      tile(o.properties, 'Properties'), tile(o.units, 'Rooms and cabins'), tile(o.bookings_30d, 'Bookings, last 30 days'),
      tile(fmtBytes(o.media_bytes), `Media storage (${o.media_files} files)`), tile(o.open_support_sessions, 'Open support sessions', o.open_support_sessions > 0)),
    h('div', { class: 'panels' },
      panel('New businesses per month', barChart(o.new_tenants_by_month.map((m) => ({ label: monthLabel(m.month), value: m.value, tip: `${m.month}: ${m.value}` })), { label: 'New businesses per month, last 12 months' }), 'last 12 months'),
      panel('Confirmed bookings per month', barChart(o.bookings_by_month.map((m) => ({ label: monthLabel(m.month), value: m.value, tip: `${m.month}: ${m.value}` })), { label: 'Confirmed bookings per month, last 12 months' }), 'all businesses')),
    h('div', { class: 'panels' },
      panel('Busiest businesses', hbars(o.top_tenants.filter((x) => x.bookings_30d > 0).map((x) => ({ label: x.name, value: x.bookings_30d, text: `${x.bookings_30d} bookings`, sub: x.domain })), { empty: 'No bookings in the last 30 days.' }), 'last 30 days'),
      panel('Most media storage', hbars(o.top_storage.map((x) => ({ label: x.name, value: x.media_bytes, text: fmtBytes(x.media_bytes) })), { empty: 'No uploads yet.' })),
      panel('Money collected', h('div', {}, h('b', { style: { fontSize: '22px' } }, revenueText(o.revenue)), h('div', { class: 'muted' }, 'Confirmed bookings, all time. Currencies are never added together.')))),
    panel('Recent activity', activityList(o.recent_activity), h('a', { href: '#/audit' }, 'Open the full log')));
}

const activityList = (items) => (items.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, h('tbody', {}, items.map((a) => h('tr', {},
  h('td', {}, actionLabel(a.action)), h('td', {}, a.tenant || ''), h('td', { class: 'muted' }, a.admin), h('td', { class: 'muted' }, fmtDateTime(a.at))))))) : h('div', { class: 'muted' }, 'Nothing yet.'));

// ------------------------------------------------------------------ tenants list
const LIMIT_FIELDS = [['max_properties', 'Properties'], ['max_units', 'Rooms and cabins'], ['max_partners', 'Partners'], ['media_quota_mb', 'Media storage (MB)']];
const limitInputs = (cur = {}) => Object.fromEntries(LIMIT_FIELDS.map(([k]) => [k, inp({ type: 'number', min: 0, value: cur[k] ?? '', placeholder: 'No limit' })]));
const readLimits = (inputs) => Object.fromEntries(LIMIT_FIELDS.map(([k]) => [k, inputs[k].value === '' ? null : Number(inputs[k].value)]));
const limitFields = (inputs) => h('div', { class: 'form-grid' }, LIMIT_FIELDS.map(([k, l]) => field(l, inputs[k])));

export async function tenants({ go }) {
  const q0 = new URLSearchParams(location.hash.split('?')[1] || '');
  let status = q0.get('status') || '';
  const search = inp({ type: 'search', placeholder: 'Search by name or domain', 'aria-label': 'Search businesses' });
  const pills = h('div', { class: 'seg-row', role: 'group', 'aria-label': 'Filter by status' });
  const list = h('div', {});
  async function load() {
    const r = await get('/tenants', { status, q: search.value.trim(), limit: 100 });
    pills.replaceChildren(...[['', 'All', Object.values(r.counts).reduce((a, b) => a + b, 0)], ['ACTIVE', 'Active'], ['PENDING', 'Pending'], ['SUSPENDED', 'Suspended'], ['REJECTED', 'Rejected']].map(([k, l, c]) =>
      h('button', { class: 'pill', type: 'button', 'aria-pressed': String(status === k), onclick: () => { status = k; load(); } }, `${l} (${c ?? r.counts[k]})`)));
    list.replaceChildren(table([
      { label: 'Business', render: (t) => h('div', {}, h('b', {}, t.name), h('div', { class: 'muted' }, t.domain)) },
      { label: 'Status', render: (t) => statusBadge(t.status) },
      { label: 'Properties', render: (t) => use(t.usage.properties, t.limits.max_properties) },
      { label: 'Rooms', render: (t) => use(t.usage.units, t.limits.max_units) },
      { label: 'Bookings (30d)', render: (t) => t.usage.bookings_30d },
      { label: 'Storage', render: (t) => fmtBytes(t.usage.media_bytes) },
      { label: 'Joined', render: (t) => fmtDate(t.created_at) },
    ], r.items, { onRowClick: (t) => go('/tenants/' + t.id), empty: 'No businesses match.' }));
  }
  search.addEventListener('input', debounce(load, 300));
  await load();
  return h('div', {}, pageHead('Businesses', 'Every business that uses this service.', btn('New business', { kind: 'primary', icon: 'plus', onClick: () => openCreate(go) })),
    h('div', { class: 'toolbar' }, pills, h('div', { style: { minWidth: '240px' } }, search)), list);
}
const use = (n, lim) => (lim == null ? String(n) : h('span', { style: lim && n >= lim ? { color: 'var(--bad)', fontWeight: 700 } : {} }, `${n} / ${lim}`));

function openCreate(go) {
  const name = inp({ maxlength: 200 }); const domain = inp({ placeholder: 'lakeview-resort.com', autocapitalize: 'none' });
  const adminName = inp({}); const adminEmail = inp({ type: 'email' }); const pw = inp({ type: 'password', autocomplete: 'new-password', placeholder: 'Leave empty to generate one' });
  const tz = inp({ value: 'UTC' }); const lim = limitInputs();
  const m = modal({ title: 'New business', wide: true,
    body: [h('div', { class: 'form-grid' }, field('Business name', name), field('Domain (account name)', domain, 'Used to sign in'), field('Owner name', adminName), field('Owner email', adminEmail),
      field('Password', pw, 'At least 10 characters'), field('Time zone', tz, 'e.g. Asia/Dhaka')), h('h3', {}, 'Limits'), h('p', { class: 'muted', style: { margin: 0 } }, 'Leave a box empty for no limit.'), limitFields(lim)],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Create business', { kind: 'primary', onClick: async () => {
      const r = await post('/tenants', { name: name.value.trim(), domain: domain.value.trim(), admin_name: adminName.value.trim(), admin_email: adminEmail.value.trim(),
        admin_password: pw.value || null, timezone: tz.value.trim() || 'UTC', limits: readLimits(lim) });
      m.close(); credentialsDialog(r, () => go('/tenants/' + r.tenant.id));
    } })] });
}
const secretRow = (label, value) => h('div', {}, h('div', { class: 'field-label' }, label), h('div', { class: 'secret' }, h('span', {}, value), copyBtn(value, 'Copy', 'sm')));
function credentialsDialog(r, done) {
  const m = modal({ title: 'Business created', onClose: done,
    body: [h('div', { class: 'callout' }, 'Save these now. The password and API secret are shown only once.'), secretRow('Sign-in domain', r.tenant.domain), secretRow('Owner email', r.admin_email),
      r.temporary_password ? secretRow('Temporary password', r.temporary_password) : null, secretRow('API key', r.api_key), secretRow('API secret', r.api_secret)],
    actions: [btn('Done', { kind: 'primary', onClick: () => m.close() })] });
}

// ------------------------------------------------------------------ tenant detail
export async function tenantDetail({ params, go }) {
  const root = h('div', {});
  const reload = async () => { root.replaceChildren(...build(await get('/tenants/' + params.id))); refreshIcons(); };
  function build(t) {
    const u = t.usage;
    const quota = t.limits.media_quota_mb;
    const bar = (label, n, lim, fmt = String) => {
      const pct = lim ? Math.min(100, (n / lim) * 100) : 0;
      return h('div', { class: 'hb' }, h('div', { class: 'hb-top' }, h('span', { class: 'hb-label' }, label), h('span', { class: 'hb-val' }, lim == null ? `${fmt(n)} (no limit)` : `${fmt(n)} of ${fmt(lim)}`)),
        h('div', { class: 'bar' + (pct >= 100 ? ' bad' : pct >= 80 ? ' warn' : ''), role: 'img', 'aria-label': `${label}: ${fmt(n)}` }, h('i', { style: { width: lim == null ? '0%' : `${pct}%` } })));
    };
    const act = (label, opts) => btn(label, opts);
    const buttons = [];
    if (t.status === 'PENDING') buttons.push(act('Approve', { kind: 'primary', icon: 'check', onClick: async () => { await post(`/tenants/${t.id}/approve`); toast('Approved', 'ok'); await reload(); } }),
      act('Reject', { kind: 'danger', onClick: () => reasonDialog('Reject this registration', 'Reject', async (reason) => { await post(`/tenants/${t.id}/reject`, { reason }); await reload(); }) }));
    if (t.status === 'ACTIVE') buttons.push(act('Sign in as this business', { icon: 'life-buoy', onClick: () => supportDialog(t) }),
      act('Suspend', { kind: 'danger', onClick: () => reasonDialog('Suspend this business', 'Suspend', async (reason) => { await post(`/tenants/${t.id}/suspend`, { reason }); await reload(); }, 'They are signed out at once and their website API stops working until you reactivate.') }));
    if (t.status === 'ACTIVE') buttons.push(act(t.showcase ? 'Stop featuring on website' : 'Feature on website', { onClick: async () => { await post(`/tenants/${t.id}/showcase?enabled=${t.showcase ? 'false' : 'true'}`); toast(t.showcase ? 'Removed from the public website' : 'Now shown on the public website', 'ok'); await reload(); } }));
    if (t.status === 'SUSPENDED' || t.status === 'REJECTED') buttons.push(act('Reactivate', { kind: 'primary', onClick: async () => { await post(`/tenants/${t.id}/reactivate`); toast('Reactivated', 'ok'); await reload(); } }));
    const days = t.bookings_by_day.map((d) => ({ label: dayLabel(d.day), value: d.bookings, tip: `${dayLabel(d.day)}: ${d.bookings} booking${d.bookings === 1 ? '' : 's'}` }));
    return [
      pageHead(t.name, `${t.domain} - joined ${fmtDate(t.created_at)}`, ...buttons),
      h('div', { style: { marginBottom: '14px' } }, statusBadge(t.status), t.status_reason ? h('span', { class: 'muted' }, `  ${t.status_reason}`) : null),
      h('div', { class: 'tile-row' }, tile(u.bookings, 'Confirmed bookings'), tile(u.bookings_30d, 'Bookings, last 30 days'), tile(revenueText(u.revenue), 'Money collected'), tile(u.last_booking_at ? fmtDate(u.last_booking_at) : 'Never', 'Last booking')),
      h('div', { class: 'panels' },
        panel('Usage and limits', h('div', { class: 'hbars' }, bar('Properties', u.properties, t.limits.max_properties), bar('Rooms and cabins', u.units, t.limits.max_units), bar('Partners', u.partners, t.limits.max_partners),
          bar('Media storage', Math.round(u.media_bytes / 1e6), quota ?? null, (n) => `${n} MB`), h('div', { class: 'hint' }, quota == null ? `Storage uses the platform default. ${u.media_files} files.` : `${u.media_files} files.`)),
          btn('Change limits', { icon: 'sliders-horizontal', onClick: () => limitsDialog(t, reload) })),
        panel('Bookings made per day', barChart(days, { label: 'Bookings per day, last 30 days' }), 'last 30 days')),
      h('h2', { class: 'section' }, 'People who sign in'),
      table([{ label: 'Name', render: (x) => x.name }, { label: 'Email', render: (x) => x.email }, { label: 'Role', render: (x) => humanize(x.role) }, { label: 'Active', render: (x) => (x.is_active ? 'Yes' : 'No') },
        { label: '', render: (x) => btn('Reset password', { kind: 'sm', icon: 'key-round', onClick: () => resetDialog(t, x) }) }], t.users),
      h('h2', { class: 'section' }, 'Support sessions'),
      sessionTable(t.support_sessions, false),
      h('h2', { class: 'section' }, 'Recent activity'),
      t.activity.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' }, h('tbody', {}, t.activity.map((a) => h('tr', {}, h('td', {}, actionLabel(a.action)), h('td', { class: 'muted' }, a.admin), h('td', { class: 'muted' }, fmtDateTime(a.at))))))) : emptyState('Nothing logged for this business yet.')];
  }
  root.replaceChildren(...build(await get('/tenants/' + params.id)));
  return root;
}

function reasonDialog(title, confirm, onDone, note) {
  const reason = area({ rows: 3, maxlength: 400 });
  const m = modal({ title, body: [note ? h('p', { class: 'muted', style: { margin: 0 } }, note) : null, field('Reason', reason, 'Saved in the audit log and shown to the business owner when they try to sign in.')],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn(confirm, { kind: 'danger', onClick: async () => { await onDone(reason.value.trim()); m.close(); } })] });
}

function limitsDialog(t, reload) {
  const lim = limitInputs(t.limits);
  const m = modal({ title: `Limits for ${t.name}`, body: [h('p', { class: 'muted', style: { margin: 0 } }, 'Empty means no limit. Lowering a limit never deletes anything; it only stops new items being added.'), limitFields(lim)],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Save limits', { kind: 'primary', onClick: async () => { await patch('/tenants/' + t.id, { limits: readLimits(lim) }); toast('Limits saved', 'ok'); m.close(); await reload(); } })] });
}

function resetDialog(t, user) {
  const pw = inp({ type: 'password', autocomplete: 'new-password', placeholder: 'Leave empty to generate one' });
  const m = modal({ title: `Reset password for ${user.name}`, body: [h('p', { style: { margin: 0 } }, `${user.email} will be signed out everywhere.`), field('New password', pw, 'At least 10 characters. Leave empty and we make a strong one.')],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Reset password', { kind: 'primary', onClick: async () => {
      const r = await post(`/tenants/${t.id}/users/${user.id}/reset-password`, { password: pw.value || null });
      if (r.temporary_password) m.setBody([h('div', { class: 'callout' }, 'Give this temporary password to the owner. It is shown only once.'), secretRow('Temporary password', r.temporary_password)]);
      else { toast('Password reset', 'ok'); m.close(); return; }
      m.setActions([btn('Done', { kind: 'primary', onClick: () => m.close() })]);
    } })] });
}

function supportDialog(t) {
  const reason = area({ rows: 3, maxlength: 400, placeholder: 'e.g. Ticket 1042: owner cannot add a unit to Lotus Houseboat' });
  const m = modal({ title: `Sign in as ${t.name}`,
    body: [h('p', { style: { margin: 0 } }, 'You will open their console in a new tab with limited access. The session ends on its own, and every change you make is logged. You cannot change their API keys or approve payouts.'), field('Why do you need to sign in?', reason, 'At least 10 characters. Saved in the log.')],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn('Open their console', { kind: 'primary', icon: 'external-link', onClick: async () => {
      const r = await post(`/tenants/${t.id}/support-session`, { reason: reason.value.trim() });
      window.open(r.url, '_blank', 'noopener');
      toast(`Support session started (${r.session_minutes} minutes)`, 'ok'); m.close();
    } })] });
}

// ------------------------------------------------------------------ logs
const STATE_KIND = { open: 'warn', ended: 'ok', expired: '' };
function sessionTable(rows, showTenant = true) {
  return table([
    ...(showTenant ? [{ label: 'Business', render: (s) => h('a', { href: '#/tenants/' + s.tenant_id }, s.tenant) }] : []),
    { label: 'Who', render: (s) => s.admin }, { label: 'Signed in as', render: (s) => s.user }, { label: 'Reason', render: (s) => s.reason },
    { label: 'Started', render: (s) => fmtDateTime(s.started_at) }, { label: 'Changes', render: (s) => s.changes },
    { label: 'State', render: (s) => h('span', { class: 'badge ' + (STATE_KIND[s.state] || '') }, humanize(s.state)) },
  ], rows, { empty: 'No support sessions yet.' });
}

const off = (b, d) => { b.disabled = d; return b; };
function paged(fetchPage) {
  const box = h('div', {}); let offset = 0;
  async function load() {
    const r = await fetchPage(offset);
    box.replaceChildren(r.node, h('div', { class: 'pager' }, h('span', {}, r.total ? `${offset + 1}-${Math.min(offset + r.size, r.total)} of ${r.total}` : ''),
      h('span', { class: 'row' }, off(btn('Newer', { kind: 'sm', onClick: async () => { offset = Math.max(0, offset - r.size); await load(); } }), offset === 0), off(btn('Older', { kind: 'sm', onClick: async () => { offset += r.size; await load(); } }), offset + r.size >= r.total))));
  }
  return load().then(() => box);
}

export async function supportSessions() {
  const list = await paged(async (offset) => { const r = await get('/support-sessions', { limit: 25, offset }); return { node: sessionTable(r.items), total: r.total, size: 25 }; });
  return h('div', {}, pageHead('Support sessions', 'Every time someone signed in as a business, why, and how many changes they made.'), list);
}

const KEEP = new Set(['session']);
export async function auditLog() {
  const kind = h('select', { class: 'input', 'aria-label': 'Filter by activity' }, [['', 'All activity'], ['login', 'Sign-ins'], ['tenant', 'Business changes'], ['user', 'Password resets'], ['support', 'Support sessions']].map(([v, l]) => h('option', { value: v }, l)));
  const holder = h('div', {});
  const draw = async () => holder.replaceChildren(await paged(async (offset) => {
    const r = await get('/audit', { limit: 30, offset, action: kind.value });
    return { total: r.total, size: 30, node: table([
      { label: 'When', render: (a) => fmtDateTime(a.at) }, { label: 'Activity', render: (a) => actionLabel(a.action) }, { label: 'Who', render: (a) => a.admin },
      { label: 'Business', render: (a) => (a.tenant_id ? h('a', { href: '#/tenants/' + a.tenant_id }, a.tenant) : a.tenant || '') },
      { label: 'Details', render: (a) => h('span', { class: 'muted' }, detailText(a.detail)) }, { label: 'From', render: (a) => h('span', { class: 'muted' }, a.ip || '') }], r.items, { empty: 'Nothing logged yet.' }) };
  }));
  kind.addEventListener('change', draw);
  await draw();
  return h('div', {}, pageHead('Audit log', 'Everything done in this portal and in support sessions. It cannot be edited or deleted.'), h('div', { class: 'toolbar' }, h('div', { style: { minWidth: '220px' } }, kind)), holder);
}
const detailText = (d) => Object.entries(d || {}).filter(([k]) => !KEEP.has(k)).map(([k, v]) => `${humanize(k)}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ').slice(0, 160);

// ------------------------------------------------------------------ overdue reseller commission
export async function overdueCommissions() {
  const r = await get('/channel/overdue');
  const total = r.totals.length ? r.totals.map((t) => money(t.amount, t.currency)).join(' + ') : '0';
  return h('div', {}, pageHead('Late commissions', 'Reseller commission that an owner has not paid by the due date, and payments a reseller says never arrived. The money moves between the two businesses, not through this service.'),
    h('div', { class: 'tile-row' }, tile(r.items.length, 'Statements needing attention', r.items.length > 0), tile(total, 'Total late or disputed')),
    table([
      { label: 'Owner (owes)', render: (x) => h('a', { href: '#/tenants/' + x.owner_id }, x.owner) },
      { label: 'Reseller (is owed)', render: (x) => h('a', { href: '#/tenants/' + x.reseller_id }, x.reseller) },
      { label: 'Statement', render: (x) => x.code },
      { label: 'Amount', render: (x) => h('b', {}, money(x.amount, x.currency)) },
      { label: 'Due', render: (x) => fmtDate(x.due_date) },
      { label: 'Problem', render: (x) => (x.status === 'DISPUTED' ? h('span', {}, h('span', { class: 'badge bad' }, 'Reseller says not received'), h('div', { class: 'muted' }, x.dispute_reason || '')) : h('span', { class: 'badge bad' }, `${x.days_overdue} day${x.days_overdue === 1 ? "" : "s"} late`)) },
    ], r.items, { empty: 'Nothing is late. Every statement is paid or not yet due.' }));
}


// ------------------------------------------------------------------ messages from the public website
export async function messages() {
  const which = h('select', { class: 'input', 'aria-label': 'Filter' }, [['', 'All'], ['NEW', 'New'], ['DONE', 'Handled']].map(([v, l]) => h('option', { value: v }, l)));
  const holder = h('div', {});
  const draw = async () => holder.replaceChildren(await paged(async (offset) => {
    const r = await get('/messages', { limit: 30, offset, status: which.value });
    return { total: r.total, size: 30, node: table([
      { label: 'When', render: (m) => fmtDateTime(m.created_at) },
      { label: 'From', render: (m) => h('span', {}, h('b', {}, m.name), h('div', { class: 'muted' }, h('a', { href: 'mailto:' + m.email }, m.email), m.phone ? ' - ' + m.phone : '')) },
      { label: 'Runs', render: (m) => humanize(m.business_type) },
      { label: 'Message', render: (m) => h('span', { style: { whiteSpace: 'pre-wrap' } }, m.message) },
      { label: 'Status', render: (m) => h('span', { class: 'badge ' + (m.status === 'NEW' ? 'warn' : 'ok') }, m.status === 'NEW' ? 'New' : 'Handled') },
      { label: '', render: (m) => btn(m.status === 'NEW' ? 'Mark handled' : 'Reopen', { kind: 'sm', onClick: async () => { await post(`/messages/${m.id}/done?done=${m.status === 'NEW'}`); await draw(); } }) }], r.items, { empty: 'No messages yet.' }) };
  }));
  which.addEventListener('change', draw);
  await draw();
  return h('div', {}, pageHead('Website messages', 'Messages sent from the contact form on the public website.'), h('div', { class: 'toolbar' }, h('div', { style: { minWidth: '180px' } }, which)), holder);
}

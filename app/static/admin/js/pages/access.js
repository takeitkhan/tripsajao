import { get, post, put } from '../api.js';
import { h, btn, check, confirmDialog, pageHead, copyBtn, toast } from '../ui.js';
import { withDocs } from '../docs.js';

const GROUPS = [
  ['Website (read only)', ['properties:read', 'pricing:read', 'availability:read', 'cms:read']],
  ['Take bookings', ['bookings:create']],
  ['Events', ['events:read', 'events:book']],
  ['Business profile', ['business:read', 'business:manage']],
  ['Sell other businesses\' rooms (resellers)', ['channel:read', 'channel:book']],
  ['Back office', ['bookings:read', 'bookings:manage', 'dashboard:read', 'partners:read', 'payouts:read', 'properties:write', 'pricing:write', 'cms:write', 'docs:read']],
  ['Customers (CRM)', ['customers:read', 'customers:manage', 'customers:export']],
  ['Event bookings and events (back office)', ['events:write', 'event_bookings:read', 'event_bookings:manage']],
  ['Vendors and budgets', ['vendors:read', 'vendors:write', 'budgets:read', 'budgets:write']],
  ['Partners and payouts (write)', ['partners:write', 'payouts:approve']],
];
const DEFAULT_ON = new Set(['properties:read', 'pricing:read', 'availability:read', 'cms:read', 'bookings:create', 'events:read', 'events:book']);

export function render() {
  return h('div', {}, pageHead('API access', 'Credentials your website or app uses to read inventory, content and take bookings.'), withDocs('auth', manage));
}

async function manage() {
  const cur = await get('/auth/api-credentials');
  const saved = new Set(cur.scopes);
  const boxes = {};
  const out = h('div');
  const groups = GROUPS.map(([title, scopes]) => h('div', {}, h('h3', { style: { marginBottom: '8px' } }, title),
    h('div', { class: 'stack', style: { gap: '8px' } }, scopes.map((s) => { boxes[s] = check(`${s}`, cur.api_key ? saved.has(s) : DEFAULT_ON.has(s)); return boxes[s]; }))));
  const chosen = () => {
    const scopes = Object.keys(boxes).filter((s) => boxes[s].querySelector('input').checked);
    if (!scopes.length) throw new Error('Choose at least one permission.');
    return scopes;
  };
  const keyBox = h('div', {});
  const paintKey = (key) => keyBox.replaceChildren(h('div', { class: 'field-label' }, 'X-API-KEY'), key ? h('div', { class: 'secret' }, h('span', {}, key), copyBtn(key)) : h('p', { class: 'muted' }, 'No credentials yet. Choose permissions and create them.'));
  paintKey(cur.api_key);
  const showSecret = (k, what) => {
    paintKey(k.api_key);
    out.replaceChildren(
      h('div', { class: 'callout' }, h('b', {}, 'Copy the secret now. '), 'It is stored only in scrambled form, so it cannot be shown again. If you lose it, change the secret.'),
      h('div', {}, h('div', { class: 'field-label' }, 'X-API-SECRET'), h('div', { class: 'secret' }, h('span', {}, k.api_secret), copyBtn(k.api_secret))));
    toast(what, 'ok');
  };
  return h('div', { class: 'stack', style: { maxWidth: '760px' } },
    h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Your credentials'), keyBox,
      h('p', { class: 'muted' }, 'The secret is never stored in readable form, so it is shown only when it is created. Change it whenever you need a new one; the key and permissions stay the same.'),
      h('div', { class: 'row' },
        cur.api_key ? btn('Change secret', { icon: 'refresh-cw', onClick: async () => {
          if (!(await confirmDialog('The current secret stops working right away. The key and permissions stay the same.', { confirmText: 'Change secret', danger: true, title: 'Change the API secret?' }))) return;
          showSecret(await post('/auth/api-keys/rotate-secret', {}), 'Secret changed');
        } }) : null),
      out),
    h('h3', { style: { margin: '8px 0 0' } }, 'Permissions'),
    h('div', { class: 'form-grid' }, groups),
    h('div', { class: 'row' },
      cur.api_key ? btn('Save permissions', { kind: 'primary', icon: 'save', onClick: async () => {
        await put('/auth/api-keys/scopes', { scopes: chosen() }); toast('Permissions saved. The key and secret did not change.', 'ok');
      } }) : null,
      btn(cur.api_key ? 'New key and secret' : 'Create credentials', { kind: cur.api_key ? '' : 'primary', icon: 'key-round', onClick: async () => {
        const scopes = chosen();
        if (cur.api_key && !(await confirmDialog('A new key and secret are created. The current ones stop working right away.', { confirmText: 'Replace credentials', danger: true, title: 'Replace API credentials?' }))) return;
        const k = await post('/auth/api-keys', { scopes });
        cur.api_key = k.api_key; showSecret(k, 'New credentials created');
      } })),
    cur.api_key ? h('div', { class: 'callout warn' }, 'Replacing the key or changing the secret stops anything that uses the old one, so update your website first or right after.') : null);
}

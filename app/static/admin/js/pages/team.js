// Team: staff accounts and exactly what each person may do.
import { get, post, patch } from '../api.js';
import { h, raw, btn, field, inp, sel, check, modal, table, badge, pageHead, confirmDialog, toast, reportError, copyBtn } from '../ui.js';
import { withDocs } from '../docs.js';

const ROLES = [['ADMIN', 'Admin (everything)'], ['MANAGER', 'Manager'], ['STAFF', 'Staff']];
const roleName = (r) => ({ ADMIN: 'Admin', MANAGER: 'Manager', STAFF: 'Staff' }[r] || r);

const levelOf = (g, scopes) => {
  const have = new Set(scopes);
  for (const l of [...g.levels].reverse()) if (l.scopes.every((s) => have.has(s))) return l.key;
  return '';
};
const scopesFor = (catalog, picks) => [...new Set(catalog.groups.flatMap((g) => g.levels.find((l) => l.key === picks[g.key])?.scopes || []))];

function showPassword(title, email, pw) {
  const m = modal({ title, body: [
    h('p', {}, `Give ${email} this temporary password. It is shown only once.`),
    h('div', { class: 'secret' }, h('code', {}, pw), copyBtn(pw, 'Copy')),
    h('p', { class: 'hint' }, 'They can change it after signing in, using Change password.')],
  actions: [btn('Done', { kind: 'primary', onClick: () => m.close() })] });
}

async function openPerson(person, catalog, onSaved) {
  const edit = !!person;
  const name = inp({ value: person?.name || '', maxlength: 200 });
  const email = inp({ type: 'email', value: person?.email || '', disabled: edit });
  const pass = inp({ type: 'password', minlength: 10, autocomplete: 'new-password', placeholder: 'Leave blank to make one for you' });
  const role = sel(ROLES, person?.role || 'STAFF');
  const custom = check('Choose exactly what this person can do', !!person?.custom_access);
  const picks = {};
  const box = h('div', { class: 'perm-box' });
  const startScopes = () => (person?.custom_access ? person.permissions : catalog.defaults[role.value] || []);
  const setPicksFrom = (scopes) => catalog.groups.forEach((g) => { picks[g.key] = levelOf(g, scopes); });
  setPicksFrom(startScopes());
  const infoLine = h('div', { class: 'hint' });

  function drawBox() {
    const isAdmin = role.value === 'ADMIN';
    custom.style.display = isAdmin ? 'none' : '';
    infoLine.textContent = isAdmin ? 'Admins can do everything, including managing the team and API access.' : custom.querySelector('input').checked ? '' : `${roleName(role.value)} standard access. Tick the box above to change it for this person.`;
    box.replaceChildren();
    if (isAdmin || !custom.querySelector('input').checked) return;
    box.append(h('div', { class: 'perm-grid' }, catalog.groups.map((g) => {
      const s = sel([['', 'No access'], ...g.levels.map((l) => [l.key, l.label])], picks[g.key]);
      s.addEventListener('change', () => { picks[g.key] = s.value; });
      return h('div', { class: 'perm-row' }, h('span', {}, g.label), s);
    })), h('div', { class: 'hint' }, 'API access and managing the team stay with admins only.'));
  }
  role.addEventListener('change', () => { if (!custom.querySelector('input').checked) setPicksFrom(catalog.defaults[role.value] || []); drawBox(); });
  custom.querySelector('input').addEventListener('change', () => { if (custom.querySelector('input').checked && !person?.custom_access) setPicksFrom(catalog.defaults[role.value] || []); drawBox(); });
  drawBox();

  const m = modal({ title: edit ? `Edit ${person.name}` : 'Add a team member', wide: true,
    body: [h('div', { class: 'form-grid' }, field('Name', name), field('Email', email, edit ? 'Email cannot change.' : null), edit ? null : field('Temporary password', pass, 'At least 10 characters.'), field('Role', role)),
      custom, infoLine, box],
    actions: [btn('Cancel', { onClick: () => m.close() }), btn(edit ? 'Save changes' : 'Add member', { kind: 'primary', onClick: async () => {
      if (!name.value.trim()) throw new Error('Enter the full name.');
      if (!edit && !email.value.trim()) throw new Error('Enter the email.');
      const isAdmin = role.value === 'ADMIN'; const useCustom = !isAdmin && custom.querySelector('input').checked;
      if (useCustom && !scopesFor(catalog, picks).length) throw new Error('Choose at least one thing this person can do.');
      if (edit) {
        await patch(`/staff/${person.id}`, { name: name.value.trim(), role: role.value, ...(useCustom ? { permissions: scopesFor(catalog, picks) } : { reset_to_role: true }) });
        toast('Saved', 'ok'); m.close(); onSaved();
      } else {
        const r = await post('/staff', { name: name.value.trim(), email: email.value.trim(), role: role.value, password: pass.value || undefined, ...(useCustom ? { permissions: scopesFor(catalog, picks) } : {}) });
        toast('Team member added', 'ok'); m.close(); onSaved();
        if (r.temporary_password) showPassword('Temporary password', r.email, r.temporary_password);
      }
    } })] });
}

export function render() {
  return h('div', {}, pageHead('Team', 'The people who sign in to this business, and exactly what each of them may do.'), withDocs('staff', manage));
}

async function manage() {
  const root = h('div'); const holder = h('div');
  let catalog = null;
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const people = await get('/staff');
    holder.replaceChildren(table([
      { label: 'Person', render: (p) => h('div', {}, h('b', {}, raw(p.name)), h('div', { class: 'muted' }, raw(p.email))) },
      { label: 'Role', render: (p) => roleName(p.role) },
      { label: 'Access', render: (p) => (p.role === 'ADMIN' ? 'Everything' : p.custom_access ? 'Chosen for this person' : 'Standard') },
      { label: 'Status', render: (p) => badge(p.is_active ? 'PUBLISHED' : 'DRAFT', p.is_active ? 'Active' : 'Switched off') },
      { label: '', render: (p) => h('div', { class: 'actions' },
        btn('Edit', { kind: 'sm', onClick: () => openPerson(p, catalog, () => load().catch(reportError)).catch(reportError) }),
        btn('New password', { kind: 'sm', onClick: async () => {
          if (!(await confirmDialog(`Give ${p.name} a new password? They will be signed out everywhere.`, { confirmText: 'New password' }))) return;
          const r = await post(`/staff/${p.id}/reset-password`, {}); showPassword('New password', p.email, r.temporary_password);
        } }),
        btn(p.is_active ? 'Switch off' : 'Switch on', { kind: 'sm', onClick: async () => {
          if (p.is_active && !(await confirmDialog(`Switch off ${p.name}? They are signed out at once and cannot sign in.`, { confirmText: 'Switch off', danger: true }))) return;
          await patch(`/staff/${p.id}`, { is_active: !p.is_active }); toast(p.is_active ? 'Switched off' : 'Switched on', 'ok'); await load();
        } })) },
    ], people, { empty: 'No team members yet.' }));
  }
  root.append(
    h('div', { class: 'callout', style: { marginBottom: '18px' } }, 'Give each person only what they need. Changes work straight away, with no need to sign in again.'),
    h('div', { class: 'toolbar' }, h('div', { style: { marginLeft: 'auto' } }, btn('Add team member', { kind: 'primary', icon: 'user-plus', onClick: () => openPerson(null, catalog, () => load().catch(reportError)).catch(reportError) }))),
    holder);
  catalog = await get("/staff/permissions"); await load(); return root;
}

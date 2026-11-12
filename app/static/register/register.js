import { h, btn, field, inp, sel, slugify, debounce } from '/admin/js/ui.js';
import { t, initLang, LANGS, getLang, setLang } from '/admin/js/i18n.js';

const app = document.getElementById('app');
const api = async (method, path, body) => {
  const res = await fetch('/api/v1/public' + path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    const msg = Array.isArray(d) ? d.map((e) => `${(e.loc || []).filter((x) => x !== 'body').join(' > ')}: ${String(e.msg).replace(/^Value error, /, '')}`).join('; ') : d || 'Something went wrong. Try again.';
    throw new Error(t(res.status === 429 ? 'Too many attempts. Wait a while and try again.' : msg));
  }
  return data;
};
const langPicker = () => { const s = h('select', { class: 'lang-pick', 'aria-label': 'Language', onchange: () => setLang(s.value) }, LANGS.map((l) => h('option', { value: l.code, selected: l.code === getLang() }, l.label))); return h('div', { class: 'login-lang' }, s); };
const shell = (...kids) => app.replaceChildren(h('div', { class: 'reg' }, h('div', { class: 'reg-box' }, h('div', { class: 'brand' }, 'Trip Sajao'), ...kids, langPicker())));

async function main() {
  await initLang();
  let cfg;
  try { cfg = await api('GET', '/register/config'); } catch (e) { return shell(h('div', { class: 'callout bad' }, e.message)); }
  if (cfg.mode === 'closed') return shell(h('h1', {}, 'Registration is closed'), h('p', { class: 'muted' }, 'We are not taking new businesses right now. Contact us if you think this is a mistake.'), h('a', { href: '/admin/' }, 'Already registered? Sign in'));

  const name = inp({ maxlength: 200, autocomplete: 'organization' });
  const domain = inp({ maxlength: 253, placeholder: 'lakeview-resort.com', autocapitalize: 'none', spellcheck: 'false' });
  let touched = false;
  const domHint = h('span', { class: 'hint' }, 'Your account name. Your guests never see it unless you want them to.');
  const owner = inp({ maxlength: 200, autocomplete: 'name' });
  const email = inp({ type: 'email', autocomplete: 'email' });
  const pass = inp({ type: 'password', autocomplete: 'new-password' });
  const phone = inp({ type: 'tel', autocomplete: 'tel', maxlength: 40 });
  const country = inp({ autocomplete: 'country-name', maxlength: 80 });
  const type = sel(cfg.business_types, 'RESORT');
  const terms = h('input', { type: 'checkbox' });
  const trap = h('input', { type: 'text', name: 'website', tabindex: '-1', autocomplete: 'off', 'aria-hidden': 'true' });
  const err = h('div', { class: 'callout bad', role: 'alert', hidden: true });
  let free = null;

  const check = debounce(async () => {
    if (domain.value.trim().length < 3) { domHint.textContent = ''; free = null; return; }
    try {
      const r = await api('GET', '/register/check?domain=' + encodeURIComponent(domain.value));
      free = r.available;
      domHint.textContent = r.available ? t(`${r.domain} is available.`) : t(r.message);
      domHint.style.color = r.available ? 'var(--ok)' : 'var(--bad)';
    } catch { /* the form will report it on submit */ }
  }, 400);
  domain.addEventListener('input', () => { touched = true; check(); });
  name.addEventListener('input', () => { if (!touched) { domain.value = slugify(name.value) ? slugify(name.value) + '.com' : ''; check(); } });

  const submit = btn('Register', { kind: 'primary', type: 'submit' });
  const form = h('form', {
    novalidate: true,
    onsubmit: async (e) => {
      e.preventDefault(); err.hidden = true; submit.disabled = true;
      try {
        const r = await api('POST', '/register', {
          business_name: name.value.trim(), domain: domain.value.trim(), owner_name: owner.value.trim(), email: email.value.trim(), password: pass.value,
          phone: phone.value.trim() || null, country: country.value.trim() || null, business_type: type.value, accept_terms: terms.checked, website: trap.value || null,
        });
        done(r, domain.value.trim().toLowerCase());
      } catch (ex) { err.textContent = ex.message; err.hidden = false; err.scrollIntoView?.({ block: 'nearest' }); } finally { submit.disabled = false; }
    },
  },
  h('div', { class: 'form-grid' }, field('Business name', name), h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Account name (domain)'), domain, domHint),
    field('Type of business', type), field('Country', country), field('Your name', owner), field('Phone', phone), field('Email', email), field('Password', pass, 'At least 10 characters.')),
  h('div', { class: 'hp', 'aria-hidden': 'true' }, h('label', {}, 'Leave this empty', trap)),
  h('label', { class: 'check' }, terms, 'I accept the terms of service'), err, submit);

  shell(h('div', {}, h('h1', {}, 'Register your business'), h('p', { class: 'muted', style: { margin: '6px 0 0' } },
    cfg.mode === 'open' ? 'Create your account and start right away.' : 'Tell us about your business. We review each registration and email you when it is ready.')),
  form, h('p', { class: 'muted' }, 'Already registered? ', h('a', { href: '/admin/' }, 'Sign in')));
  name.focus();
}

function done(r, domain) {
  const ready = r.status === 'ACTIVE';
  shell(h('h1', {}, ready ? 'Your account is ready' : 'Thanks, we have your registration'),
    h('div', { class: 'callout' }, ready ? 'Sign in with the email and password you just chose.' : 'We will review it shortly. You can sign in once it is approved.'),
    h('p', {}, 'Your account name is ', h('code', {}, domain), '. You need it to sign in.'),
    h('a', { class: 'btn primary', href: '/admin/' }, ready ? 'Sign in' : 'Go to sign in'));
}
main();

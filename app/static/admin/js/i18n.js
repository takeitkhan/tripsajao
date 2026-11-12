// Languages for the admin console.
// How it works: every text the console draws passes through t(). English is the source text. A language file (lang/<code>.js) maps
// the English text to the translation. Text with changing parts uses {} (or {1}, {2} to reorder): "Let {} sell your rooms".
// Text that has no translation is shown in English, and listed by __i18nMissing() in the browser console, so a new language can be
// filled in by opening each page and copying that list.
//
// To add a language: (1) add a line to LANGS below, (2) create lang/<code>.js with `export default { ... }` (copy lang/bn.js).
const KEY = 'kt.lang';
export const LANGS = [
  { code: 'en', label: 'English', locale: undefined },
  { code: 'bn', label: 'বাংলা', locale: 'bn-BD' },
];

let lang = 'en';
let dict = {};
let digits = null;
let templates = [];
const cache = new Map();
const missing = new Set();
window.__i18nMissing = () => [...missing].sort();

const known = (code) => LANGS.find((l) => l.code === code);
const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };

export async function initLang(force) {
  let code = force || stored();
  if (!known(code)) code = (navigator.languages || [navigator.language || 'en']).map((x) => String(x).slice(0, 2)).find(known) || 'en';
  await load(code);
}

async function load(code) {
  lang = code;
  dict = {};
  if (code !== 'en') {
    try { dict = (await import(`./lang/${code}.js`)).default || {}; } catch (e) { console.error('language file missing', code, e); lang = 'en'; }
  }
  digits = dict.__digits__ || null;
  delete dict.__digits__;
  cache.clear();
  templates = Object.keys(dict).filter((k) => k.includes('{')).map((k) => {
    const parts = k.split(/\{\d*\}/).map((p) => p.replace(/[.*+?^$()|[\]\\]/g, '\\$&'));
    return { re: new RegExp('^' + parts.join('(.*?)') + '$', 's'), to: dict[k] };
  });
  document.documentElement.lang = lang;
}

export function setLang(code) {
  if (!known(code)) return;
  try { localStorage.setItem(KEY, code); } catch { /* the choice is just not remembered */ }
  location.reload();
}
export const getLang = () => lang;
export const locale = () => known(lang)?.locale;

export function num(s) {
  if (!digits) return s;
  return String(s).replace(/[0-9]/g, (d) => digits[+d]);
}

const WORD = /[A-Za-z]{2}/;
// amounts such as "440.00 US$" are already formatted for the language; they only need local digits
const AMOUNT = /^(?=.*[\d\u09E6-\u09EF])[\d\u09E6-\u09EF\s.,:/+-]*(?:[A-Z]{2,3}\$?|\u09F3)?[\d\u09E6-\u09EF\s.,:/+-]*$/;
export function t(s) {
  if (lang === 'en' || typeof s !== 'string' || s === '') return s;
  const hit = cache.get(s);
  if (hit !== undefined) return hit;
  const core = s.trim();
  let out = s;
  if (core && WORD.test(core) && !AMOUNT.test(core)) {
    const lead = s.slice(0, s.indexOf(core)), tail = s.slice(s.indexOf(core) + core.length);
    let r = dict[core];
    if (r === undefined) {
      for (const { re, to } of templates) {
        const m = re.exec(core);
        if (!m) continue;
        const vals = m.slice(1).map((v) => (/^[\d.,]+$/.test(v) ? num(v) : t(v)));
        let i = 0;
        r = to.replace(/\{(\d*)\}/g, (_, n) => vals[(n ? Number(n) : ++i) - 1] ?? '');
        break;
      }
    }
    if (r === undefined) missing.add(core); else out = lead + r + tail;
  } else if (digits && /\d/.test(s) && AMOUNT.test(core)) out = num(s);
  cache.set(s, out);
  return out;
}

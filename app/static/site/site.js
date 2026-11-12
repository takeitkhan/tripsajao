// Trip Sajao public site. Two languages (text carries its Bengali in data-bn), no dependencies.
const KEY = 'kt.lang';
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
let lang = 'en';
try { const s = localStorage.getItem(KEY); lang = s === 'bn' || s === 'en' ? s : (navigator.language || '').startsWith('bn') ? 'bn' : 'en'; } catch { /* default */ }
const bnDigits = (s) => String(s).replace(/[0-9]/g, (d) => '০১২৩৪৫৬৭৮৯'[+d]);
const tr = (en, bn) => (lang === 'bn' && bn ? bn : en);
const num = (x) => (lang === 'bn' ? bnDigits(x) : String(x));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const rnd = (n) => Math.floor(Math.random() * n);

const ICONS = {
  building: '<path d="M4 21V8l8-5 8 5v13M9 21v-6h6v6M3 21h18"/>',
  hotel: '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M10 21v-4h4v4"/>',
  boat: '<path d="M3 15h18l-2.5 4.5h-13z"/><path d="M6 15v-5h9l3 5M9 10V6h4v4"/>',
  ticket: '<path d="M3 7h18v3a2 2 0 0 0 0 4v3H3v-3a2 2 0 0 0 0-4z"/><path d="M14 7v10" stroke-dasharray="2 3"/>',
  clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/>',

  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  timer: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.3"/>',
  link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
  swap: '<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-8 8"/>',
  shield: '<path d="M12 3 4 6v6c0 4.5 3.2 8 8 9 4.8-1 8-4.5 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  card: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3 10h18M7 15h4"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.5-3.6 3-5.5 6.5-5.5s6 1.9 6.5 5.5M16 4.8a3.5 3.5 0 0 1 0 6.4M18 14.8c2 .6 3.2 2.3 3.5 5.2"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  book: '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M16 7l3 3"/>',
  code: '<path d="m8 8-5 4 5 4M16 8l5 4-5 4M14 5l-4 14"/>',
};
const icons = (root = document) => $$('[data-ico]', root).forEach((e) => { e.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[e.dataset.ico] || ''}</svg>`; });

/* ---------- text in two languages ---------- */
function applyText(root = document) {
  $$('[data-bn]', root).forEach((e) => {
    if (e.dataset.en === undefined) e.dataset.en = e.textContent;
    e.textContent = lang === 'bn' ? e.dataset.bn : e.dataset.en;
  });
}
const setT = (el, en, bn) => { el.dataset.en = en; el.dataset.bn = bn; el.textContent = tr(en, bn); };

/* ---------- shared header, contact, footer ---------- */
const page = document.body.dataset.page, kindKey = document.body.dataset.kind;
const NAV = [['/resorts', 'Resorts', 'রিসোর্ট', 'resorts'], ['/hotels', 'Hotels', 'হোটেল', 'hotels'], ['/houseboats', 'Houseboats', 'হাউজবোট', 'houseboats'], ['/events', 'Events & tours', 'ইভেন্ট ও ট্যুর', 'events'],
  ['/#features', 'Features', 'ফিচার', ''], ['/#developers', 'Developers', 'ডেভেলপার', '']];
const navHtml = (cls) => NAV.map(([href, en, bn, k]) => `<a href="${href}"${k && k === kindKey ? ' class="on"' : ''} data-bn="${bn}">${esc(en).replace('&amp;', '&amp;')}</a>`).join('');
$('#site-header').innerHTML = `
<header class="top" id="top"><div class="top-in">
  <a class="logo" href="/" aria-label="Trip Sajao"><svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true"><circle cx="16" cy="16" r="15" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 4"/><path d="M8 21c4-1 5-8 9-8s3 6 7 5" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/><circle cx="24" cy="18" r="2.6" fill="currentColor"/></svg><span>Trip Sajao</span></a>
  <nav class="nav" id="nav" aria-label="Main">${navHtml()}</nav>
  <div class="top-act"><button class="lang" id="lang" type="button" aria-label="Language"><span data-l="en">EN</span><span data-l="bn">বাং</span></button>
    <a class="link-in" href="/admin/" data-bn="সাইন ইন">Sign in</a><a class="btn sm" href="/register/" data-bn="নিবন্ধন করুন">Register</a>
    <button class="burger" id="burger" type="button" aria-label="Menu" aria-expanded="false"><i></i><i></i></button></div>
</div></header>
<div class="sheet" id="sheet" aria-hidden="true">${navHtml()}<a class="btn" href="/register/" data-bn="আপনার ব্যবসা নিবন্ধন করুন">Register your business</a><a class="plain" href="/admin/" data-bn="সাইন ইন">Sign in</a></div>`;

$('#site-contact').outerHTML = `
<section class="final" id="contact"><div class="wrap final-in">
  <div><h2 data-bn="আপনার ব্যবসার কথা বলুন">Tell us about your business</h2>
    <p class="s" data-bn="আপনি কী চালান আর কী দরকার, লিখে পাঠান। আমরা আপনার সঙ্গে যোগাযোগ করব, দাম ও পরিকল্পনা নিয়েও কথা হবে।">Tell us what you run and what you need. We will get back to you, and we can talk about plans and pricing then.</p>
    <div class="cta"><a class="btn big" href="/register/" data-bn="সরাসরি নিবন্ধন করুন">Or register straight away</a></div></div>
  <form class="cform" id="cform" novalidate>
    <div class="two"><label><span data-bn="আপনার নাম">Your name</span><input name="name" required maxlength="120" autocomplete="name"></label>
    <label><span data-bn="ইমেইল">Email</span><input name="email" type="email" required maxlength="200" autocomplete="email"></label></div>
    <div class="two"><label><span data-bn="ফোন (ঐচ্ছিক)">Phone (optional)</span><input name="phone" maxlength="40" autocomplete="tel"></label>
    <label><span data-bn="আপনি কী চালান">What you run</span><select name="business_type"><option value="resort" data-bn="রিসোর্ট">Resort</option><option value="hotel" data-bn="হোটেল">Hotel</option><option value="houseboat" data-bn="হাউজবোট">Houseboat</option><option value="events" data-bn="ইভেন্ট বা ট্যুর">Events or tours</option><option value="agency" data-bn="ট্রাভেল এজেন্সি">Travel agency</option><option value="other" data-bn="অন্য কিছু">Something else</option></select></label></div>
    <label><span data-bn="বার্তা">Message</span><textarea name="message" required maxlength="2000"></textarea></label>
    <input class="hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
    <div id="cmsg" role="status" hidden></div>
    <button class="btn big" type="submit" data-bn="বার্তা পাঠান">Send message</button>
  </form></div></section>`;
$('#site-footer').innerHTML = `<footer><div class="wrap foot"><span><b style="color:#fff">Trip Sajao</b> · <span data-bn="রিসোর্ট, হোটেল, হাউজবোট ও ইভেন্টের ব্যবস্থাপনা">Management for resorts, hotels, houseboats and events</span></span>
<nav>${navHtml()}<a href="/admin/" data-bn="সাইন ইন">Sign in</a></nav></div></footer>`;

/* ---------- header behaviour ---------- */
const topEl = $('#top'), bar = $('#progress'), sheet = $('#sheet'), burger = $('#burger');
let lastY = 0;
function onScroll() {
  const y = scrollY, h = document.documentElement.scrollHeight - innerHeight;
  bar.style.transform = `scaleX(${h > 0 ? y / h : 0})`;
  topEl.classList.toggle('solid', y > 70);
  const open = sheet.classList.contains('open');
  topEl.classList.toggle('hide', !open && y > lastY + 4 && y > 420); if (y < lastY - 4) topEl.classList.remove('hide');
  lastY = y; journeyFill();
}
function menu(open) {
  sheet.classList.toggle('open', open); burger.setAttribute('aria-expanded', open); sheet.setAttribute('aria-hidden', !open);
  document.body.style.overflow = open ? 'hidden' : ''; if (open) topEl.classList.remove('hide');
}
burger.addEventListener('click', () => menu(!sheet.classList.contains('open')));
$$('a', sheet).forEach((a) => a.addEventListener('click', () => menu(false)));
addEventListener('keydown', (e) => { if (e.key === 'Escape') menu(false); });
$('#lang').addEventListener('click', () => { lang = lang === 'en' ? 'bn' : 'en'; try { localStorage.setItem(KEY, lang); } catch { /* not remembered */ } render(); });

/* ---------- the four boards ---------- */
const ST = ['av', 'bk', 'hd', 'mt'];
const KINDS = {
  resort: { c: '--resort', title: ['Hill resort · Building A', 'পাহাড়ি রিসোর্ট · ভবন ক'], sub: ['15 cottages on 3 floors', '৩ তলায় ১৫টি কটেজ'], unit: ['Cottage', 'কটেজ'] },
  hotel: { c: '--hotel', title: ['City hotel · Tower', 'শহরের হোটেল · টাওয়ার'], sub: ['30 rooms on 5 floors', '৫ তলায় ৩০টি রুম'], unit: ['Room', 'রুম'] },
  houseboat: { c: '--boat', title: ['Lake houseboat', 'লেকের হাউজবোট'], sub: ['6 cabins or the whole boat', '৬টি কেবিন বা পুরো বোট'], unit: ['Cabin', 'কেবিন'] },
  event: { c: '--event', title: ['Sajek 3-day trek', 'সাজেক ৩ দিনের ট্রেক'], sub: ['28 seats · 12 - 14 Dec', '২৮টি সিট · ১২–১৪ ডিসেম্বর'], unit: ['Seat', 'সিট'] },
};
let boardKind = 'resort', cells = [], seatState = { sold: 16, held: 3, total: 28 }, ticking = null;
function buildBoard(kind) {
  boardKind = kind; const b = $('#board'); cells = [];
  if (kind === 'resort') {
    let s = '<svg viewBox="0 0 420 252" role="img" aria-label="Resort building grid"><path class="shell" d="M14 54 210 12 406 54V240H14z"/>';
    for (let f = 0; f < 3; f++) for (let i = 0; i < 5; i++) s += `<g><rect class="cell" data-i="${cells.length}" x="${40 + i * 70}" y="${70 + f * 56}" width="60" height="42" rx="7"/><text x="${70 + i * 70}" y="${96 + f * 56}" text-anchor="middle">${String.fromCharCode(67 - f)}${i + 1}</text></g>`, cells.push(0);
    b.innerHTML = s + '</svg>';
  } else if (kind === 'hotel') {
    let s = '<svg viewBox="0 0 420 272" role="img" aria-label="Hotel floor board"><rect class="shell" x="14" y="10" width="392" height="254" rx="10"/>';
    for (let f = 0; f < 5; f++) { s += `<text x="26" y="${46 + f * 46}" style="fill:#7B8E8C">${5 - f}</text>`; for (let i = 0; i < 6; i++) s += `<g><rect class="cell" data-i="${cells.length}" x="${56 + i * 56}" y="${24 + f * 46}" width="48" height="32" rx="6"/><text x="${80 + i * 56}" y="${44 + f * 46}" text-anchor="middle">${(5 - f) * 100 + i + 1}</text></g>`, cells.push(0); }
    b.innerHTML = s + '</svg>';
  } else if (kind === 'houseboat') {
    let s = '<svg viewBox="0 0 560 300" role="img" aria-label="Houseboat layout"><path d="M14 196 74 266Q88 282 112 282H448Q472 282 486 266L546 196Z" fill="#fff" stroke="#C9D5D3" stroke-width="2"/><path d="M50 238H510" class="deck"/><path d="M62 104H498L476 76H84Z" fill="#E4EDEC" stroke="#C9D5D3" stroke-width="2"/>';
    for (let i = 0; i < 6; i++) s += `<g><rect class="cell" data-i="${cells.length}" x="${74 + i * 74}" y="112" width="66" height="76" rx="9"/><text x="${107 + i * 74}" y="156" text-anchor="middle">${tr('Cabin', 'কেবিন')} ${num(i + 1)}</text></g>`, cells.push(0);
    b.innerHTML = s + '</svg>';
  } else {
    b.innerHTML = `<div class="ev"><div class="ev-card"><b>${tr('Sajek 3-day trek', 'সাজেক ৩ দিনের ট্রেক')}</b><small>${tr('12 - 14 Dec · pickup from Dhaka', '১২–১৪ ডিসেম্বর · ঢাকা থেকে যাত্রা')}</small>
      <div class="seatbar"><i class="s1" id="sb1"></i><i class="s2" id="sb2"></i><i class="s3" id="sb3"></i></div><div class="seatrow"><span id="sr1"></span><span id="sr2"></span><span id="sr3"></span></div></div>
      <div class="ev-card"><b>${tr('Customer details first', 'আগে গ্রাহকের তথ্য')}</b><small>${tr('Then a 10-minute hold, then payment with a screenshot.', 'তারপর ১০ মিনিটের হোল্ড, তারপর স্ক্রিনশটসহ পেমেন্ট।')}</small></div></div>`;
    seatPaint();
  }
  if (cells.length) {
    $$('.cell', b).forEach((c, i) => { cells[i] = ST[0]; });
    const start = { resort: 'bk bk av hd av bk av av mt av hd av bk av av', hotel: 'bk av bk av av hd av bk av av mt av bk bk av av hd av av bk av av av bk av av hd av bk av av', houseboat: 'bk av hd av bk mt' }[kind].split(' ');
    const els = $$('.cell', b); start.slice(0, els.length).forEach((s, i) => { cells[i] = s; els[i].setAttribute('class', 'cell ' + s); });
  }
  const K = KINDS[kind]; $('#st-title').textContent = tr(...K.title); $('#st-sub').textContent = tr(...K.sub);
  $('#toast-t').textContent = tr('Live: this updates the moment anything changes.', 'লাইভ: কিছু বদলালেই এটা সঙ্গে সঙ্গে বদলায়।');
}
function seatPaint() {
  const { sold, held, total } = seatState, free = total - sold - held;
  if (!$('#sb1')) return;
  $('#sb1').style.width = (sold / total * 100) + '%'; $('#sb2').style.width = (held / total * 100) + '%'; $('#sb3').style.width = (free / total * 100) + '%';
  $('#sr1').textContent = `${num(sold)} ${tr('sold', 'বিক্রি')}`; $('#sr2').textContent = `${num(held)} ${tr('on hold', 'হোল্ডে')}`; $('#sr3').textContent = `${num(free)} ${tr('free', 'ফাঁকা')}`;
}
function toast(kind, text) { const t = $('#toast'); if (!t) return; const dot = $('i', t); dot.style.background = { av: 'var(--av)', bk: 'var(--bk)', hd: 'var(--hd)', mt: 'var(--mt)' }[kind] || 'var(--av)'; $('#toast-t').textContent = text; }
function tick() {
  if (!$('#board') || document.hidden) return;
  if (boardKind === 'event') {
    const s = seatState, free = s.total - s.sold - s.held, r = Math.random();
    if (s.held > 0 && r < .45) { s.held--; s.sold++; toast('bk', tr('Payment checked: 1 seat confirmed', 'পেমেন্ট যাচাই হলো: ১টি সিট নিশ্চিত')); }
    else if (s.held > 0 && r < .6) { s.held--; toast('av', tr('Hold ran out: the seat is free again', 'হোল্ডের সময় শেষ: সিটটি আবার ফাঁকা')); }
    else if (free > 0) { s.held++; toast('hd', tr('1 seat held for 10 minutes', '১টি সিট ১০ মিনিটের জন্য হোল্ডে')); }
    if (s.sold >= s.total - 2) s.sold = 14;
    seatPaint(); return;
  }
  const i = rnd(cells.length), cur = cells[i], K = KINDS[boardKind];
  const next = cur === 'av' ? 'hd' : cur === 'hd' ? (Math.random() < .7 ? 'bk' : 'av') : cur === 'bk' ? (Math.random() < .5 ? 'av' : 'bk') : 'av';
  if (next === cur) return; const el = $$('.cell', $('#board'))[i]; if (!el) return; cells[i] = next; el.setAttribute('class', 'cell ' + next);
  const label = `${tr(...K.unit)} ${num(i + 1)}`;
  toast(next, next === 'hd' ? tr(`${label} held for 10 minutes`, `${label} ১০ মিনিটের জন্য হোল্ডে`) : next === 'bk' ? tr(`${label} booked and paid`, `${label} বুক ও পেমেন্ট হয়েছে`) : tr(`${label} is free again`, `${label} আবার ফাঁকা`));
}

/* ---------- journey (home) ---------- */
function journeyFill() {
  const list = $('#journey-list'), fill = $('#jfill'); if (!list || !fill) return;
  const r = list.getBoundingClientRect(), mid = innerHeight * .55;
  fill.style.height = Math.max(0, Math.min(r.height - 40, mid - r.top - 20)) + 'px';
  $$('.j', list).forEach((j) => { j.classList.toggle('on', j.getBoundingClientRect().top < mid); });
}
function fillMini(id, pat) { const m = $(id); if (!m) return; m.innerHTML = Array.from({ length: 24 }, (_, i) => `<i class="${pat[i % pat.length] === 'av' ? '' : pat[i % pat.length]}"></i>`).join(''); }
let holdRun = 0;
function runHold() {
  const fg = $('#r-fg'), tx = $('#r-t'); if (!fg) return; const id = ++holdRun, t0 = performance.now(), D = reduce ? 1 : 8000;
  const mini = $$('#mini i'); const held = mini[7]; if (held) held.className = 'hd';
  (function f(now) {
    if (id !== holdRun) return; const p = Math.min(1, (now - t0) / D), sec = Math.round(600 * (1 - p));
    fg.style.strokeDashoffset = 327 * p; tx.textContent = num(`${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`);
    if (p < 1) requestAnimationFrame(f); else if (held) held.className = '';
  })(t0);
}
function payAnim() {
  const shot = $('#shot'); if (!shot) return; shot.classList.remove('done'); setT(shot, 'Payment screenshot', 'পেমেন্টের স্ক্রিনশট');
  const chip = $('#pay-chip'); chip.className = 'chip hd'; setT(chip, 'To check', 'যাচাই বাকি');
  setTimeout(() => { shot.classList.add('done'); setT(shot, 'Screenshot added ✓', 'স্ক্রিনশট যোগ হয়েছে ✓'); }, 1100);
  setTimeout(() => { chip.className = 'chip av'; setT(chip, 'Confirmed', 'নিশ্চিত'); }, 2400);
}

/* ---------- code sample ---------- */
const SNIP = {
  curl: () => `<span class="c"># ${tr('Free rooms and prices', 'ফাঁকা রুম ও দাম')}</span>\ncurl https://your-domain/api/v1/properties \\\n  -H <span class="s">"X-API-KEY: pk_live_..."</span> \\\n  -H <span class="s">"X-API-SECRET: sk_live_..."</span>\n\n<span class="c"># ${tr('Hold event seats for 10 minutes', 'ইভেন্টের সিট ১০ মিনিট হোল্ড')}</span>\ncurl -X POST https://your-domain/api/v1/events/{id}/hold \\\n  -H <span class="s">"X-API-KEY: pk_live_..."</span> -H <span class="s">"X-API-SECRET: sk_live_..."</span> \\\n  -d <span class="s">'{"seats": 2, "customer": {...}}'</span>`,
  js: () => `<span class="k">const</span> headers = {\n  <span class="s">'X-API-KEY'</span>: <span class="s">'pk_live_...'</span>,\n  <span class="s">'X-API-SECRET'</span>: <span class="s">'sk_live_...'</span>,\n};\n\n<span class="c">// ${tr('Free rooms and prices', 'ফাঁকা রুম ও দাম')}</span>\n<span class="k">const</span> rooms = <span class="k">await</span> fetch(<span class="s">'/api/v1/properties'</span>, { headers }).then(r => r.json());\n\n<span class="c">// ${tr('Hold event seats for 10 minutes', 'ইভেন্টের সিট ১০ মিনিট হোল্ড')}</span>\n<span class="k">await</span> fetch(<span class="s">\`/api/v1/events/\${id}/hold\`</span>, {\n  method: <span class="s">'POST'</span>, headers, body: JSON.stringify({ seats: 2, customer }),\n});`,
  py: () => `<span class="k">import</span> httpx\n\nheaders = {<span class="s">"X-API-KEY"</span>: <span class="s">"pk_live_..."</span>, <span class="s">"X-API-SECRET"</span>: <span class="s">"sk_live_..."</span>}\n\n<span class="c"># ${tr('Free rooms and prices', 'ফাঁকা রুম ও দাম')}</span>\nrooms = httpx.get(<span class="s">"https://your-domain/api/v1/properties"</span>, headers=headers).json()\n\n<span class="c"># ${tr('Hold event seats for 10 minutes', 'ইভেন্টের সিট ১০ মিনিট হোল্ড')}</span>\nhttpx.post(f<span class="s">"https://your-domain/api/v1/events/{id}/hold"</span>,\n           headers=headers, json={<span class="s">"seats"</span>: 2, <span class="s">"customer"</span>: customer})`,
};
let tab = 'curl';
const code = () => { const p = $('#cpre'); if (!p) return; p.innerHTML = SNIP[tab](); $$('#ctabs button').forEach((b) => b.classList.toggle('on', b.dataset.c === tab)); };

/* ---------- kind pages ---------- */
const P = (en, bn) => ({ en, bn });
const KP = {
  resort: { page: 'resorts', c: '--resort', title: P('Resort management | Trip Sajao', 'রিসোর্ট ব্যবস্থাপনা | Trip Sajao'), board: 'resort', live: 'resort',
    kicker: P('For resorts', 'রিসোর্টের জন্য'), h1: P('Every cottage and duplex, live on one building grid', 'প্রতিটি কটেজ ও ডুপ্লেক্স, এক ভবনের লাইভ গ্রিডে'),
    lead: P('See which rooms are free, held or booked across buildings and floors, and sell them without a double booking, whether the guest books on your site, through an agent or at the desk.', 'ভবন ও তলা ধরে কোন রুম ফাঁকা, হোল্ডে বা বুক করা, এক নজরে দেখুন। অতিথি আপনার সাইটে, এজেন্টের মাধ্যমে বা ডেস্কে যেভাবেই বুক করুন, ডাবল বুকিং হবে না।'),
    checks: [P('A building grid with floors and cottage names', 'তলা ও কটেজের নামসহ ভবনের গ্রিড'), P('Weekday, weekend, holiday and season prices', 'সপ্তাহের দিন, সপ্তাহান্ত, ছুটি ও মৌসুমের দাম'), P('Advance payment with a screenshot check', 'স্ক্রিনশট যাচাইসহ অগ্রিম পেমেন্ট'), P('Agents and partners paid commission automatically', 'এজেন্ট ও পার্টনারের কমিশন নিজে থেকে হিসাব')],
    mh: P('What a resort manager gets', 'রিসোর্ট ব্যবস্থাপক যা পান'), mp: P('The tools a resort needs on a normal Friday night.', 'একটা সাধারণ শুক্রবার রাতে রিসোর্টের যা যা দরকার।'),
    manage: [['grid', P('A live building board', 'লাইভ ভবন বোর্ড'), P('Cottages, duplexes and rooms on a grid by floor. Green, red, yellow and grey tell you the story.', 'তলা ধরে কটেজ, ডুপ্লেক্স ও রুম গ্রিডে। সবুজ, লাল, হলুদ আর ধূসর রঙেই সব বোঝা যায়।')],
      ['building', P('Cottages, duplexes, rooms', 'কটেজ, ডুপ্লেক্স, রুম'), P('Each unit has capacity, photos and its own amenities, like a fireplace or a hill view.', 'প্রতিটি ইউনিটের ধারণক্ষমতা, ছবি ও সুবিধা থাকে, যেমন ফায়ারপ্লেস বা পাহাড়ের দৃশ্য।')],
      ['tag', P('Prices that follow the calendar', 'ক্যালেন্ডার ধরে দাম'), P('Weekend, Eid and winter rates, with a night-by-night price quote for any dates.', 'সপ্তাহান্ত, ঈদ ও শীতের রেট এবং যেকোনো তারিখের জন্য রাত ধরে হিসাব।')],
      ['timer', P('No double bookings', 'ডাবল বুকিং নেই'), P('A cottage is held for 10 minutes while the guest pays, and frees itself if nothing arrives.', 'অতিথি পেমেন্ট করা পর্যন্ত কটেজ ১০ মিনিট আটকে থাকে, টাকা না এলে নিজেই ছাড়া পায়।')],
      ['link', P('Agents and MoU partners', 'এজেন্ট ও MoU পার্টনার'), P('Each partner gets a clean short link. Their bookings and commission add up in their own ledger.', 'প্রতিটি পার্টনারের পরিষ্কার ছোট লিংক। তাদের বুকিং ও কমিশন নিজের খাতায় জমা হয়।')],
      ['globe', P('Your own website', 'আপনার নিজের ওয়েবসাইট'), P('Rooms, prices, photos and blog come out through the API, so your site looks the way you want.', 'রুম, দাম, ছবি ও ব্লগ API দিয়ে আসে, তাই আপনার সাইট আপনার মতো দেখতে হয়।')]],
    fh: P('How a guest books a cottage', 'অতিথি যেভাবে কটেজ বুক করেন'), fp: P('Four steps, and every one is tracked.', 'চারটি ধাপ, প্রতিটিই হিসাবে থাকে।'),
    flow: [[P('Picks dates', 'তারিখ বাছেন'), P('Free cottages and the price for those nights appear.', 'ফাঁকা কটেজ আর ওই রাতের দাম দেখা যায়।')], [P('Cottage is held', 'কটেজ আটকে যায়'), P('Ten minutes to pay. Nobody else can take it.', 'পেমেন্টের জন্য ১০ মিনিট। আর কেউ নিতে পারে না।')], [P('Pays an advance', 'অগ্রিম পাঠান'), P('The guest adds the payment screenshot.', 'অতিথি পেমেন্টের স্ক্রিনশট যোগ করেন।')], [P('Owner confirms', 'মালিক নিশ্চিত করেন'), P('The booking is confirmed, the balance is due before check-in.', 'বুকিং নিশ্চিত হয়, বাকি টাকা চেক-ইনের আগে।')]],
    lh: P('Resorts on the platform now', 'এখন প্ল্যাটফর্মে থাকা রিসোর্ট'), lp: P('Real listings from businesses we feature.', 'আমাদের দেখানো ব্যবসাগুলোর আসল তালিকা।') },
  hotel: { page: 'hotels', c: '--hotel', title: P('Hotel management | Trip Sajao', 'হোটেল ব্যবস্থাপনা | Trip Sajao'), board: 'hotel', live: 'hotel',
    kicker: P('For hotels', 'হোটেলের জন্য'), h1: P('Every room, floor by floor, always up to date', 'প্রতিটি রুম, তলা ধরে, সব সময় হালনাগাদ'),
    lead: P('A room-number board for the front desk, daily rates that follow the season, and sales through agents and other agencies, all without a double booking.', 'ফ্রন্ট ডেস্কের জন্য রুম নম্বর অনুযায়ী বোর্ড, মৌসুম ধরে দৈনিক রেট এবং এজেন্ট ও অন্য এজেন্সির বিক্রি। কোথাও ডাবল বুকিং নেই।'),
    checks: [P('A floor and room-number board', 'তলা ও রুম নম্বর অনুযায়ী বোর্ড'), P('Daily rates, weekends and festival seasons', 'দৈনিক রেট, সপ্তাহান্ত ও উৎসবের মৌসুম'), P('Other agencies can resell your rooms at your price', 'অন্য এজেন্সি আপনার দামেই রুম বিক্রি করতে পারে'), P('Maintenance rooms are blocked from sale', 'রক্ষণাবেক্ষণের রুম বিক্রির বাইরে থাকে')],
    mh: P('What a hotel manager gets', 'হোটেল ব্যবস্থাপক যা পান'), mp: P('Everything at the front desk, in one console.', 'ফ্রন্ট ডেস্কের সবকিছু, এক কনসোলে।'),
    manage: [['hotel', P('A floor-by-floor board', 'তলা ধরে বোর্ড'), P('Every room by number, with its live state for any date.', 'প্রতিটি রুম নম্বর ধরে, যেকোনো তারিখের লাইভ অবস্থাসহ।')],
      ['tag', P('Daily and seasonal rates', 'দৈনিক ও মৌসুমি রেট'), P('Weekday and weekend prices, plus holiday and festival rules.', 'সপ্তাহের দিন ও সপ্তাহান্তের দাম, সঙ্গে ছুটি ও উৎসবের নিয়ম।')],
      ['card', P('Payments and cancellations', 'পেমেন্ট ও বাতিল'), P('Full or advance payment, a screenshot check, and a cancellation with a reason.', 'পূর্ণ বা অগ্রিম পেমেন্ট, স্ক্রিনশট যাচাই এবং কারণসহ বাতিল।')],
      ['swap', P('Reseller agreements', 'রিসেলার চুক্তি'), P('Let another agency sell your rooms. Commission is counted per night, with clear refund rules.', 'অন্য এজেন্সিকে রুম বিক্রি করতে দিন। কমিশন প্রতি রাত ধরে, ফেরতের নিয়ম পরিষ্কার।')],
      ['users', P('Guests and history', 'অতিথি ও ইতিহাস'), P('One profile per guest email, with every stay in one place.', 'প্রতি ইমেইলে একটি প্রোফাইল, সব থাকা এক জায়গায়।')],
      ['shield', P('Staff roles', 'স্টাফের ভূমিকা'), P('Managers and staff see only what their role allows.', 'ম্যানেজার ও স্টাফ শুধু নিজের ভূমিকার জিনিস দেখেন।')]],
    fh: P('How a guest books a room', 'অতিথি যেভাবে রুম বুক করেন'), fp: P('The same four steps, on your site, at the desk or through an agent.', 'একই চার ধাপ, আপনার সাইটে, ডেস্কে বা এজেন্টের মাধ্যমে।'),
    flow: [[P('Searches', 'খোঁজেন'), P('Free rooms and the bill for those nights.', 'ফাঁকা রুম আর ওই রাতগুলোর বিল।')], [P('Room is held', 'রুম আটকে যায়'), P('Ten minutes to pay. The room is off sale for others.', 'পেমেন্টে ১০ মিনিট। অন্যদের কাছে রুম বিক্রির বাইরে।')], [P('Pays', 'পেমেন্ট করেন'), P('In full or an advance, with a screenshot.', 'পুরো বা অগ্রিম, স্ক্রিনশটসহ।')], [P('Confirmed', 'নিশ্চিত'), P('The room turns red on the board and the guest is on file.', 'বোর্ডে রুম লাল হয় আর অতিথি তালিকায় যুক্ত হন।')]],
    lh: P('Hotels on the platform now', 'এখন প্ল্যাটফর্মে থাকা হোটেল'), lp: P('Real listings from businesses we feature.', 'আমাদের দেখানো ব্যবসাগুলোর আসল তালিকা।') },
  houseboat: { page: 'houseboats', c: '--boat', title: P('Houseboat management | Trip Sajao', 'হাউজবোট ব্যবস্থাপনা | Trip Sajao'), board: 'houseboat', live: 'houseboat',
    kicker: P('For houseboats', 'হাউজবোটের জন্য'), h1: P('Sell the whole boat or one cabin, never both by mistake', 'পুরো বোট বা একটি কেবিন বিক্রি করুন, ভুল করে দুটো নয়'),
    lead: P('Cabins are drawn on the hull with their live state. A whole-boat charter blocks every cabin, and a single cabin sale leaves the rest open.', 'নৌকার আকারে কেবিনগুলো লাইভ অবস্থাসহ দেখা যায়। পুরো বোট ভাড়া হলে সব কেবিন বন্ধ, একটি কেবিন বিক্রি হলে বাকিগুলো খোলা।'),
    checks: [P('A boat-shaped board with named cabins', 'নাম দেওয়া কেবিনসহ নৌকার আকারের বোর্ড'), P('Whole-boat charter or single cabins', 'পুরো বোট ভাড়া বা আলাদা কেবিন'), P('Seasonal prices for each cabin', 'প্রতিটি কেবিনের মৌসুমি দাম'), P('Boat, guide and driver vendors with rates', 'বোট, গাইড ও চালক ভেন্ডর, রেটসহ')],
    mh: P('What a houseboat owner gets', 'হাউজবোট মালিক যা পান'), mp: P('Rules that match how boats are really sold.', 'নৌকা যেভাবে সত্যিই বিক্রি হয়, নিয়মগুলো তার সঙ্গে মেলে।'),
    manage: [['boat', P('A boat-shaped board', 'নৌকার আকারের বোর্ড'), P('Each cabin sits on the hull with its name and live state.', 'প্রতিটি কেবিন নাম ও লাইভ অবস্থাসহ নৌকার ওপর বসে।')],
      ['swap', P('Charter or cabin', 'ভাড়া বা কেবিন'), P('A whole-boat booking conflicts with every cabin, so the same night is never sold twice.', 'পুরো বোটের বুকিং সব কেবিনের সঙ্গে মেলে না, তাই একই রাত দুবার বিক্রি হয় না।')],
      ['tag', P('Prices per cabin', 'কেবিন ধরে দাম'), P('Weekend, season and festival rates for the boat and for each cabin.', 'বোট ও প্রতিটি কেবিনের সপ্তাহান্ত, মৌসুম ও উৎসবের রেট।')],
      ['clipboard', P('Vendors and budgets', 'ভেন্ডর ও বাজেট'), P('Keep boat, cook and guide rates, and budget each trip cost.', 'বোট, রাঁধুনি ও গাইডের রেট রাখুন, আর প্রতিটি ট্রিপের খরচের বাজেট করুন।')],
      ['link', P('Agents and resellers', 'এজেন্ট ও রিসেলার'), P('Partners with short links, and agencies that resell your cabins.', 'ছোট লিংকওয়ালা পার্টনার এবং আপনার কেবিন রিসেল করা এজেন্সি।')],
      ['image', P('Photos and videos', 'ছবি ও ভিডিও'), P('One library for the boat, the cabins and the route.', 'বোট, কেবিন ও যাত্রাপথের জন্য একটাই লাইব্রেরি।')]],
    fh: P('How a guest books the boat', 'অতিথি যেভাবে বোট বুক করেন'), fp: P('Whole boat or a single cabin, the steps are the same.', 'পুরো বোট বা একটি কেবিন, ধাপ একই।'),
    flow: [[P('Chooses the boat or a cabin', 'বোট বা কেবিন বাছেন'), P('Only what is really free for those nights is shown.', 'ওই রাতগুলোতে যা সত্যিই ফাঁকা, শুধু তাই দেখা যায়।')], [P('Cabin is held', 'কেবিন আটকে যায়'), P('Ten minutes to pay. The whole boat is held if that was the choice.', 'পেমেন্টে ১০ মিনিট। পুরো বোট বাছলে পুরোটাই আটকে থাকে।')], [P('Pays an advance', 'অগ্রিম পাঠান'), P('A screenshot goes with the payment.', 'পেমেন্টের সঙ্গে স্ক্রিনশট যায়।')], [P('Owner confirms', 'মালিক নিশ্চিত করেন'), P('The cabins turn red on the hull.', 'নৌকার ওপর কেবিনগুলো লাল হয়।')]],
    lh: P('Houseboats on the platform now', 'এখন প্ল্যাটফর্মে থাকা হাউজবোট'), lp: P('Real listings from businesses we feature.', 'আমাদের দেখানো ব্যবসাগুলোর আসল তালিকা।') },
  events: { page: 'events', c: '--event', title: P('Events and tours | Trip Sajao', 'ইভেন্ট ও ট্যুর | Trip Sajao'), board: 'event', live: 'events',
    kicker: P('For events and tours', 'ইভেন্ট ও ট্যুরের জন্য'), h1: P('Dated trips and events, with seats that never oversell', 'তারিখভিত্তিক ট্যুর ও ইভেন্ট, যার সিট কখনও বেশি বিক্রি হয় না'),
    lead: P('Turn a package into a dated event, set the seats, and take bookings. A seat is held for 10 minutes, the guest pays with a screenshot, and your partners earn commission.', 'প্যাকেজ থেকে তারিখসহ ইভেন্ট বানান, সিট ঠিক করুন, বুকিং নিন। সিট ১০ মিনিট আটকে থাকে, অতিথি স্ক্রিনশটসহ পেমেন্ট করেন, আর আপনার পার্টনাররা কমিশন পান।'),
    checks: [P('Seat limits counted live, last seat included', 'সিট সীমা লাইভ গোনা হয়, শেষ সিটও'), P('Customer details first, then payment on a second page', 'আগে গ্রাহকের তথ্য, তারপর দ্বিতীয় পাতায় পেমেন্ট'), P('Itinerary, transport, what to bring and health rules', 'যাত্রাপথ, পরিবহন, কী আনতে হবে ও স্বাস্থ্যবিধি'), P('Partner commission per seat or by percent', 'প্রতি সিটে বা শতাংশে পার্টনারের কমিশন')],
    mh: P('What an event organiser gets', 'ইভেন্ট আয়োজক যা পান'), mp: P('From the package to the last seat on the bus.', 'প্যাকেজ থেকে বাসের শেষ সিট পর্যন্ত।'),
    manage: [['clipboard', P('Packages and events', 'প্যাকেজ ও ইভেন্ট'), P('Write a package once, then make as many dated events from it as you like.', 'একবার প্যাকেজ লিখুন, তা থেকে যত খুশি তারিখওয়ালা ইভেন্ট বানান।')],
      ['ticket', P('Seats and holds', 'সিট ও হোল্ড'), P('The event is locked while seats are held, so the last seat cannot be sold twice.', 'সিট হোল্ড করার সময় ইভেন্ট লক থাকে, তাই শেষ সিট দুবার বিক্রি হয় না।')],
      ['card', P('Manual payments, checked', 'ম্যানুয়াল পেমেন্ট, যাচাইসহ'), P('Guests attach a screenshot. You verify or reject each payment.', 'অতিথি স্ক্রিনশট যোগ করেন। আপনি প্রতিটি পেমেন্ট যাচাই বা বাতিল করেন।')],
      ['link', P('Partner commission', 'পার্টনার কমিশন'), P('Percent of the total or a flat amount per seat, reversed if the booking is cancelled.', 'মোটের শতাংশ বা প্রতি সিটে নির্দিষ্ট অঙ্ক, বুকিং বাতিল হলে তা ফেরত যায়।')],
      ['users', P('Customers', 'গ্রাহক'), P('The same customer record across events and room bookings.', 'ইভেন্ট ও রুম বুকিং জুড়ে একই গ্রাহক রেকর্ড।')],
      ['book', P('Vendors and budgets', 'ভেন্ডর ও বাজেট'), P('Buses, jeeps, guides and resorts with rates, and a budget for each trip.', 'বাস, জিপ, গাইড ও রিসোর্টের রেট এবং প্রতিটি ট্রিপের বাজেট।')]],
    fh: P('How a guest books a seat', 'অতিথি যেভাবে সিট বুক করেন'), fp: P('Details first, so we can hold the seat properly.', 'আগে তথ্য, যাতে সিট ঠিকভাবে আটকানো যায়।'),
    flow: [[P('Gives details', 'তথ্য দেন'), P('Name, contact and the number of seats.', 'নাম, যোগাযোগ ও সিটের সংখ্যা।')], [P('Seats are held', 'সিট আটকে যায়'), P('Ten minutes on the payment page.', 'পেমেন্টের পাতায় ১০ মিনিট।')], [P('Pays with a screenshot', 'স্ক্রিনশটসহ পেমেন্ট'), P('The payment goes to the organiser to check.', 'পেমেন্ট যাচাইয়ের জন্য আয়োজকের কাছে যায়।')], [P('Confirmed', 'নিশ্চিত'), P('Seats are sold and the partner is credited.', 'সিট বিক্রি হয় আর পার্টনারের হিসাবে কমিশন জমা হয়।')]],
    lh: P('Upcoming events on the platform', 'প্ল্যাটফর্মের আসন্ন ইভেন্ট'), lp: P('Real events from businesses we feature.', 'আমাদের দেখানো ব্যবসাগুলোর আসল ইভেন্ট।') },
};
const cur = (c) => (c === 'BDT' ? '৳' : c || '');
const fmtDate = (d) => { try { return new Date(d + 'T00:00:00').toLocaleDateString(lang === 'bn' ? 'bn-BD' : 'en-GB', { day: 'numeric', month: 'short' }); } catch { return d; } };
async function loadLive(k) {
  const grid = $('#l-grid'), note = $('#l-note'); if (!grid) return;
  const empty = () => { grid.innerHTML = `<div class="empty">${esc(tr('Live listings appear here as soon as a business is featured on the platform.', 'কোনো ব্যবসাকে প্ল্যাটফর্মে দেখানো শুরু হলেই লাইভ তালিকা এখানে আসবে।'))}</div>`; note.textContent = ''; };
  try {
    const r = await fetch(`/api/v1/public/showcase?kind=${KP[k].live}&limit=6`); if (!r.ok) throw new Error(r.status);
    const d = await r.json(); if (!d.items.length) return empty();
    grid.innerHTML = d.items.map((x) => {
      const img = x.image ? ` style="background-image:url('${esc(x.image)}')"` : '';
      if (k === 'events') return `<article class="lcard"><div class="ph"${img}></div><div class="tx"><h3>${esc(x.title)}</h3><small>${esc(x.location || '')} · ${num(fmtDate(x.starts_on))} - ${num(fmtDate(x.ends_on))}</small><div class="pr">${esc(cur(x.currency))} ${num(Number(x.price).toLocaleString('en-US'))} <span>${tr('per seat', 'প্রতি সিট')}${x.seats ? ' · ' + num(x.seats) + ' ' + tr('seats', 'সিট') : ''}</span></div><small>${esc(x.business)}</small></div></article>`;
      return `<article class="lcard"><div class="ph"${img}></div><div class="tx"><h3>${esc(x.name)}</h3><small>${esc(x.location || '')}</small><div class="pr">${x.from_price ? `${tr('From', 'শুরু')} ${esc(cur(x.currency))} ${num(Number(x.from_price).toLocaleString('en-US'))} <span>${tr('per night', 'প্রতি রাত')}</span>` : ''}</div><small>${num(x.units)} ${tr('units', 'ইউনিট')} · ${esc(x.business)}</small></div></article>`;
    }).join('');
    note.textContent = tr('Shown from the platform right now. Your own website would read the same data through the API.', 'প্ল্যাটফর্ম থেকে এই মুহূর্তে দেখানো হচ্ছে। আপনার নিজের ওয়েবসাইটও API দিয়ে একই ডেটা পড়বে।');
  } catch { empty(); }
}
function renderKind() {
  const k = KP[kindKey]; if (!k) return;
  document.title = tr(...[k.title.en, k.title.bn]);
  $('#k-kicker').textContent = tr(k.kicker.en, k.kicker.bn); $('#k-h1').textContent = tr(k.h1.en, k.h1.bn); $('#k-lead').textContent = tr(k.lead.en, k.lead.bn);
  $('#k-check').innerHTML = k.checks.map((c) => `<li>${esc(tr(c.en, c.bn))}</li>`).join('');
  $('#m-h').textContent = tr(k.mh.en, k.mh.bn); $('#m-p').textContent = tr(k.mp.en, k.mp.bn);
  $('#m-grid').innerHTML = k.manage.map(([i, t, p]) => `<article class="fcard"><span class="ico" data-ico="${i}"></span><h3>${esc(tr(t.en, t.bn))}</h3><p style="color:var(--muted);font-size:15.5px">${esc(tr(p.en, p.bn))}</p></article>`).join('');
  $('#f-h').textContent = tr(k.fh.en, k.fh.bn); $('#f-p').textContent = tr(k.fp.en, k.fp.bn);
  $('#f-list').innerHTML = k.flow.map(([t, p]) => `<li><h3>${esc(tr(t.en, t.bn))}</h3><p>${esc(tr(p.en, p.bn))}</p></li>`).join('');
  $('#l-h').textContent = tr(k.lh.en, k.lh.bn); $('#l-p').textContent = tr(k.lp.en, k.lp.bn);
  $('#o-list').innerHTML = Object.entries(KP).filter(([x]) => x !== kindKey).map(([, o]) => `<a href="/${o.page}" style="--c:var(${o.c})"><i></i>${esc(tr(...[{ resorts: ['Resorts', 'রিসোর্ট'], hotels: ['Hotels', 'হোটেল'], houseboats: ['Houseboats', 'হাউজবোট'], events: ['Events & tours', 'ইভেন্ট ও ট্যুর'] }[o.page]].flat()))}</a>`).join('');
  icons();
}

/* ---------- home pieces ---------- */
function bindHome() {
  const tabs = $('#stage-tabs'); if (!tabs) return; let auto = true;
  const pick = (k) => { $$('button', tabs).forEach((b) => b.setAttribute('aria-selected', b.dataset.k === k)); buildBoard(k); };
  $$('button', tabs).forEach((b) => b.addEventListener('click', () => { auto = false; pick(b.dataset.k); }));
  const order = ['resort', 'hotel', 'houseboat', 'event']; let n = 0;
  setInterval(() => { if (!auto || document.hidden) return; n = (n + 1) % 4; pick(order[n]); }, 7000);
  fillMini('#mini', ['av', 'bk', 'av', 'av', 'bk', 'mt', 'av', 'hd']); fillMini('#mini2', ['bk', 'bk', 'av', 'bk', 'hd', 'av', 'bk', 'mt']);
  $('#r-btn').addEventListener('click', runHold);
  const once = (el, fn) => { const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { fn(); io.disconnect(); } }, { threshold: .5 }); io.observe(el); };
  once($('.ring'), runHold); once($('#shot'), payAnim);
  const rt = $('#rtabs');
  $$('button', rt).forEach((b) => b.addEventListener('click', () => { $$('button', rt).forEach((x) => x.setAttribute('aria-selected', x === b)); $$('.rolebox').forEach((p) => p.classList.toggle('on', p.dataset.role === b.dataset.r)); }));
  $$('#ctabs button').forEach((b) => b.addEventListener('click', () => { tab = b.dataset.c; code(); }));
  $$('.fcard,.kind').forEach((e, i) => { if (!reduce) { e.classList.add('rv'); e.style.transitionDelay = (i % 4) * 60 + 'ms'; io2.observe(e); } });
}
const io2 = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io2.unobserve(e.target); } }), { threshold: .12 });

/* ---------- contact form ---------- */
$('#cform').addEventListener('submit', async (ev) => {
  ev.preventDefault(); const f = ev.target, m = $('#cmsg'), btn = $('button[type=submit]', f);
  const body = Object.fromEntries(new FormData(f)); body.lang = lang;
  const show = (ok, en, bn) => { m.hidden = false; m.className = ok ? 'ok' : 'bad'; m.textContent = tr(en, bn); };
  if (!body.name.trim() || !/^\S+@\S+\.\S+$/.test(body.email) || !body.message.trim()) return show(false, 'Please add your name, a valid email and a message.', 'আপনার নাম, সঠিক ইমেইল ও বার্তা দিন।');
  btn.disabled = true;
  try {
    const r = await fetch('/api/v1/public/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.status === 201) { f.reset(); show(true, 'Thank you. We have your message and will reply by email.', 'ধন্যবাদ। আপনার বার্তা পেয়েছি, ইমেইলে উত্তর দেব।'); }
    else if (r.status === 429) show(false, 'Too many messages just now. Please try again in a little while.', 'এখন অনেক বার্তা এসেছে। একটু পরে আবার চেষ্টা করুন।');
    else show(false, 'We could not send that. Please check the details and try again.', 'পাঠানো গেল না। তথ্য দেখে আবার চেষ্টা করুন।');
  } catch { show(false, 'No connection. Please try again.', 'সংযোগ নেই। আবার চেষ্টা করুন।'); }
  btn.disabled = false;
});

/* ---------- render everything for the current language ---------- */
function render() {
  document.documentElement.lang = lang;
  $$('.lang span').forEach((s) => s.classList.toggle('on', s.dataset.l === lang));
  applyText();
  if (page === 'kind') { renderKind(); buildBoard(KP[kindKey]?.board || 'resort'); loadLive(kindKey); }
  else { buildBoard($$('#stage-tabs button').find((b) => b.getAttribute('aria-selected') === 'true')?.dataset.k || 'resort'); code(); }
  icons(); applyText();
}
render();
if (page === 'home') bindHome();
setInterval(tick, 2400);
addEventListener('scroll', onScroll, { passive: true }); onScroll();

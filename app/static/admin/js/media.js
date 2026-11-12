import { t } from './i18n.js';
// Shared media tools: thumbnails, uploads with progress, and the "choose from library" popup
// that every photo / video field in the console opens.
import { get, post, upload } from './api.js';
import { perms } from './data.js';
import { h, icon, btn, inp, sel, modal, spinner, emptyState, errorBox, refreshIcons, reportError, debounce, toast } from './ui.js';

// ---------------------------------------------------------------- small helpers
export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1073741824) return `${(n / 1048576).toFixed(n < 10485760 ? 1 : 0)} MB`;
  return `${(n / 1073741824).toFixed(1)} GB`;
}
export function fmtDuration(s) {
  if (s == null) return '';
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, '0')}`;
}
export const csv = (s) => [...new Set(String(s || '').split(',').map((t) => t.trim()).filter(Boolean))];

let summaryCache = null;
export async function mediaSummary(force = false) {
  if (!summaryCache || force) summaryCache = await get('/media/summary');
  return summaryCache;
}

/** A square-ish preview of a photo or video. `asset` may also be a plain {type, url, thumbnail_url} item. */
export function thumb(asset, { eager = false } = {}) {
  const isVideo = asset.kind === 'VIDEO' || asset.type === 'video';
  const src = asset.thumbnail_url || (!isVideo ? asset.url : null);
  const box = h('div', { class: 'thumb' });
  if (src) box.append(h('img', { src, alt: asset.alt_text || asset.alt || asset.title || '', loading: eager ? 'eager' : 'lazy', decoding: 'async',
    onerror: (e) => { e.target.remove(); box.classList.add('broken'); if (!isVideo) box.append(icon('image-off')); refreshIcons(); } }));
  else if (!isVideo) box.append(icon('image'));            // a video without a preview shows just the play button
  if (isVideo) {
    box.append(h('span', { class: 'play', 'aria-hidden': 'true' }, icon('play')));
    if (asset.duration_seconds != null) box.append(h('span', { class: 'dur' }, fmtDuration(asset.duration_seconds)));
  }
  return box;
}

// ---------------------------------------------------------------- uploading
/** Why a file would be refused, judged in the browser so people get the answer before waiting for an upload. */
export function problemWith(file, s) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const img = ['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ext);
  const vid = ['mp4', 'mov', 'webm'].includes(ext);
  if (!img && !vid) return `${file.name}: use JPG, PNG, WEBP or GIF photos, or MP4, MOV or WEBM videos.`;
  if (file.size === 0) return `${file.name}: the file is empty.`;
  const max = vid ? s.max_video_bytes : s.max_image_bytes;
  if (file.size > max) return `${file.name}: ${fmtBytes(file.size)} is over the ${fmtBytes(max)} limit for ${vid ? 'videos' : 'photos'}.`;
  return null;
}

/** Shows one row per file with a progress bar. Resolves with the uploaded assets. */
export function uploadFiles(files, { tags = [], into, onAsset, kind = 'any' } = {}) {
  const run = async () => {
    const s = await mediaSummary();
    const done = [];
    for (const file of [...files]) {
      const bar = h('div', { class: 'bar' }, h('span'));
      const note = h('span', { class: 'note muted' }, 'Waiting');
      const row = h('div', { class: 'up-row' }, h('div', { class: 'up-name' }, file.name), bar, note);
      into?.append(row);
      const wrong = kind === 'image' && !/\.(jpe?g|png|webp|gif)$/i.test(file.name) ? `${file.name}: this field takes photos only.`
        : kind === 'video' && !/\.(mp4|mov|webm)$/i.test(file.name) ? `${file.name}: this field takes videos only.` : null;
      const bad = wrong || problemWith(file, s);
      if (bad) { row.classList.add('fail'); note.textContent = t(bad); continue; }
      const form = new FormData();
      form.append('file', file);
      if (tags.length) form.append('tags', tags.join(','));
      note.textContent = t('Uploading');
      try {
        const asset = await upload('/media', form, (p) => { bar.firstChild.style.width = `${Math.round(p * 100)}%`; if (p >= 1) note.textContent = t('Processing'); });
        bar.firstChild.style.width = '100%'; row.classList.add('done'); note.textContent = t('Done');
        setTimeout(() => row.remove(), 2500);
        done.push(asset); onAsset?.(asset);
      } catch (e) { row.classList.add('fail'); note.textContent = t(`${file.name}: ${e.message}`); }
    }
    mediaSummary(true).catch(() => {});
    return done;
  };
  return run();
}

/** Opens the operating system's file chooser. */
export function chooseFiles({ accept, multiple = true } = {}) {
  return new Promise((resolve) => {
    const input = h('input', { type: 'file', multiple, accept, hidden: true, 'aria-hidden': 'true', tabindex: '-1' });
    input.addEventListener('change', () => { resolve([...input.files]); input.remove(); });
    document.body.append(input);
    input.click();
  });
}

const ACCEPT = { image: '.jpg,.jpeg,.png,.webp,.gif', video: '.mp4,.mov,.webm', any: '.jpg,.jpeg,.png,.webp,.gif,.mp4,.mov,.webm' };

/** Make an element accept dropped files. */
export function dropTarget(el, onFiles) {
  let depth = 0;
  const has = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  el.addEventListener('dragenter', (e) => { if (has(e)) { depth++; el.classList.add('dragging'); e.preventDefault(); } });
  el.addEventListener('dragover', (e) => { if (has(e)) e.preventDefault(); });
  el.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; el.classList.remove('dragging'); } });
  el.addEventListener('drop', (e) => { if (!has(e)) return; e.preventDefault(); depth = 0; el.classList.remove('dragging'); onFiles([...e.dataTransfer.files]); });
}

// ---------------------------------------------------------------- add a video by link
export function addVideoLink() {
  return new Promise((resolve) => {
    let out = null;
    const url = inp({ placeholder: 'https://www.youtube.com/watch?v=...', 'aria-label': 'Video link' });
    const title = inp({ placeholder: 'Optional', maxlength: 200, 'aria-label': 'Title' });
    const m = modal({
      title: 'Add a video link', onClose: () => resolve(out),
      body: [h('p', { class: 'muted', style: { margin: 0 } }, 'Paste a YouTube or Vimeo link, or a direct link to an .mp4 or .webm file. Nothing is uploaded; your website plays it from there.'),
        h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Video link'), url),
        h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Title'), title)],
      actions: [btn('Cancel', { onClick: () => m.close() }),
        btn('Add video', { kind: 'primary', onClick: async () => {
          if (!url.value.trim()) throw new Error('Paste a video link first.');
          out = await post('/media/link', { url: url.value.trim(), ...(title.value.trim() ? { title: title.value.trim() } : {}) });
          m.close();
        } })],
    });
  });
}

// ---------------------------------------------------------------- the picker popup
/**
 * openPicker({ kind: 'image' | 'video' | 'any', multiple, title }) -> Promise<asset[] | null>
 * People can search, filter, upload new files (or drop them in) and pick one or several.
 */
export function openPicker({ kind = 'any', multiple = false, title } = {}) {
  return new Promise((resolve) => {
    const canWrite = perms.can('media:write');
    let result = null;
    const chosen = new Map();
    const st = { q: '', kind: kind === 'any' ? '' : kind.toUpperCase(), tag: '', offset: 0, total: 0, seq: 0 };
    const PAGE = 36;

    const search = inp({ type: 'search', placeholder: 'Search by name or tag', 'aria-label': 'Search media' });
    const kindSel = kind === 'any' ? sel([['', 'Photos and videos'], ['IMAGE', 'Photos'], ['VIDEO', 'Videos']], '', { 'aria-label': 'Type' }) : null;
    const tagSel = sel([['', 'Any tag']], '', { 'aria-label': 'Tag' });
    const grid = h('div', { class: 'media-grid', role: multiple ? 'group' : 'radiogroup', 'aria-label': 'Media library' });
    const more = h('div', { class: 'more' });
    const queue = h('div', { class: 'uploads' });
    const count = h('span', { class: 'muted' });
    const drop = h('div', { class: 'picker' });

    const useBtn = btn('Use selected', { kind: 'primary', onClick: () => { result = [...chosen.values()]; m.close(); } });
    const cancel = btn('Cancel', { onClick: () => m.close() });
    const m = modal({
      title: title || (kind === 'image' ? 'Choose a photo' : kind === 'video' ? 'Choose a video' : 'Choose photos and videos'),
      wide: true, body: drop, actions: [count, cancel, useBtn], onClose: () => resolve(result),
    });
    m.body.classList.add('picker-body');
    m.footer.classList.add('picker-foot');

    function syncFooter() {
      const n = chosen.size;
      useBtn.disabled = n === 0;
      count.textContent = t(n ? (multiple ? `${n} selected` : '1 selected') : (multiple ? 'Click to select several' : 'Click to select'));
      useBtn.lastChild.textContent = t(multiple && n > 1 ? `Use ${n} items` : 'Use selected');
    }

    function card(a) {
      const on = chosen.has(a.id);
      const b = h('button', { class: 'media-card' + (on ? ' on' : ''), type: 'button', role: multiple ? 'checkbox' : 'radio', 'aria-checked': String(on),
        'aria-label': `${a.kind === 'VIDEO' ? 'Video' : 'Photo'}: ${a.title}`, 'data-id': a.id,
        onclick: () => {
          if (chosen.has(a.id)) chosen.delete(a.id);
          else { if (!multiple) { chosen.clear(); grid.querySelectorAll('.media-card.on').forEach((x) => { x.classList.remove('on'); x.setAttribute('aria-checked', 'false'); }); } chosen.set(a.id, a); }
          const now = chosen.has(a.id); b.classList.toggle('on', now); b.setAttribute('aria-checked', String(now)); syncFooter();
        },
        ondblclick: () => { if (!multiple) { chosen.clear(); chosen.set(a.id, a); result = [a]; m.close(); } },
      }, thumb(a), h('span', { class: 'tick', 'aria-hidden': 'true' }, icon('check')), h('span', { class: 'cap' }, a.title));
      return b;
    }

    async function load(reset) {
      const mine = ++st.seq;
      if (reset) { st.offset = 0; grid.replaceChildren(spinner()); more.replaceChildren(); }
      try {
        const page = await get('/media', { limit: PAGE, offset: st.offset, kind: st.kind, q: st.q, tag: st.tag });
        if (mine !== st.seq) return;
        if (reset) grid.replaceChildren();
        st.total = page.total; st.offset += page.items.length;
        page.items.forEach((a) => grid.append(card(a)));
        if (!grid.children.length) {
          grid.replaceChildren(emptyState(st.q || st.tag || (kind === 'any' && st.kind) ? 'Nothing matches that search.'
            : canWrite ? 'Your library is empty. Upload your first file, or drop it here.' : 'Your library is empty.'));
        }
        more.replaceChildren(st.offset < st.total ? btn(`Show more (${st.total - st.offset} left)`, { onClick: () => load(false) }) : '');
        refreshIcons();
      } catch (e) { if (mine === st.seq) grid.replaceChildren(errorBox(e)); }
    }

    async function loadTags() {
      try {
        const tags = await get('/media/tags');
        tagSel.replaceChildren(h('option', { value: '' }, 'Any tag'), ...tags.map((t) => h('option', { value: t }, t)));
        tagSel.value = st.tag;
      } catch { /* tags are optional */ }
    }

    async function send(files) {
      if (!files.length) return;
      if (!canWrite) { toast('You can choose files, but not add new ones.', 'error'); return; }
      await uploadFiles(files, { into: queue, kind, onAsset: (a) => {
        if (!multiple) { chosen.clear(); grid.querySelectorAll('.media-card.on').forEach((x) => { x.classList.remove('on'); x.setAttribute('aria-checked', 'false'); }); }
        chosen.set(a.id, a);
        grid.querySelector('.empty, .spinner')?.remove();
        grid.prepend(card(a)); syncFooter(); refreshIcons();
      } });
      loadTags();
    }

    const bar = h('div', { class: 'picker-bar' },
      search, kindSel, tagSel,
      canWrite ? btn('Upload', { icon: 'upload', kind: 'primary', onClick: async () => send(await chooseFiles({ accept: ACCEPT[kind], multiple: true })) }) : null,
      canWrite && kind !== 'image' ? btn('Video link', { icon: 'link', onClick: async () => {
        const a = await addVideoLink();
        if (a) { if (!multiple) chosen.clear(); chosen.set(a.id, a); await load(true); syncFooter(); }
      } }) : null);
    drop.append(bar, queue, grid, more,
      h('p', { class: 'hint' }, canWrite ? `Drop files anywhere in this window to upload. Photos up to 15 MB, videos up to 300 MB.` : 'Choose from the files already in your library.'));
    if (canWrite) dropTarget(drop, send);

    search.addEventListener('input', debounce(() => { st.q = search.value.trim(); load(true); }, 250));
    kindSel?.addEventListener('change', () => { st.kind = kindSel.value; load(true); });
    tagSel.addEventListener('change', () => { st.tag = tagSel.value; load(true); });
    syncFooter(); load(true); loadTags();
    mediaSummary().then((s) => {
      const hint = drop.querySelector('.hint');
      if (hint && canWrite) hint.textContent = t(`Drop files anywhere in this window to upload. Photos up to ${fmtBytes(s.max_image_bytes)}, videos up to ${fmtBytes(s.max_video_bytes)}.`);
    }).catch(() => {});
  });
}

// ---------------------------------------------------------------- single-value field (cover image, logo)
/** A picture field: preview + "Choose" + the address underneath for anyone who wants to paste one. get() returns the URL. */
export function mediaField({ kind = 'image', value = '', placeholder = 'Choose from the library, or paste a link' } = {}) {
  const input = inp({ value, placeholder, 'aria-label': kind === 'video' ? 'Video address' : 'Image address' });
  const prev = h('div', { class: 'mf-prev', 'aria-hidden': 'true' });
  const draw = () => {
    const v = input.value.trim();
    prev.replaceChildren(v && /^https?:\/\//.test(v) ? thumb({ type: kind === 'video' ? 'video' : 'photo', url: v }, { eager: true }) : h('div', { class: 'thumb' }, icon(kind === 'video' ? 'film' : 'image')));
    refreshIcons();
  };
  const choose = btn(input.value.trim() ? 'Change' : 'Choose', { kind: 'sm', icon: 'images', onClick: async (_e, b) => {
    const r = await openPicker({ kind });
    if (r?.[0]) { input.value = r[0].url; b.lastChild.textContent = t('Change'); draw(); }
  } });
  const clear = btn('Remove', { kind: 'sm ghost', icon: 'x', onClick: () => { input.value = ''; choose.lastChild.textContent = t('Choose'); draw(); } });
  input.addEventListener('input', debounce(draw, 250));
  draw();
  return { el: h('div', { class: 'media-field' }, prev, h('div', { class: 'mf-side' }, h('div', { class: 'row' }, choose, clear), input)), get: () => input.value.trim() };
}

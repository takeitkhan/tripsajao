// Media library: every photo and video the business owns, in one place.
import { get, patch, del } from '../api.js';
import { h, icon, btn, field, fieldBox, inp, sel, area, modal, confirmDialog, pageHead, figures, emptyState, errorBox, spinner, refreshIcons, toast, debounce, copyBtn, fmtDate } from '../ui.js';
import { thumb, fmtBytes, fmtDuration, csv, mediaSummary, uploadFiles, chooseFiles, dropTarget, addVideoLink } from '../media.js';
import { withDocs } from '../docs.js';

export function render(ctx) {
  const canWrite = ctx.can('media:write');
  return h('div', {}, pageHead('Media library', 'Photos and videos for your properties and website. Upload once, use anywhere.'),
    withDocs('media', () => manage(canWrite)));
}

const KIND_LABEL = { IMAGE: 'Photo', VIDEO: 'Video' };

async function manage(canWrite) {
  const PAGE = 48;
  const st = { q: '', kind: '', tag: '', offset: 0, seq: 0 };
  const summary = await mediaSummary(true);
  const stats = h('div');
  const search = inp({ type: 'search', placeholder: 'Search by name or tag', 'aria-label': 'Search media' });
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Type' });
  const tagSel = sel([['', 'Any tag']], '', { 'aria-label': 'Tag' });
  const queue = h('div', { class: 'uploads' });
  const grid = h('div', { class: 'media-grid' });
  const more = h('div', { class: 'more' });
  const root = h('div', { class: 'stack' });

  async function drawStats() {
    const s = await mediaSummary(true);
    const pct = Math.min(100, Math.round((s.used_bytes / s.quota_bytes) * 100));
    stats.replaceChildren(figures([{ value: s.images, label: 'Photos' }, { value: s.videos, label: 'Videos' },
      { value: fmtBytes(s.used_bytes), label: `of ${fmtBytes(s.quota_bytes)} used` }]),
    h('div', { class: 'quota', role: 'img', 'aria-label': `${pct}% of storage used` }, h('span', { style: { width: pct + '%' }, class: pct > 90 ? 'hot' : '' })));
  }

  const kinds = [['', 'All'], ['IMAGE', 'Photos'], ['VIDEO', 'Videos']];
  const segBtns = kinds.map(([v, l]) => h('button', { type: 'button', 'aria-pressed': String(v === st.kind), onclick: () => { st.kind = v; segBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(kinds[i][0] === v))); load(true); } }, l));
  seg.append(...segBtns);

  function card(a) {
    const b = h('button', { class: 'media-card', type: 'button', 'aria-label': `${KIND_LABEL[a.kind]}: ${a.title}. Open details`, onclick: () => openAsset(a, canWrite, {
      saved: (n) => { Object.assign(a, n); b.replaceWith(card(a)); refreshIcons(); loadTags(); },
      removed: () => { b.remove(); if (!grid.children.length) load(true); drawStats(); loadTags(); },
    }) }, thumb(a), h('span', { class: 'cap' }, a.title),
    h('span', { class: 'meta' }, a.source === 'EXTERNAL' ? 'Link' : fmtBytes(a.size_bytes), a.width ? ` · ${a.width}×${a.height}` : ''));
    return b;
  }

  async function load(reset) {
    const mine = ++st.seq;
    if (reset) { st.offset = 0; grid.replaceChildren(spinner()); more.replaceChildren(); }
    try {
      const page = await get('/media', { limit: PAGE, offset: st.offset, kind: st.kind, q: st.q, tag: st.tag });
      if (mine !== st.seq) return;
      if (reset) grid.replaceChildren();
      st.offset += page.items.length;
      page.items.forEach((a) => grid.append(card(a)));
      if (!grid.children.length) {
        grid.replaceChildren(st.q || st.kind || st.tag ? emptyState('Nothing matches that search.')
          : emptyState(canWrite ? 'No photos or videos yet. Drop files here, or use Upload.' : 'No photos or videos yet.',
            canWrite ? btn('Upload files', { kind: 'primary', icon: 'upload', onClick: pick }) : null));
      }
      more.replaceChildren(st.offset < page.total ? btn(`Show more (${page.total - st.offset} left)`, { onClick: () => load(false) }) : '');
      refreshIcons();
    } catch (e) { if (mine === st.seq) grid.replaceChildren(errorBox(e)); }
  }
  async function loadTags() {
    try {
      const tags = await get('/media/tags');
      tagSel.replaceChildren(h('option', { value: '' }, 'Any tag'), ...tags.map((t) => h('option', { value: t }, t)));
      tagSel.value = tags.includes(st.tag) ? st.tag : '';
    } catch { /* optional */ }
  }

  async function send(files) {
    if (!files.length || !canWrite) return;
    await uploadFiles(files, { into: queue, onAsset: (a) => { grid.querySelector('.empty')?.remove(); grid.prepend(card(a)); refreshIcons(); } });
    drawStats(); loadTags();
  }
  const pick = async () => send(await chooseFiles({ accept: '.jpg,.jpeg,.png,.webp,.gif,.mp4,.mov,.webm' }));

  const bar = h('div', { class: 'picker-bar' }, search, seg, tagSel, h('span', { class: 'grow' }),
    canWrite ? btn('Video link', { icon: 'link', onClick: async () => { if (await addVideoLink()) { load(true); drawStats(); } } }) : null,
    canWrite ? btn('Upload', { kind: 'primary', icon: 'upload', onClick: pick }) : null);
  root.append(stats, bar, queue, grid, more,
    h('p', { class: 'hint' }, `Accepted: ${summary.allowed.images.join(', ')} photos up to ${fmtBytes(summary.max_image_bytes)}; ${summary.allowed.videos.join(', ')} videos up to ${fmtBytes(summary.max_video_bytes)}. Photos are cleaned of camera location data and scaled down to 4000 px.`));
  search.addEventListener('input', debounce(() => { st.q = search.value.trim(); load(true); }, 250));
  tagSel.addEventListener('change', () => { st.tag = tagSel.value; load(true); });
  if (canWrite) dropTarget(root, send);
  drawStats(); loadTags(); load(true);
  return root;
}

// ---------------------------------------------------------------- one file
function preview(a) {
  if (a.kind === 'IMAGE') return h('img', { class: 'big', src: a.url, alt: a.alt_text || a.title });
  if (a.embed_url) {
    return h('div', { class: 'embed' }, h('iframe', { src: a.embed_url, title: a.title, loading: 'lazy', allow: 'fullscreen; picture-in-picture', allowfullscreen: true,
      referrerpolicy: 'strict-origin-when-cross-origin', sandbox: 'allow-scripts allow-same-origin allow-presentation allow-popups' }));
  }
  return h('video', { class: 'big', controls: true, preload: 'metadata', ...(a.thumbnail_url ? { poster: a.thumbnail_url } : {}), src: a.url });
}

function openAsset(a, canWrite, { saved, removed }) {
  const title = inp({ value: a.title, maxlength: 200, readOnly: !canWrite });
  const alt = area({ rows: 2, maxlength: 300, value: a.alt_text || '', readOnly: !canWrite, placeholder: a.kind === 'IMAGE' ? 'Describe the picture for people who cannot see it' : 'Optional' });
  const tags = inp({ value: (a.tags || []).join(', '), placeholder: 'e.g. rooms, pool, winter', readOnly: !canWrite });
  const used = h('div', { class: 'muted' }, 'Checking where this is used…');
  let places = null;
  const facts = [['Type', KIND_LABEL[a.kind] + (a.provider && a.provider !== 'upload' ? ` (${a.provider === 'file' ? 'link to a file' : a.provider})` : '')],
    a.width ? ['Size', `${a.width} × ${a.height} px`] : null, a.duration_seconds != null ? ['Length', fmtDuration(a.duration_seconds)] : null,
    a.source === 'UPLOAD' ? ['File', `${fmtBytes(a.size_bytes)}${a.original_name ? ` · ${a.original_name}` : ''}`] : null, ['Added', fmtDate(a.created_at)]].filter(Boolean);

  get(`/media/${a.id}/usage`).then((u) => {
    places = u.places;
    used.replaceChildren(...(u.count ? [h('div', { class: 'field-label' }, `Used in ${u.count} place${u.count === 1 ? '' : 's'}`),
      h('ul', { class: 'plain' }, u.places.map((p) => h('li', {}, h('span', { class: 'chip' }, p.kind), ' ', p.name)))] : [h('span', { class: 'muted' }, 'Not used anywhere yet.')]));
  }).catch(() => { used.textContent = ''; });

  const m = modal({
    title: a.title, wide: true,
    body: h('div', { class: 'media-detail' },
      h('div', { class: 'md-view' }, preview(a)),
      h('div', { class: 'md-side stack-sm' },
        field('Name', title), field('Description', alt, a.kind === 'IMAGE' ? 'Shown when the picture cannot load, and read aloud by screen readers.' : null), field('Tags', tags, 'Separate with commas'),
        h('dl', { class: 'facts' }, facts.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
        fieldBox('Address', h('div', { class: 'row nowrap' }, inp({ value: a.url, readOnly: true, 'aria-label': 'File address', onfocus: (e) => e.target.select() }), copyBtn(a.url)), 'Use this on your own website.'), used)),
    actions: [
      canWrite ? btn('Delete', { kind: 'danger', icon: 'trash-2', onClick: async () => {
        const n = places?.length || 0;
        const ok = await confirmDialog(n ? `"${a.title}" is used in ${n} place${n === 1 ? '' : 's'}: ${places.slice(0, 4).map((p) => p.name).join(', ')}${n > 4 ? ', …' : ''}. If you delete it, those places will show a broken ${a.kind === 'IMAGE' ? 'picture' : 'video'}.`
          : `Delete "${a.title}"? This cannot be undone.`, { confirmText: n ? 'Delete anyway' : 'Delete', danger: true, title: 'Delete this file?' });
        if (!ok) return;
        await del(`/media/${a.id}${n ? '?force=true' : ''}`);
        toast('Deleted', 'ok'); m.close(); removed();
      } }) : null,
      h('span', { class: 'grow' }),
      btn(canWrite ? 'Cancel' : 'Close', { onClick: () => m.close() }),
      canWrite ? btn('Save changes', { kind: 'primary', onClick: async () => {
        if (!title.value.trim()) throw new Error('Give the file a name.');
        const n = await patch(`/media/${a.id}`, { title: title.value.trim(), alt_text: alt.value.trim() || null, tags: csv(tags.value) });
        toast('Saved', 'ok'); m.close(); saved(n);
      } }) : null],
  });
  m.footer.classList.add('picker-foot');
}

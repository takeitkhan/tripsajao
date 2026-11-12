import { get, post, put, del } from '../api.js';
import { h, btn, reportError, field, fieldBox, inp, area, sel, modal, confirmDialog, tabs, table, badge, pageHead, fmtDateTime, toLocalInput, toast, slugify } from '../ui.js';
import { mediaEditor, kvEditor } from '../components.js';
import { mediaField } from '../media.js';
import { withDocs } from '../docs.js';

const csv = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
const iso = (v) => (v ? new Date(v).toISOString() : null);

// Each builder returns { nodes, get() } for the type-specific payload fields.
const BUILDERS = {
  blog: (p = {}) => {
    const body = area({ rows: 10, value: p.body_markdown || '', placeholder: 'Write in Markdown' });
    const excerpt = inp({ value: p.excerpt || '', maxlength: 300 }); const cover = mediaField({ value: p.cover_image || '' });
    const tags = inp({ value: (p.tags || []).join(', ') }); const author = inp({ value: p.author || '' });
    return { nodes: [field('Post', body, 'Markdown is supported.'), h('div', { class: 'form-grid' }, field('Short summary', excerpt), fieldBox('Cover image', cover.el), field('Tags', tags, 'Separate with commas'), field('Author', author))],
      get: () => ({ body_markdown: body.value, excerpt: excerpt.value.trim() || null, cover_image: cover.get() || null, tags: csv(tags.value), author: author.value.trim() || null }) };
  },
  event: (p = {}) => {
    const starts = inp({ type: 'datetime-local', value: toLocalInput(p.starts_at) }); const ends = inp({ type: 'datetime-local', value: toLocalInput(p.ends_at) });
    const venue = inp({ value: p.venue || '' }); const cover = mediaField({ value: p.cover_image || '' }); const reg = inp({ value: p.registration_url || '', placeholder: 'https://...' });
    const desc = area({ rows: 6, value: p.description || '' });
    return { nodes: [h('div', { class: 'form-grid' }, field('Starts', starts), field('Ends', ends), field('Venue', venue), fieldBox('Cover image', cover.el), field('Registration link', reg)), field('Description', desc)],
      get: () => { if (!starts.value) throw new Error('Choose when the event starts.'); return { starts_at: iso(starts.value), ends_at: iso(ends.value), venue: venue.value.trim() || null, description: desc.value.trim() || null, cover_image: cover.get() || null, registration_url: reg.value.trim() || null }; } };
  },
  gallery: (p = {}) => {
    const media = mediaEditor(p.items || [{ type: 'photo', url: '', caption: '' }]);
    return { nodes: [h('div', {}, h('div', { class: 'field-label', style: { marginBottom: '8px' } }, 'Photos and videos'), media.el)],
      get: () => { const items = media.get(); if (!items.length) throw new Error('Add at least one photo or video.'); return { items }; } };
  },
  page: (p = {}) => {
    const body = area({ rows: 10, value: p.body_markdown || '' }); const st = inp({ value: p.seo_title || '' }); const sd = inp({ value: p.seo_description || '' });
    return { nodes: [field('Page content', body, 'Markdown is supported.'), h('div', { class: 'form-grid' }, field('Search title', st), field('Search description', sd))],
      get: () => ({ body_markdown: body.value, seo_title: st.value.trim() || null, seo_description: sd.value.trim() || null }) };
  },
  announcement: (p = {}) => {
    const msg = area({ rows: 3, value: p.message || '' }); const sev = sel([['info', 'Information'], ['warning', 'Warning'], ['critical', 'Urgent']], p.severity || 'info');
    const from = inp({ type: 'datetime-local', value: toLocalInput(p.starts_at) }); const to = inp({ type: 'datetime-local', value: toLocalInput(p.ends_at) });
    return { nodes: [field('Message', msg), h('div', { class: 'form-grid' }, field('Style', sev), field('Show from', from), field('Show until', to))],
      get: () => ({ message: msg.value.trim(), severity: sev.value, starts_at: iso(from.value), ends_at: iso(to.value) }) };
  },
};

// Events are not listed here: trips are published from packages under Events. The cms 'event' type still works through the API.
const SECTIONS = {
  company: ['Company', 'Your business details shown on your website: name, logo, contact, address and social links.'],
  blog: ['Blog posts', 'Articles for your website blog.', 'blog post'],
  gallery: ['Galleries', 'Photo and video galleries for your website.', 'gallery'],
  page: ['Pages', 'Pages such as About us, Terms or Contact.', 'page'],
  announcement: ['Announcements', 'Short notices shown across your website.', 'announcement'],
};
export const SECTION_LIST = Object.entries(SECTIONS).map(([id, v]) => ({ id, label: v[0] }));

function openEditor(type, noun, item, onSaved) {
  const title = inp({ value: item?.title || '', maxlength: 300 });
  const slug = inp({ value: item?.slug || '', maxlength: 150, placeholder: 'auto from the title' });
  let touched = !!item;
  slug.addEventListener('input', () => { touched = true; });
  title.addEventListener('input', () => { if (!touched) slug.value = slugify(title.value); });
  const status = sel([['DRAFT', 'Draft (hidden from your website)'], ['PUBLISHED', 'Published']], item?.status || 'DRAFT');
  const b = BUILDERS[type](item?.payload || {});
  const m = modal({
    title: item ? `Edit ${noun}` : `New ${noun}`, wide: true,
    body: [h('div', { class: 'form-grid' }, field('Title', title), field('Web address name', slug), field('Status', status)), ...b.nodes],
    actions: [btn('Cancel', { onClick: () => m.close() }),
      btn(item ? 'Save changes' : 'Create', { kind: 'primary', onClick: async () => {
        const body = { title: title.value.trim(), slug: slug.value.trim() || undefined, status: status.value, payload: b.get() };
        if (item) await put(`/cms/${type}/${item.id}`, body); else await post(`/cms/${type}`, body);
        toast('Saved', 'ok'); m.close(); onSaved();
      } })],
  });
}

function contentList(type, label, noun, canWrite) {
  const root = h('div'); const holder = h('div');
  async function load() {
    holder.replaceChildren(h('div', { class: 'spinner' }));
    const page = await get(`/cms/${type}`, { limit: 200 });
    holder.replaceChildren(table([
      { label: 'Title', render: (i) => h('b', {}, i.title) },
      { label: 'Address', render: (i) => h('code', {}, i.slug) },
      { label: 'Status', render: (i) => badge(i.status, i.status === 'PUBLISHED' ? 'Published' : 'Draft') },
      { label: 'Updated', render: (i) => fmtDateTime(i.updated_at) },
      { label: '', render: (i) => canWrite ? h('div', { class: 'actions' }, btn('Edit', { kind: 'sm', onClick: () => openEditor(type, noun, i, () => load().catch(reportError)) }),
        btn('Delete', { kind: 'sm danger', onClick: async () => { if (await confirmDialog(`Delete "${i.title}"? This cannot be undone.`, { confirmText: 'Delete', danger: true })) { await del(`/cms/${type}/${i.id}`); toast('Deleted', 'ok'); await load(); } } })) : null },
    ], page.items, { empty: `No ${label.toLowerCase()} yet. Published items appear on your website through the API.` }));
  }
  root.append(canWrite ? h('div', { class: 'toolbar' }, h('div', { style: { marginLeft: 'auto' } }, btn(`New ${noun}`, { kind: 'primary', icon: 'plus', onClick: () => openEditor(type, noun, null, () => load().catch(reportError)) }))) : null, holder);
  return load().then(() => root);
}

async function companyTab(canWrite) {
  const c = await get('/cms/company');
  const f = {
    name: inp({ value: c.name || '' }), tagline: inp({ value: c.tagline || '' }), logo_url: mediaField({ value: c.logo_url || '' }),
    email: inp({ type: 'email', value: c.email || '' }), phone: inp({ value: c.phone || '' }), address: inp({ value: c.address || '' }),
    currency: inp({ value: c.currency || '', maxlength: 3, placeholder: 'USD' }), timezone: inp({ value: c.timezone || '', placeholder: 'Asia/Dhaka' }),
  };
  const social = kvEditor(c.social || {}, 'Network, e.g. facebook');
  return h('div', { class: 'stack', style: { maxWidth: '820px' } },
    h('div', { class: 'form-grid' }, field('Business name', f.name), field('Tagline', f.tagline), fieldBox('Logo', f.logo_url.el), field('Email', f.email), field('Phone', f.phone), field('Address', f.address), field('Currency', f.currency), field('Time zone', f.timezone)),
    h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Social links'), social.el),
    canWrite ? h('div', {}, btn('Save company info', { kind: 'primary', onClick: async () => {
      const body = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, (el.get ? el.get() : el.value.trim()) || null]));
      if (body.currency) body.currency = body.currency.toUpperCase();
      await put('/cms/company', { ...body, social: social.get() }); toast('Company info saved', 'ok');
      document.dispatchEvent(new CustomEvent('kt:company', { detail: { name: body.name, logo: body.logo_url } }));
    } })) : null);
}

export function render(ctx) {
  const canWrite = ctx.can('cms:write');
  const id = SECTIONS[ctx.params.section] ? ctx.params.section : 'company';
  const [label, sub, noun] = SECTIONS[id];
  return h('div', {}, pageHead(label, sub), withDocs('cms', () => (id === 'company' ? companyTab(canWrite) : contentList(id, label, noun, canWrite))));
}

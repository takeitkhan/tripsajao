// "API documentation" tab shown inside every module. Content comes from GET /api/v1/docs/module/{name},
// which is generated from the live OpenAPI schema, so it always matches the real API.
import { get } from './api.js';
import { h, tabs, copyBtn, humanize } from './ui.js';

const SNIPPET_LABELS = { curl: 'cURL', javascript_fetch: 'JavaScript (fetch)', javascript_axios: 'JavaScript (axios)', python_requests: 'Python' };
const code = (t) => h('code', {}, t);

function codeBlock(text) {
  return h('div', { class: 'code-wrap' }, h('pre', { class: 'code' }, text), copyBtn(text, 'Copy', 'sm'));
}
const json = (v) => JSON.stringify(v, null, 2);

function snippetTabs(snippets) {
  const keys = Object.keys(snippets);
  const bar = h('div', { class: 'snip-tabs' });
  const panel = h('div');
  const btns = {};
  const show = (k) => {
    for (const x in btns) btns[x].setAttribute('aria-pressed', String(x === k));
    panel.replaceChildren(codeBlock(snippets[k]));
  };
  keys.forEach((k) => {
    btns[k] = h('button', { class: 'chip', type: 'button', onclick: () => show(k) }, SNIPPET_LABELS[k] || k);
    bar.append(btns[k]);
  });
  show(keys[0]);
  return h('div', {}, bar, panel);
}

function params(title, list) {
  if (!list.length) return null;
  return h('div', {}, h('h3', { style: { marginBottom: '6px' } }, title),
    h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, ['Name', 'Type', 'Required', 'Description'].map((t) => h('th', {}, t)))),
      h('tbody', {}, list.map((p) => h('tr', {}, h('td', {}, code(p.name)), h('td', {}, p.type), h('td', {}, p.required ? 'Yes' : 'No'), h('td', {}, p.description || '')))))));
}

function endpoint(e) {
  return h('details', { class: 'endpoint' },
    h('summary', {},
      h('span', { class: 'method m-' + e.method }, e.method),
      code(e.path),
      h('span', { class: 'muted' }, e.summary || '')),
    h('div', { class: 'endpoint-body' },
      e.description ? h('p', { style: { whiteSpace: 'pre-wrap', margin: 0 } }, e.description) : null,
      h('div', { class: 'row' },
        h('b', {}, 'Access:'), e.auth,
        e.required_scopes.length ? h('span', { class: 'chips' }, e.required_scopes.map((s) => h('span', { class: 'chip' }, s))) : null),
      params('Path parameters', e.path_params),
      params('Query parameters', e.query_params),
      e.request_body_example != null ? h('div', {}, h('h3', { style: { marginBottom: '6px' } }, 'Request body'), codeBlock(json(e.request_body_example))) : null,
      h('div', {}, h('h3', { style: { marginBottom: '6px' } }, `Response (${e.response_status})`), e.response_example != null ? codeBlock(json(e.response_example)) : h('p', { class: 'muted' }, 'No body.')),
      h('div', {}, h('h3', { style: { marginBottom: '6px' } }, 'Code'), snippetTabs(e.snippets))));
}

export async function renderDocs(module) {
  const d = await get(`/docs/module/${module}`);
  return h('div', { class: 'docs' },
    h('p', { style: { margin: 0 } }, d.description),
    h('div', { class: 'callout' }, h('b', {}, 'How to authenticate. '),
      'Send ', code('X-API-KEY'), ' and ', code('X-API-SECRET'), ' headers from your website or server. Create the pair under API access. Base URL: ', code(d.base_url), '.'),
    d.endpoints.length ? d.endpoints.map(endpoint) : h('p', { class: 'muted' }, `No endpoints found for ${humanize(module)}.`));
}

/** Wrap a module page: "Manage" tab + "API documentation" tab. */
export function withDocs(module, manage, { initial } = {}) {
  return tabs([
    { id: 'manage', label: 'Manage', render: manage },
    { id: 'docs', label: 'API documentation', render: () => renderDocs(module) },
  ], { initial });
}

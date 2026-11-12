// API client: bearer tokens in sessionStorage, single-flight refresh, readable errors.
const KEY = 'kt.tokens';

export const auth = {
  get tokens() { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } },
  set(t) { sessionStorage.setItem(KEY, JSON.stringify(t)); },
  clear() { sessionStorage.removeItem(KEY); },
};

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

let lostCb = null;
export const onAuthLost = (cb) => { lostCb = cb; };

function describe(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => {
      const where = (e.loc || []).filter((x) => x !== 'body' && x !== 'query').join(' > ');
      const msg = String(e.msg).replace(/^Value error, /, '');
      return where ? `${where}: ${msg}` : msg;
    }).join('; ');
  }
  return fallback || 'Request failed';
}

let refreshing = null;
async function refresh() {
  refreshing ||= (async () => {
    const t = auth.tokens;
    if (!t?.refresh_token) throw new ApiError(401, 'Session ended');
    const res = await fetch('/api/v1/auth/refresh', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: t.refresh_token }),
    });
    if (!res.ok) throw new ApiError(401, 'Session ended');
    auth.set(await res.json());
  })().finally(() => { refreshing = null; });
  return refreshing;
}

export async function api(method, path, { body, params, anonymous } = {}) {
  const url = new URL('/api/v1' + path, location.origin);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  }
  const run = () => fetch(url, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(!anonymous && auth.tokens ? { Authorization: 'Bearer ' + auth.tokens.access_token } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let res = await run();
  if (res.status === 401 && !anonymous && auth.tokens?.refresh_token) {
    try { await refresh(); } catch { auth.clear(); lostCb?.(); throw new ApiError(401, 'Your session ended. Sign in again.'); }
    res = await run();
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, describe(data?.detail, res.statusText));
  return data;
}

// Save a file the server builds (for example the customer list as CSV). Signed in the same way as every other call.
export async function download(path, params, filename) {
  const url = new URL('/api/v1' + path, location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  const run = () => fetch(url, { headers: auth.tokens ? { Authorization: 'Bearer ' + auth.tokens.access_token } : {} });
  let res = await run();
  if (res.status === 401 && auth.tokens?.refresh_token) {
    try { await refresh(); } catch { auth.clear(); lostCb?.(); throw new ApiError(401, 'Your session ended. Sign in again.'); }
    res = await run();
  }
  if (!res.ok) { const data = await res.json().catch(() => null); throw new ApiError(res.status, describe(data?.detail, res.statusText)); }
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = filename; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

// File upload with progress. fetch() cannot report upload progress, so this uses XMLHttpRequest.
export async function upload(path, form, onProgress) {
  const send = () => new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', '/api/v1' + path);
    if (auth.tokens) x.setRequestHeader('Authorization', 'Bearer ' + auth.tokens.access_token);
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(e.loaded / e.total); };
    x.onload = () => { let data = null; try { data = JSON.parse(x.responseText); } catch { /* not JSON */ } resolve({ status: x.status, data, text: x.statusText }); };
    x.onerror = () => reject(new ApiError(0, 'Network problem. Check your connection and try again.'));
    x.send(form);
  });
  let res = await send();
  if (res.status === 401 && auth.tokens?.refresh_token) {
    try { await refresh(); } catch { auth.clear(); lostCb?.(); throw new ApiError(401, 'Your session ended. Sign in again.'); }
    res = await send();
  }
  if (res.status < 200 || res.status >= 300) throw new ApiError(res.status, describe(res.data?.detail, res.text));
  return res.data;
}

export const get = (p, params) => api('GET', p, { params });
export const post = (p, body = {}) => api('POST', p, { body });
export const put = (p, body) => api('PUT', p, { body });
export const patch = (p, body) => api('PATCH', p, { body });
export const del = (p) => api('DELETE', p);

export async function login(domain, email, password, principal) {
  const tokens = await api('POST', '/auth/login', {
    body: { tenant_domain: domain.trim().toLowerCase(), email: email.trim(), password, principal },
    anonymous: true,
  });
  auth.set(tokens);
}

export async function logout() {
  const t = auth.tokens;
  auth.clear();
  if (t?.refresh_token) {
    try { await api('POST', '/auth/logout', { body: { refresh_token: t.refresh_token }, anonymous: true }); } catch { /* ignore */ }
  }
}

// Server-sent events via fetch, because EventSource cannot send an Authorization header.
export async function streamEvents(onEvent, signal, onOpen) {
  const t = auth.tokens;
  const res = await fetch('/api/v1/dashboard/visual/stream', {
    headers: { Authorization: 'Bearer ' + t.access_token }, signal,
  });
  if (!res.ok) throw new ApiError(res.status, 'Live updates are unavailable');
  onOpen?.();
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const line = chunk.split('\n').find((l) => l.startsWith('data:'));
      if (line) { try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* ignore */ } }
    }
  }
}

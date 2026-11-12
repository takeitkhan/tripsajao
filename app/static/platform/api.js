// Super admin API client. Separate token store from the business console, so the two can be open side by side.
const KEY = 'kt.platform.tokens';
export const auth = {
  get tokens() { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } },
  set(t) { sessionStorage.setItem(KEY, JSON.stringify(t)); },
  clear() { sessionStorage.removeItem(KEY); },
};
export class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }
let lostCb = null;
export const onAuthLost = (cb) => { lostCb = cb; };

const describe = (d, fb) => (typeof d === 'string' ? d : Array.isArray(d)
  ? d.map((e) => `${(e.loc || []).filter((x) => x !== 'body' && x !== 'query').join(' > ')}: ${String(e.msg).replace(/^Value error, /, '')}`).join('; ') : fb || 'Request failed');

let refreshing = null;
const refresh = () => (refreshing ||= (async () => {
  const t = auth.tokens;
  if (!t?.refresh_token) throw new ApiError(401, 'Session ended');
  const res = await fetch('/api/v1/platform/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: t.refresh_token }) });
  if (!res.ok) throw new ApiError(401, 'Session ended');
  auth.set(await res.json());
})().finally(() => { refreshing = null; }));

export async function api(method, path, { body, params, anonymous } = {}) {
  const url = new URL('/api/v1/platform' + path, location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  const run = () => fetch(url, { method, headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(!anonymous && auth.tokens ? { Authorization: 'Bearer ' + auth.tokens.access_token } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
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
export const get = (p, params) => api('GET', p, { params });
export const post = (p, body = {}) => api('POST', p, { body });
export const patch = (p, body) => api('PATCH', p, { body });

export async function login(email, password) {
  auth.set(await api('POST', '/auth/login', { body: { email: email.trim(), password }, anonymous: true }));
}
export async function logout() {
  const t = auth.tokens; auth.clear();
  if (t?.refresh_token) { try { await api('POST', '/auth/logout', { body: { refresh_token: t.refresh_token }, anonymous: true }); } catch { /* ignore */ } }
}

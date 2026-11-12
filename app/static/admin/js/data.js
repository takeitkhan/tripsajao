// Cached id -> name lookups so lists can show "Cabin 2 - Lotus Houseboat" instead of UUIDs.
import { get } from './api.js';

let cache = null;

export async function lookups(force = false) {
  if (cache && !force) return cache;
  const properties = (await get('/properties', { limit: 200, include_inactive: true })).items;
  const units = {};
  await Promise.all(properties.map(async (p) => {
    const page = await get(`/properties/${p.id}/units`, { limit: 200 });
    for (const u of page.items) units[u.id] = { ...u, property: p };
  }));
  let partners = {};
  try { partners = Object.fromEntries((await get('/partners', { limit: 200 })).items.map((p) => [p.id, p])); } catch { /* no partner access */ }
  cache = {
    propertyList: properties,
    properties: Object.fromEntries(properties.map((p) => [p.id, p])),
    units, partners,
  };
  return cache;
}

export const invalidate = () => { cache = null; };

export const unitLabel = (lk, id) => {
  const u = lk.units[id];
  return u ? `${u.unit_name} - ${u.property.name}` : 'Removed unit';
};

// Set by main.js after sign-in so shared widgets (the media picker) can hide actions the user may not take.
export const perms = { can: () => true };

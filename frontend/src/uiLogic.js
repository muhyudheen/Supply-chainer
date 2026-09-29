// Pure helpers used by the dashboard. No React here, so backend/tests/test_frontend.py can run them under Node.

// A whole, non-negative number typed into a count box, or null if the text isn't one (e.g. an emptied box).
export function parseCount(text) {
  const trimmed = String(text).trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

// The `overrides` body for /api/recommend. Only limits the user set are included: the backend keeps its
// defaults for missing keys, but a null would break its comparisons. Returns null when nothing is set.
// max_delay is compared with the route's total transit time in days, hence the input's name.
export function buildOverrides({ avoid = [], costCeiling = '', maxTransitDays = '' }) {
  const overrides = {};
  if (avoid.length > 0) overrides.avoid_chokepoints = [...avoid];
  const cost = parseCount(costCeiling);
  if (cost) overrides.cost_ceiling = cost;
  const days = parseCount(maxTransitDays);
  if (days) overrides.max_delay = days;
  return Object.keys(overrides).length > 0 ? overrides : null;
}

// Display names for hub ids (e.g. the response's closed_hubs), falling back to the id itself.
export function hubNames(ids, namesById) {
  return (ids ?? []).map(id => namesById[id] ?? id);
}

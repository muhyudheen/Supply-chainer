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

// The route card the user picked; the first card if the index is out of range (e.g. after a new search).
export function pickSelected(recommendations, index) {
  return recommendations[index] ?? recommendations[0] ?? null;
}

// What a route card shows for one leg. The reason is kept only when a scenario hit the leg: otherwise
// it is the backend's generic "no live news" text, which explains nothing.
export function legFacts(leg) {
  return {
    time: `${Math.round(leg.eta * 10) / 10}h`,
    cost: `$${leg.cost.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    threat: `${Math.round(leg.threat * 100)}%`,
    reason: leg.intel_source === 'SCENARIO' ? leg.reason : null,
  };
}

// Display names for hub ids (e.g. the response's closed_hubs), falling back to the id itself.
export function hubNames(ids, namesById) {
  return (ids ?? []).map(id => namesById[id] ?? id);
}

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

// How many legs of a route a scenario actually hit (the backend marks them intel_source SCENARIO).
export function scenarioLegCount(rec) {
  return (rec?.legs ?? []).filter(l => l.intel_source === 'SCENARIO').length;
}

// Header badge for the /ws engine status. null means no message yet; OFFLINE is set by App when the socket drops.
export function engineStatusView(status) {
  const s = status?.engine_status;
  if (!s) return { label: 'CONNECTING TO ENGINE', tone: 'muted', hint: 'Waiting for the first /ws status message' };
  if (s === 'FULLY OPERATIONAL') return { label: 'ENGINE OPERATIONAL', tone: 'ok', hint: 'NLP threat engine warmed up' };
  if (s === 'WARMING RISK ENGINE') return { label: 'WARMING RISK ENGINE', tone: 'warn', hint: 'Threat scores are not ready yet' };
  if (s === 'WARM-UP FAILED') return { label: 'NLP WARM-UP FAILED', tone: 'error', hint: 'The NLP threat engine failed to load; see the backend log' };
  if (s === 'OFFLINE') return { label: 'ENGINE OFFLINE', tone: 'error', hint: 'Lost the /ws connection; retrying' };
  return { label: s, tone: 'warn', hint: 'Unrecognised engine status' };
}

// Hub search URL with the query encoded, so "&", "#" or accents can't break the request (F3).
export function hubSearchUrl(query) {
  return `/api/hubs/search?q=${encodeURIComponent(query.trim())}`;
}

// Calls fn once, with the latest arguments, after `ms` without another call. .cancel() drops a pending call.
export function debounce(fn, ms) {
  let timer;
  const debounced = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
}

// Numbers requests so a slow, older reply can't overwrite a newer one: only the latest token is accepted.
export function createRequestGate() {
  let latest = 0;
  return { next: () => ++latest, isLatest: (token) => token === latest };
}

// What to send as origin/destination: the picked hub id, or else the typed text (the backend also resolves names).
export function endpointFor(hubId, typedText) {
  return hubId || typedText.trim();
}

// What the supplier table shows (F8), all from the backend's audit_trace: reliability after disruptions
// (0-100), the points a scenario took off it, the days it added to lead time, and the ranking score (0-100).
export function supplierFacts(s) {
  const t = s.audit_trace ?? {};
  return {
    reliability: Math.round((t.scores?.reliability ?? s.historical_reliability ?? 0) * 100),
    reliabilityPenalty: Math.round((t.penalties?.risk_inflation ?? 0) * 100),
    leadTimePenalty: Math.round((t.penalties?.lead_time_impact ?? 0) * 10) / 10,
    decisionScore: Math.round(s.decision_score * 100),
  };
}

// Display names for hub ids (e.g. the response's closed_hubs), falling back to the id itself.
export function hubNames(ids, namesById) {
  return (ids ?? []).map(id => namesById[id] ?? id);
}

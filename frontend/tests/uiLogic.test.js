// Run with: npm test --prefix frontend (Node's built-in test runner, no extra packages).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as ui from '../src/uiLogic.js';

const source = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8');

// F7: clearing an inventory box must not send null to /api/suppliers
test('F7: parseCount accepts whole non-negative numbers only', () => {
  for (const text of ['', 'abc', '-5', '12.5', '1e3']) assert.equal(ui.parseCount(text), null, text);
  assert.equal(ui.parseCount('0'), 0);
  assert.equal(ui.parseCount('1500'), 1500);
  assert.equal(ui.parseCount(' 42 '), 42);
});

test('F7: supplier page survives a failed or error response', () => {
  const src = source('SupplierIntelligence.jsx');
  assert.ok(!src.includes('parseInt('), 'inputs must not use parseInt');
  assert.ok(src.includes('data.suppliers ?? []'));
  assert.ok(src.includes('apiError(res, data)'));
});

// M13 follow-up: the backend now answers errors with 400/404 and an {error} body
test('apiError prefers the backend message and catches non-2xx replies without one', () => {
  assert.equal(ui.apiError({ ok: false, status: 400 }, { error: "Unknown scenario 'X'" }), "Unknown scenario 'X'");
  assert.equal(ui.apiError({ ok: false, status: 422 }, { detail: [] }), 'Request failed (HTTP 422)');
  assert.equal(ui.apiError({ ok: true, status: 200 }, { error: 'legacy 200 error' }), 'legacy 200 error');
  assert.equal(ui.apiError({ ok: true, status: 200 }, { suppliers: [] }), null);
});

test('both pages use apiError for their API replies', () => {
  for (const page of ['SupplierIntelligence.jsx', 'RouteRecommender.jsx'])
    assert.ok(source(page).includes('apiError(res, data)'), page);
});

// F2: "Strategic Overrides" must be real inputs sent to /api/recommend
test('F2: buildOverrides sends only the limits that are set', () => {
  assert.equal(ui.buildOverrides({ avoid: [], costCeiling: '', maxTransitDays: '' }), null);
  assert.deepEqual(
    ui.buildOverrides({ avoid: ['CHOKE-SUEZ'], costCeiling: '5000', maxTransitDays: '30' }),
    { avoid_chokepoints: ['CHOKE-SUEZ'], cost_ceiling: 5000, max_delay: 30 });
  // a blank or zero limit is left out, so the backend keeps its default instead of getting null
  assert.deepEqual(ui.buildOverrides({ avoid: [], costCeiling: '0', maxTransitDays: '12' }), { max_delay: 12 });
});

test('F2: closed hubs are named for the banner', () => {
  const names = { 'CHOKE-SUEZ': 'Suez Canal' };
  assert.deepEqual(ui.hubNames(['CHOKE-SUEZ', 'PORT-X'], names), ['Suez Canal', 'PORT-X']);
  assert.deepEqual(ui.hubNames(undefined, names), []);
});

test('F2: the fixed "Auto-bypass" text is gone and overrides are sent', () => {
  const src = source('RouteRecommender.jsx');
  assert.ok(!src.includes('Auto-bypass enabled'));
  assert.ok(src.includes('overrides: buildOverrides('));
  assert.ok(src.includes('closed_hubs'));
});

// F1: the audit panel follows the selected card, not always card #1
test('F1: pickSelected returns the chosen card, falling back to the first', () => {
  const recs = [{ persona: 'FASTEST' }, { persona: 'BALANCED' }, { persona: 'SAFEST' }];
  assert.equal(ui.pickSelected(recs, 2).persona, 'SAFEST');
  assert.equal(ui.pickSelected(recs, 7).persona, 'FASTEST'); // stale index after a smaller result
  assert.equal(ui.pickSelected([], 0), null);
});

test('F1: the audit panel no longer reads recommendations[0]', () => {
  const src = source('RouteRecommender.jsx');
  assert.ok(!src.includes('recommendations[0].audit_trace'));
  assert.ok(src.includes('selected.audit_trace'));
  assert.ok(src.includes('aria-pressed={idx === selectedIdx}'));
});

// F4: route cards explain each leg: time, cost, threat, and the scenario reason
test('F4: legFacts formats time, cost and threat, and keeps only scenario reasons', () => {
  const leg = { eta: 24.35, cost: 1234.5, threat: 0.05, reason: 'No live news for this corridor', intel_source: 'FALLBACK' };
  assert.deepEqual(ui.legFacts(leg), { time: '24.4h', cost: '$1,234.50', threat: '5%', reason: null });
  const hit = { eta: 264, cost: 900, threat: 1, reason: 'Suez Canal blocked', intel_source: 'SCENARIO' };
  assert.equal(ui.legFacts(hit).reason, 'Suez Canal blocked');
  assert.equal(ui.legFacts(hit).threat, '100%');
});

test('F4: route cards render the leg facts and the route threat', () => {
  const src = source('RouteRecommender.jsx');
  assert.ok(src.includes('legFacts(leg)'));
  assert.ok(src.includes('rec.threat_level'));
});

// F5: no hardcoded claims; only what the API returned
test('F5: scenarioLegCount counts the legs a scenario hit', () => {
  const rec = { legs: [{ intel_source: 'SCENARIO' }, { intel_source: 'FALLBACK' }, { intel_source: 'SCENARIO' }] };
  assert.equal(ui.scenarioLegCount(rec), 2);
  assert.equal(ui.scenarioLegCount(null), 0);
});

test('F5: the hardcoded claims are gone', () => {
  const src = source('RouteRecommender.jsx');
  for (const claim of ['ACTIVE GLOBAL DISRUPTION DETECTED', 'co-location miracles', 'TRUTH AUDIT VERIFIED', 'Strategic Truth Anchor'])
    assert.ok(!src.includes(claim), claim);
  assert.ok(src.includes('activeScenario'), 'the scenario banner comes from the response');
});

// F3: hub search is encoded, debounced, and ignores stale replies
test('F3: hubSearchUrl URL-encodes the query', () => {
  assert.equal(ui.hubSearchUrl(' São Paulo & Co#1 '), '/api/hubs/search?q=S%C3%A3o%20Paulo%20%26%20Co%231');
});

test('F3: debounce runs once, with the last arguments, after the pause', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const calls = [];
  const search = ui.debounce(q => calls.push(q), 250);
  search('ro'); search('rot'); search('rott');
  t.mock.timers.tick(249);
  assert.deepEqual(calls, []);
  t.mock.timers.tick(1);
  assert.deepEqual(calls, ['rott']);
  search('x'); search.cancel(); t.mock.timers.tick(500);
  assert.deepEqual(calls, ['rott']);
});

test('F3: a request gate only accepts the newest reply', () => {
  const gate = ui.createRequestGate();
  const older = gate.next(), newer = gate.next();
  assert.equal(gate.isLatest(older), false);
  assert.equal(gate.isLatest(newer), true);
});

test('F3: a typed name is sent when no suggestion was picked', () => {
  assert.equal(ui.endpointFor('PORT-ROTTERDAM', 'Rotterdam'), 'PORT-ROTTERDAM');
  assert.equal(ui.endpointFor('', '  Rotterdam '), 'Rotterdam');
  assert.equal(ui.endpointFor('', '  '), '');
});

test('F3: editing the box clears the chosen hub', () => {
  const src = source('RouteRecommender.jsx');
  assert.ok(src.includes('hubSearchUrl(') && !src.includes('search?q=${'));
  assert.ok(src.includes("setHub[type]('')"), 'editing the text must drop the hub picked earlier');
});

// F8: the supplier table shows the backend's reliability and penalties, not 1 - decision score
test('F8: supplierFacts reads reliability, penalties and decision score from the audit trace', () => {
  const hit = { decision_score: 0.614, audit_trace: {
    scores: { reliability: 0.66 }, penalties: { risk_inflation: 0.26, lead_time_impact: 5.0 } } };
  assert.deepEqual(ui.supplierFacts(hit), {
    reliability: 66, reliabilityPenalty: 26, leadTimePenalty: 5, decisionScore: 61 });
  const calm = { decision_score: 0.8, audit_trace: {
    scores: { reliability: 0.92 }, penalties: { risk_inflation: 0, lead_time_impact: 0 } } };
  assert.deepEqual(ui.supplierFacts(calm), {
    reliability: 92, reliabilityPenalty: 0, leadTimePenalty: 0, decisionScore: 80 });
});

test('F8: the fake "Risk Score" column is gone', () => {
  const src = source('SupplierIntelligence.jsx');
  assert.ok(!src.includes('Risk Score') && !src.includes('1 - s.decision_score'));
  assert.ok(src.includes('supplierFacts(s)'));
});

// F10: the /ws engine status is shown, including a failed NLP warm-up
test('F10: engineStatusView maps each /ws state to a label and tone', () => {
  assert.equal(ui.engineStatusView(null).tone, 'muted');
  assert.equal(ui.engineStatusView({ engine_status: 'FULLY OPERATIONAL' }).tone, 'ok');
  assert.equal(ui.engineStatusView({ engine_status: 'WARMING RISK ENGINE' }).tone, 'warn');
  const failed = ui.engineStatusView({ engine_status: 'WARM-UP FAILED' });
  assert.equal(failed.tone, 'error');
  assert.match(failed.label, /WARM-UP FAILED/);
  assert.equal(ui.engineStatusView({ engine_status: 'OFFLINE' }).tone, 'error');
});

test('F10: App passes the status down and both pages show it', () => {
  assert.ok(source('App.jsx').includes('engineStatus={status}'));
  for (const page of ['RouteRecommender.jsx', 'SupplierIntelligence.jsx'])
    assert.ok(source(page).includes('<EngineStatus status={engineStatus}'), page);
});

// Round 7 (R2): the delay model's output on the dashboard, read from the API, never computed here
const MODEL_CARD = {
  persona: 'SAFEST', adjusted_eta: 623.3, also_best_for: ['BALANCED'],
  eta_range: { p50: 623.3, p85: 801.8, p95: 1005.6 },
  audit_trace: {
    eta: { transit: 545.4, transfer: 0, scenario: 0, predicted_delay: 77.9 },
    delay_drivers: {
      quantile: 'p95', calm_transit_h: 96.4, total_h: 441.1,
      drivers: [
        { feature: 'cargo_handled', label: 'terminal dwell', hours: 175.3 },
        { feature: 'arrives_canal', label: 'canal queue', hours: 169.1 },
        { feature: 'chokepoint', label: 'chokepoint risk', hours: 0.3 },
        { feature: 'news', label: 'news', hours: 0 },
        { feature: 'weather', label: 'weather', hours: -0.2 },
      ],
    },
  },
};

test('R2: etaRange shows the p50/p85/p95 range the API sent', () => {
  assert.deepEqual(ui.etaRange(MODEL_CARD), { p50: '623.3h', p85: '801.8h', p95: '1,005.6h' });
  assert.equal(ui.etaRange({}), null);
});

test('R2: delayDrivers lists the biggest drivers and a table that adds up', () => {
  const d = ui.delayDrivers(MODEL_CARD);
  assert.equal(d.quantile, 'p95');
  assert.deepEqual(d.top, ['terminal dwell +175.3h', 'canal queue +169.1h']);
  assert.deepEqual(d.rows.map(r => r.value), ['96.4h', '+175.3h', '+169.1h', '+0.3h', '+0.0h', '−0.2h']);
  assert.equal(d.total, '441.1h');
  assert.equal(ui.delayDrivers({ audit_trace: {} }), null);
});

test('R2: legDelay shows a transit leg\'s p50 delay and where cargo is handled', () => {
  assert.deepEqual(ui.legDelay({ type: 'transit', delay: { p50: 34.6, p85: 90, p95: 150 }, cargo_handled: true }),
    { p50: '+34.6h', handled: true });
  assert.equal(ui.legDelay({ type: 'transfer', delay: { p50: 0, p85: 0, p95: 0 }, cargo_handled: false }), null);
});

test('R17: alsoBestFor names the personas that picked the same route', () => {
  assert.equal(ui.alsoBestFor(MODEL_CARD), 'Also the BALANCED choice');
  assert.equal(ui.alsoBestFor({ also_best_for: ['SAFEST', 'BALANCED'] }), 'Also the SAFEST and BALANCED choice');
  assert.equal(ui.alsoBestFor({ also_best_for: [] }), null);
});

test('M10: modelStatusView shows the real model and weather source from /api/status', () => {
  const v = ui.modelStatusView({
    delay_model: { trained_at: '2026-09-30T05:59:31+00:00', n_rows: 50000, coverage_p85: 0.855 },
    weather_source: 'offline (demo mode: not fetched)',
  });
  assert.deepEqual(v, { trained: '2026-09-30 05:59 UTC', rows: '50,000 simulated legs',
    coverage: '85.5%', weather: 'offline (demo mode: not fetched)' });
  assert.equal(ui.modelStatusView({}), null);
});

test('R2: the route page renders the model output and counts the predicted delay in the ETA audit', () => {
  const src = source('RouteRecommender.jsx');
  for (const call of ['etaRange(rec)', 'delayDrivers(rec)', 'legDelay(leg)', 'alsoBestFor(rec)',
    'delayDrivers(selected)', 'modelStatusView(', "fetch('/api/status')", 'audit_trace.eta.predicted_delay'])
    assert.ok(src.includes(call), call);
});

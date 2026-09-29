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
  assert.ok(src.includes('res.ok') && src.includes('data.error'));
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

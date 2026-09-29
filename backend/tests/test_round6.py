"""Round 6: supplier scoring (BUG_REPORT.md section 6)."""
import os

import pytest

from backend.engine.scenario_manager import ScenarioManager
from backend.engine.supplier_scorer import SupplierScorer

CATEGORIES = ["Electronics", "Raw Materials", "Chemicals"]


@pytest.fixture(scope="module")
def scorer():
    return SupplierScorer(os.path.join(os.path.dirname(__file__), "..", "data", "suppliers.json"))


def _by_name(ranked):
    return {s["name"]: s for s in ranked}


# P1: a supplier behind a disrupted chokepoint gets the delay the scenario announces (Suez: 240h = 10 days)
@pytest.mark.parametrize("sid, supplier", [("SUEZ_BLOCK", "Global Dynamics Manufacturing"),
                                           ("HORMUZ_CLOSURE", "Desert Tech Solutions")])
def test_p1_lead_time_penalty_is_the_scenario_delay(scorer, sid, supplier):
    delay_days = ScenarioManager.SCENARIOS[sid]["delay_hours"] / 24
    normal = _by_name(scorer.get_ranked_suppliers("Electronics", {}))[supplier]
    hit = _by_name(scorer.get_ranked_suppliers("Electronics", ScenarioManager().get_disruptions(sid)))[supplier]
    assert hit["audit_trace"]["penalties"]["lead_time_impact"] == pytest.approx(delay_days, abs=0.05)
    assert hit["effective_lead_time"] == pytest.approx(normal["effective_lead_time"] + delay_days, abs=0.05)


# P2: cost scores stay in 0..1, and a cheaper supplier never scores lower on cost
@pytest.mark.parametrize("category", CATEGORIES)
def test_p2_cost_score_in_range_and_ordered(scorer, category):
    ranked = scorer.get_ranked_suppliers(category, {})
    assert ranked
    for s in ranked:
        assert 0 <= s["audit_trace"]["scores"]["cost"] <= 1, (s["name"], s["audit_trace"]["scores"]["cost"])
    by_cost = sorted(ranked, key=lambda s: s["unit_cost"])
    scores = [s["audit_trace"]["scores"]["cost"] for s in by_cost]
    assert scores == sorted(scores, reverse=True)

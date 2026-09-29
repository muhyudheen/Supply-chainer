"""Round 5: explanations and persona cards (BUG_REPORT.md section 5). Runs without the NLP model."""
import re

import pytest

from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager


class _Pred:
    def warmup(self): pass


@pytest.fixture(scope="module")
def rr():
    return RouteRecommender(None, _Pred(), None, ScenarioManager(), demo_mode=True)


def _cards(rr, src, dst, scenario=None, mode="sea"):
    out = rr.recommend(src, dst, transport_preference=mode, scenario=scenario)
    return {r["persona"]: r for r in out["recommendations"]}


# R17: when personas pick the same route, the card says so instead of silently dropping them
def test_r17_every_persona_is_accounted_for(rr):
    cards = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")
    covered = set(cards) | {p for c in cards.values() for p in c["also_best_for"]}
    assert covered == {"FASTEST", "SAFEST", "BALANCED"}
    assert len(cards) < 3  # this trip has shared routes, so the merge is actually exercised


def test_r17_merged_card_explains_it(rr):
    for card in _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM").values():
        for p in card["also_best_for"]:
            assert p in card["explanation"]


# R18: explanation numbers are real comparisons between the routes, not formulas on one route
def test_r18_no_invented_percentages(rr):
    for scenario in [None, "RED_SEA_CONFLICT", "SUEZ_BLOCK"]:
        for card in _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM", scenario).values():
            assert "%" not in card["explanation"], card["explanation"]


def test_r18_safest_states_its_real_extra_time_and_cost(rr):
    cards = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM", "RED_SEA_CONFLICT")
    fast, safe = cards["FASTEST"], cards["SAFEST"]
    dt = safe["adjusted_eta"] - fast["adjusted_eta"]
    dc = safe["total_cost"] - fast["total_cost"]
    assert f"{dt:+.1f}h" in safe["explanation"], safe["explanation"]
    assert f"${abs(dc):,.0f}" in safe["explanation"], safe["explanation"]
    assert f"{fast['threat_level']}" in safe["explanation"] and f"{safe['threat_level']}" in safe["explanation"]


def test_r18_transfer_count_is_the_real_count(rr):
    for scenario in [None, "HORMUZ_CLOSURE"]:
        for card in _cards(rr, "PORT-JEBEL", "PORT-SHANGHAI", scenario).values():
            real = sum(leg["type"] == "transfer" for leg in card["legs"])
            said = re.search(r"(\d+) transfers?", card["explanation"])
            assert said and int(said.group(1)) == real, card["explanation"]


# S4: a scenario that doesn't close anything must not claim ships are rerouting
@pytest.mark.parametrize("sid", list(ScenarioManager.SCENARIOS))
def test_s4_only_closures_claim_rerouting(sid):
    s = ScenarioManager.SCENARIOS[sid]
    if s["threat_level"] < 1.0:
        assert "rerout" not in s["reason"].lower(), s["reason"]

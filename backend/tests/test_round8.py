"""Round 8: cargo type and priority (R6, N1, N2). Runs without the NLP model (demo mode).

The cargo rules are the organizers' MODE_PROFILES table (simplified rules, not real regulations).
"""
import pytest

from backend.engine.multimodal_network import MODE_PROFILES
from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager


class _Pred:
    def warmup(self): pass


@pytest.fixture(scope="module")
def rr():
    return RouteRecommender(None, _Pred(), None, ScenarioManager(), demo_mode=True)


def _modes(out):
    return {leg["mode"] for c in out["recommendations"] for leg in c["legs"] if leg["type"] == "transit"}


# N1: the rule table is read, and every rule says why
def test_n1_excluded_modes_come_from_mode_profiles():
    from backend.engine.multimodal_network import CARGO_REASONS, excluded_modes
    assert excluded_modes("hazardous_waste") == ["air"]
    assert excluded_modes("perishable_urgent") == ["sea"]
    assert excluded_modes("oversize_heavy") == ["road"]
    assert excluded_modes("general") == []
    restricted = {c for p in MODE_PROFILES.values() for c in p["cargo_restrictions"]}
    assert set(CARGO_REASONS) == restricted


def test_n1_hazardous_waste_never_flies(rr):
    assert "AIR" in _modes(rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM"))  # general cargo flies on this trip
    assert "AIR" not in _modes(rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", cargo_type="hazardous_waste"))


def test_n1_perishables_never_sail(rr):
    assert "SEA" in _modes(rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM"))
    assert "SEA" not in _modes(rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", cargo_type="perishable_urgent"))


def test_n1_oversize_loads_never_go_by_road(rr):
    assert "ROAD" in _modes(rr.recommend("PORT-CHENNAI", "HUB-CHENNAI"))
    out = rr.recommend("PORT-CHENNAI", "HUB-CHENNAI", cargo_type="oversize_heavy")
    assert "ROAD" not in _modes(out)


# R6: the response says which rules applied and why
def test_r6_response_reports_the_cargo_rules(rr):
    out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", cargo_type="hazardous_waste")
    rules = out["cargo_rules"]
    assert rules["cargo_type"] == "hazardous_waste" and rules["excluded_modes"] == ["air"]
    assert len(rules["reasons"]) == 1 and rules["reasons"][0].startswith("air: ")
    assert rules["priority"] == "normal" and rules["balanced_time_weight"] == 0.3


# R6: bad input is a clear 400; a rule that leaves no route is a 404 that names the rule
def test_r6_unknown_cargo_type_or_priority_is_400(rr):
    for kwargs in ({"cargo_type": "plutonium"}, {"priority": "asap"}):
        out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", **kwargs)
        assert out.get("status") == 400, out
    assert "hazardous_waste" in rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", cargo_type="plutonium")["error"]


def test_r6_mode_preference_that_the_cargo_forbids_is_400(rr):
    out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", transport_preference="sea", cargo_type="perishable_urgent")
    assert out.get("status") == 400 and "sea" in out["error"], out


def test_r6_no_route_left_names_the_rule(rr):
    out = rr.recommend("PORT-CHENNAI", "DC-KOCHI", cargo_type="oversize_heavy")  # DC-KOCHI is reachable by road only
    assert out.get("status") == 404 and "oversize_heavy" in out["error"] and "road" in out["error"], out


# N2: priority changes how much BALANCED weighs time (0.3 / PRIORITY_MULTIPLIERS)
def test_n2_priority_sets_balanced_time_weight(rr):
    weight = {p: rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", priority=p)["cargo_rules"]["balanced_time_weight"]
              for p in ("urgent", "normal", "low")}
    assert weight == {"urgent": 0.43, "normal": 0.3, "low": 0.25}


def test_n2_urgent_balanced_is_never_slower(rr):
    def balanced_eta(priority):
        cards = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", priority=priority)["recommendations"]
        return next(c for c in cards if c["persona"] == "BALANCED" or "BALANCED" in c["also_best_for"])["adjusted_eta"]
    assert balanced_eta("urgent") <= balanced_eta("normal") <= balanced_eta("low")

"""Round 3: disruption scenarios (BUG_REPORT.md section 2). Runs without the NLP model."""
import re

import pytest

from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager


class _Pred:
    def warmup(self): pass


@pytest.fixture(scope="module")
def rr():
    return RouteRecommender(None, _Pred(), None, ScenarioManager(), demo_mode=True)


def _routes(rr, src, dst, scenario=None, mode="any"):
    out = rr.recommend(src, dst, transport_preference=mode, scenario=scenario)
    assert "error" not in out, out.get("error")
    return {r["persona"]: r for r in out["recommendations"]}


def _stops(route):
    return [leg["to"] for leg in route["legs"] if leg["type"] == "transit"]


# R9: a scenario with threat 1.0 closes the chokepoint for every persona.
# Asia -> eastern Med shows it: the Cape detour costs more than the 240h delay, so ships sailed through the closed canal.
@pytest.mark.parametrize("mode", ["sea", "any"])
def test_r9_suez_block_closes_the_canal(rr, mode):
    routes = _routes(rr, "PORT-SHANGHAI", "PORT-PIRAEUS", "SUEZ_BLOCK", mode)
    for persona, route in routes.items():
        assert "CHOKE-SUEZ" not in _stops(route), persona


def test_r9_suez_block_sends_ships_round_the_cape(rr):
    route = _routes(rr, "PORT-SHANGHAI", "PORT-PIRAEUS", "SUEZ_BLOCK", "sea")["FASTEST"]
    assert "CHOKE-CAPEGOOD" in _stops(route)


def test_r9_hormuz_closure_keeps_ships_out_of_the_gulf(rr):
    for persona, route in _routes(rr, "PORT-JEBEL", "PORT-SHANGHAI", "HORMUZ_CLOSURE", "sea").items():
        assert "CHOKE-HORMUZ" not in _stops(route), persona


def test_r9_response_lists_the_closed_hubs(rr):
    out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", scenario="SUEZ_BLOCK")
    assert out["closed_hubs"] == ["CHOKE-SUEZ"]


# S2: a scenario only hits its own mode (a road flood doesn't slow ships)
def test_s2_road_flood_does_not_delay_ships(rr):
    normal = _routes(rr, "PORT-SINGAPORE", "PORT-CHENNAI", None, "sea")["FASTEST"]
    flood = _routes(rr, "PORT-SINGAPORE", "PORT-CHENNAI", "CHENNAI_FLOOD", "sea")["FASTEST"]
    assert flood["adjusted_eta"] == normal["adjusted_eta"]


def test_s2_road_flood_still_delays_trucks(rr):
    normal = _routes(rr, "PORT-CHENNAI", "HUB-CHENNAI", None, "road")["FASTEST"]
    flood = _routes(rr, "PORT-CHENNAI", "HUB-CHENNAI", "CHENNAI_FLOOD", "road")["FASTEST"]
    assert flood["adjusted_eta"] > normal["adjusted_eta"]


# S3: the delay a scenario applies matches the delay its text announces
@pytest.mark.parametrize("sid", list(ScenarioManager.SCENARIOS))
def test_s3_reason_text_matches_delay(sid):
    s = ScenarioManager.SCENARIOS[sid]
    for hours in re.findall(r"(\d+)\s*h\b", s["reason"]):
        assert int(hours) == s["delay_hours"], s["reason"]
    for days in re.findall(r"(\d+)-day", s["reason"]):
        assert int(days) * 24 == s["delay_hours"], s["reason"]


# M7: an unknown scenario is an error, not silently "no scenario"
def test_m7_unknown_scenario_is_an_error(rr):
    out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", scenario="SUEZ_BLOK")
    assert "error" in out and "SUEZ_BLOK" in out["error"]


# M14: a request must not write the scenario into state shared with other requests
def test_m14_recommend_does_not_touch_shared_scenario_state(rr):
    before = dict(vars(rr.scenario_mgr))
    rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", scenario="SUEZ_BLOCK")
    assert vars(rr.scenario_mgr) == before


def test_m14_disruptions_are_looked_up_per_request():
    mgr = ScenarioManager()
    suez = mgr.get_disruptions("SUEZ_BLOCK")
    mgr.get_disruptions("HORMUZ_CLOSURE")
    assert mgr.get_disruptions("SUEZ_BLOCK") == suez and "CHOKE-SUEZ" in suez
    assert mgr.get_disruptions(None) == {}

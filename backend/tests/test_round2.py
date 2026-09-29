"""Round 2: the route graph (BUG_REPORT.md section 3). Runs without the NLP model."""
import itertools

import pytest

from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager


class _Pred:
    def warmup(self): pass


@pytest.fixture(scope="module")
def rr():
    return RouteRecommender(None, _Pred(), None, ScenarioManager(), demo_mode=True)


def _sea(rr, src, dst, scenario=None):
    out = rr.recommend(src, dst, transport_preference="sea", scenario=scenario)
    assert "error" not in out, out.get("error")
    return {r["persona"]: r for r in out["recommendations"]}


def _stops(route):
    return [leg["to"] for leg in route["legs"] if leg["type"] == "transit"]


# N7: every transit link must work in both directions
def test_n7_every_transit_link_has_reverse(rr):
    G = rr.unified_graph
    missing = [(u, v) for u, v, d in G.edges(data=True) if d["type"] == "transit" and not G.has_edge(v, u)]
    assert missing == []


def test_n7_europe_to_asia_by_sea(rr):
    _sea(rr, "PORT-ROTTERDAM", "PORT-SHANGHAI")


# N9: chokepoints must be on the path, so scenarios on them take effect
def test_n9_every_chokepoint_can_be_entered(rr):
    G = rr.unified_graph
    assert [n for n in G if n.startswith("CHOKE-") and G.in_degree(n) == 0] == []


def test_n9_asia_europe_passes_malacca_babel_suez(rr):
    stops = _stops(_sea(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"])
    for choke in ["CHOKE-MALACCA", "CHOKE-BABEL", "CHOKE-SUEZ"]:
        assert choke in stops, stops


def test_n9_gulf_departure_passes_hormuz(rr):
    for port in ["PORT-JEBEL", "PORT-HAMAD"]:  # HAMAD had a feeder link that skipped Hormuz
        assert "CHOKE-HORMUZ" in _stops(_sea(rr, port, "PORT-COLOMBO")["FASTEST"]), port


def test_n9_hormuz_scenario_hits_gulf_departure(rr):
    route = _sea(rr, "PORT-JEBEL", "PORT-SHANGHAI", "HORMUZ_CLOSURE")["FASTEST"]
    assert any(leg["to"] == "CHOKE-HORMUZ" and leg["intel_source"] == "SCENARIO" for leg in route["legs"])


def test_n9_red_sea_scenario_affects_asia_europe(rr):
    normal = _sea(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    red = _sea(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM", "RED_SEA_CONFLICT")["FASTEST"]
    assert "CHOKE-BABEL" in _stops(normal)  # otherwise the scenario can't matter at all
    assert red["adjusted_eta"] > normal["adjusted_eta"] or "CHOKE-BABEL" not in _stops(red)


def test_n9_caspian_has_no_sea_route_to_the_ocean(rr):
    out = rr.recommend("PORT-BAKU", "PORT-ROTTERDAM", transport_preference="sea")
    assert "error" in out or all(
        "sea" not in {leg["mode"].lower() for leg in r["legs"]} for r in out["recommendations"])


# N4 (trunk): sea lanes go around land, so Shanghai -> Rotterdam is ~19,000 km, not 13,800 km
def test_n4_asia_europe_sea_time_is_realistic(rr):
    assert _sea(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]["adjusted_eta"] >= 480  # 35 km/h -> >= 16,800 km


# N11: the road auto-wire must not create roads across the sea
def test_n11_no_road_across_water(rr):
    G = rr.unified_graph
    water = [{"UK", "France"}, {"UK", "Netherlands"}, {"Morocco", "Spain"},
             {"Indonesia", "Singapore"}, {"Indonesia", "Malaysia"}]
    bad = [(u, v) for u, v, d in G.edges(data=True) if d["transport_mode"] == "road"
           and {G.nodes[u]["country"], G.nodes[v]["country"]} in water]
    assert bad == []


# N10: no self-loops or zero-length transit legs
def test_n10_no_zero_length_or_self_loop_legs(rr):
    G = rr.unified_graph
    bad = [(u, v) for u, v, d in G.edges(data=True) if d["type"] == "transit"
           and (G.nodes[u]["physical_id"] == G.nodes[v]["physical_id"] or d["distance"] < 1)]
    assert bad == []


# L1: a port-to-port sea trip starts and ends on the ship, so it pays no truck handoffs
def test_l1_port_to_port_sea_has_no_handoffs(rr):
    route = _sea(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    assert route["audit_trace"]["eta"]["transfer"] == 0

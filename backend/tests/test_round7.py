"""Round 7 step 3: the delay model wired into routing (R2), ETA ranges, SHAP delay drivers, live weather, TI15.

FASTEST adds each leg's p50 delay, BALANCED p85, SAFEST p95. Runs without the NLP model (demo mode).
"""
import os

import numpy as np
import pytest

from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager
from backend.ml.features import leg_features

QUANTILE_OF = {"FASTEST": "p50", "BALANCED": "p85", "SAFEST": "p95"}
TRIPS = [("PORT-SHANGHAI", "PORT-ROTTERDAM", None, "sea"),
         ("PORT-SHANGHAI", "PORT-ROTTERDAM", "RED_SEA_CONFLICT", "sea"),
         ("PORT-JEBEL", "PORT-SHANGHAI", "HORMUZ_CLOSURE", "sea"),
         ("PORT-CHENNAI", "HUB-CHENNAI", "CHENNAI_FLOOD", "road")]


class _Pred:
    def warmup(self): pass


def _new_rr():
    return RouteRecommender(None, _Pred(), None, ScenarioManager(), demo_mode=True)


@pytest.fixture(scope="module")
def rr():
    return _new_rr()


def _cards(rr, src, dst, scenario=None, mode="sea"):
    out = rr.recommend(src, dst, transport_preference=mode, scenario=scenario)
    return {r["persona"]: r for r in out["recommendations"]}


def _all_cards(rr):
    return [c for trip in TRIPS for c in _cards(rr, *trip).values()]


def _node(leg, end):
    return f"{leg[end]}:{leg['mode'].lower()}"


# R2: every card's ETA carries its persona's quantile of the model's delay
def test_r2_each_persona_adds_its_quantile(rr):
    for card in _all_cards(rr):
        q = QUANTILE_OF[card["persona"]]
        predicted = card["audit_trace"]["eta"]["predicted_delay"]
        assert predicted == pytest.approx(sum(leg["delay"][q] for leg in card["legs"]), abs=0.5)
        assert card["adjusted_eta"] == pytest.approx(card["eta_range"][q], abs=0.2)


def test_r2_route_choice_follows_the_model():
    """Make the model predict a huge delay into Suez: FASTEST must stop sailing through it."""
    rr = _new_rr()
    before = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    assert "CHOKE-SUEZ" in [leg["to"] for leg in before["legs"]]
    for u in rr.unified_graph.predecessors("CHOKE-SUEZ:sea"):
        rr.unified_graph[u]["CHOKE-SUEZ:sea"]["delay_q"] = {False: (5000.0,) * 3, True: (5000.0,) * 3}
    after = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    assert "CHOKE-SUEZ" not in [leg["to"] for leg in after["legs"]]


# ETA range on every card: ordered, never below the schedule, and a sane share of the voyage
def test_eta_range_is_ordered_and_above_the_schedule(rr):
    for card in _all_cards(rr):
        r, eta = card["eta_range"], card["audit_trace"]["eta"]
        assert r["p50"] <= r["p85"] <= r["p95"]
        assert r["p50"] >= eta["transit"] + eta["transfer"] + eta["scenario"] - 0.1


def test_shanghai_rotterdam_p50_is_under_a_quarter_more_than_the_voyage(rr):
    fastest = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    assert 545.1 < fastest["eta_range"]["p50"] < 1.25 * 545.1


def test_explanation_states_the_range(rr):
    for card in _all_cards(rr):
        r = card["eta_range"]
        assert f"p50 {r['p50']}h, p85 {r['p85']}h, p95 {r['p95']}h" in card["explanation"], card["explanation"]


# Legs: cargo is handled where the next step is a transfer or the trip ends, and the delay is the model's
def test_legs_know_where_cargo_is_handled(rr):
    for card in _all_cards(rr):
        legs = card["legs"]
        for i, leg in enumerate(legs):
            if leg["type"] != "transit":
                assert leg["cargo_handled"] is False and leg["delay"] == {"p50": 0.0, "p85": 0.0, "p95": 0.0}
                continue
            ends_trip_or_transfers = i == len(legs) - 1 or legs[i + 1]["type"] == "transfer"
            assert leg["cargo_handled"] is ends_trip_or_transfers, (card["persona"], i, leg)


def test_leg_delay_is_the_models_prediction(rr):
    card = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    G = rr.unified_graph
    for leg in card["legs"]:
        f = leg_features(G, _node(leg, "from"), _node(leg, "to"), cargo_handled=leg["cargo_handled"])
        p50, p85, p95 = rr.delay_model.predict([f])[0]
        assert leg["delay"] == {"p50": round(p50, 1), "p85": round(p85, 1), "p95": round(p95, 1)}


# SHAP: the delay drivers are exact Shapley values against the same leg in calm conditions, and add up
def test_shap_drivers_add_up_to_the_models_delay(rr):
    for card in _all_cards(rr):
        d = card["audit_trace"]["delay_drivers"]
        assert d["quantile"] == QUANTILE_OF[card["persona"]]
        assert {x["feature"] for x in d["drivers"]} == {"cargo_handled", "arrives_canal", "chokepoint", "weather", "news"}
        assert d["calm_transit_h"] + sum(x["hours"] for x in d["drivers"]) == pytest.approx(d["total_h"], abs=0.1)
        assert d["total_h"] == pytest.approx(card["audit_trace"]["eta"]["predicted_delay"], rel=0.05, abs=1.0)


def test_shap_values_equal_the_shap_librarys(rr):
    shap = pytest.importorskip("shap")
    from backend.ml.predictor import CALM, VARYING
    from backend.ml.train import encode, encoded_columns
    m = rr.delay_model
    cols = encoded_columns(m.bundle)
    G = rr.unified_graph
    card = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    rows = [leg_features(G, _node(l, "from"), _node(l, "to"), cargo_handled=l["cargo_handled"], weather=0.6)
            for l in card["legs"]]
    calm_h, phi = m.explain(rows, q=1)
    for i, row in enumerate(rows):
        ref = encode(m.bundle, [{**row, **CALM}])
        e = shap.TreeExplainer(m.bundle["models"][1], data=ref, feature_perturbation="interventional")
        sv = e.shap_values(encode(m.bundle, [row]))[0]
        for f in VARYING:
            assert phi[f][i] == pytest.approx(sv[cols.index(f)], abs=1e-3), (i, f)


# Weather: live severity raises the delay; offline means exactly 0, never an invented value
def test_storm_weather_raises_the_delay():
    rr = _new_rr()
    calm = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    rr.set_weather({h: 0.9 for h in {d["physical_id"] for _, d in rr.unified_graph.nodes(data=True)}}, "test storm")
    storm = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]
    assert storm["eta_range"]["p85"] > calm["eta_range"]["p85"]
    weather = next(x for x in storm["audit_trace"]["delay_drivers"]["drivers"] if x["feature"] == "weather")
    assert weather["hours"] > 0
    assert rr.model_status()["weather_source"] == "test storm"


def test_offline_weather_is_zero_and_says_so():
    rr = _new_rr()
    before = _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]

    def no_network(coords):
        raise ConnectionError("no route to api.open-meteo.com")
    rr.refresh_weather(fetcher=no_network)
    assert rr.model_status()["weather_source"].startswith("offline")
    assert rr.weather == {}
    assert _cards(rr, "PORT-SHANGHAI", "PORT-ROTTERDAM")["FASTEST"]["eta_range"] == before["eta_range"]


def test_open_meteo_batch_request_is_parsed():
    from backend.engine.weather_integration import fetch_hub_weather
    calls = []

    class _Resp:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    def fake_get(url, params, timeout):
        calls.append(params)
        n = len(params["latitude"].split(","))
        codes = [0, 95, 63][:n]
        return _Resp([{"current_weather": {"weathercode": c}} for c in codes] if n > 1
                     else {"current_weather": {"weathercode": codes[0]}})
    out = fetch_hub_weather({"A": (1.0, 2.0), "B": (3.0, 4.0), "C": (5.0, 6.0)}, get=fake_get, batch_size=2)
    assert out == {"A": 0.0, "B": 0.9, "C": 0.0}  # C is alone in the second batch: code 0
    assert len(calls) == 2 and calls[0]["latitude"] == "1.0,3.0"


# TI15: the app's model and anchor paths don't depend on the folder it's started from
def test_ti15_paths_are_absolute_and_exist():
    import backend.engine.threat_intelligence as ti
    for p in (ti.MODEL_PATH, ti.ENCODER_PATH, ti.NLP_ANCHORS_PATH, ti.CALIBRATION_PATH):
        assert os.path.isabs(p) and os.path.exists(p), p


# M10 (part): the status reports the real model and weather source, not hardcoded values
def test_model_status_reports_the_real_model(rr):
    s = rr.model_status()
    assert s["delay_model"]["n_rows"] == 50_000 and s["delay_model"]["trained_at"]
    assert 0.8 < s["delay_model"]["coverage_p85"] < 0.9
    assert s["weather_source"].startswith("offline")  # demo mode never fetches


@pytest.mark.slow
def test_api_status_serves_the_model_status():
    from fastapi.testclient import TestClient
    from backend.main import app
    body = TestClient(app).get("/api/status").json()
    assert body["ml_trained"] is True and "delay_model" in body and "weather_source" in body

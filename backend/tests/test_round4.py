"""Round 4: the audit trace and totals must add up (BUG_REPORT.md section 4)."""
import pytest

from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager


class _Pred:
    def warmup(self): pass


@pytest.fixture(scope="module")
def rr():
    return RouteRecommender(None, _Pred(), None, ScenarioManager(), demo_mode=True)


def _red_sea_fastest(rr):
    # FASTEST still pays Bab-el-Mandeb under RED_SEA_CONFLICT (+72h, threat 0.85), so the scenario shows in the audit
    out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", transport_preference="sea", scenario="RED_SEA_CONFLICT")
    route = {r["persona"]: r for r in out["recommendations"]}["FASTEST"]
    assert any(leg["intel_source"] == "SCENARIO" for leg in route["legs"])
    return route


# R10: the scenario delay is counted once, so the ETA breakdown sums to the ETA
def test_r10_eta_breakdown_sums_to_adjusted_eta(rr):
    route = _red_sea_fastest(rr)
    eta = route["audit_trace"]["eta"]
    assert eta["scenario"] == 72
    # Round 7 added the model's predicted delay as its own bucket
    assert eta["transit"] + eta["transfer"] + eta["scenario"] + eta["predicted_delay"] == \
        pytest.approx(route["adjusted_eta"], abs=0.2)


# R11: the scenario surcharge is part of the total cost
def test_r11_cost_breakdown_sums_to_total_cost(rr):
    route = _red_sea_fastest(rr)
    cost = route["audit_trace"]["cost"]
    assert cost["scenario"] > 0
    assert cost["transit"] + cost["transfer"] + cost["scenario"] == pytest.approx(route["total_cost"], abs=0.05)
    assert sum(leg["cost"] for leg in route["legs"]) == pytest.approx(route["total_cost"], abs=0.05)


def test_r10_r11_legs_sum_to_totals_without_scenario(rr):
    out = rr.recommend("PORT-SHANGHAI", "PORT-ROTTERDAM", transport_preference="sea")
    for route in out["recommendations"]:
        eta, cost = route["audit_trace"]["eta"], route["audit_trace"]["cost"]
        assert eta["scenario"] == 0 and cost["scenario"] == 0
        assert sum(leg["eta"] for leg in route["legs"]) == pytest.approx(route["adjusted_eta"], abs=0.5)


# R12: baseline risk is measured before the scenario is applied
def test_r12_baseline_risk_excludes_the_scenario(rr):
    route = _red_sea_fastest(rr)
    risk = route["audit_trace"]["risk"]
    assert risk["scenario"] == 0.85
    assert risk["baseline"] < 0.85


# M13: errors come back with an error status, not 200, and a clean message
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


@pytest.mark.slow
def test_m13_no_route_is_404(client):
    r = client.post("/api/recommend", json={"source": "PORT-BAKU", "destination": "PORT-ROTTERDAM",
                                            "transport_preference": "sea"})
    assert r.status_code == 404
    assert "établi" not in r.json()["error"]


@pytest.mark.slow
@pytest.mark.parametrize("body", [
    {"source": "PORT-SHANGHAI", "destination": "PORT-ROTTERDAM", "scenario": "SUEZ_BLOK"},
    {"source": "NOWHERE", "destination": "PORT-ROTTERDAM"},
])
def test_m13_bad_input_is_400(client, body):
    r = client.post("/api/recommend", json=body)
    assert r.status_code == 400 and "error" in r.json()


@pytest.mark.slow
def test_m13_unknown_supplier_scenario_is_400(client):
    r = client.post("/api/suppliers", json={"category": "Semiconductors", "scenario": "NOPE"})
    assert r.status_code == 400 and "error" in r.json()


@pytest.mark.slow
def test_m13_good_request_is_still_200(client):
    r = client.post("/api/recommend", json={"source": "PORT-SHANGHAI", "destination": "PORT-ROTTERDAM"})
    assert r.status_code == 200 and r.json()["recommendations"]

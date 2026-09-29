import pytest
from backend.engine.threat_intelligence import ContrastiveNLPEngine, CARFFilter
from backend.engine.route_recommender import RouteRecommender
from backend.engine.scenario_manager import ScenarioManager
import backend.engine.threat_intelligence as ti

class _Pred:
    def warmup(self): pass

def _router():
    return RouteRecommender(None, _Pred(), None, ScenarioManager())

@pytest.fixture(scope="module")
def nlp():
    e = ContrastiveNLPEngine(lazy_load=True); e.warmup(); return e

# TI1: anchors must load on a CPU-only machine
@pytest.mark.slow
def test_ti1_nlp_loads_on_cpu(nlp):
    assert nlp._ready

# TI2/R3: an NLP failure must mark the warm-up as failed
@pytest.mark.slow
def test_r3_nlp_failure_is_reported(monkeypatch):
    monkeypatch.setattr(ti, "NLP_ANCHORS_PATH", "missing.pt")
    rr = _router(); rr.run_background_warmup()
    assert rr.warmup_failed and not rr.is_warmed_up

# TI3 + decision 1: margin -> threat
def test_ti3_score_from_margin():
    e = ContrastiveNLPEngine(lazy_load=True)
    assert e.score_from_margin(0.567) > 0.8     # Ever Given
    assert e.score_from_margin(0.018) == 0.0    # noise
    assert e.score_from_margin(-0.155) == 0.0   # calm news, no negative scores
    assert e.score_from_margin(0.6) == 1.0

@pytest.mark.slow
def test_ti3_real_disaster_scores_high(nlp):
    assert nlp.get_semantic_score("Container ship Ever Given runs aground in the Suez Canal, blocking all traffic in both directions.") > 0.8

# TI5: a disaster sentence after >256 chars of good news must still be caught
@pytest.mark.slow
def test_ti5_disaster_in_good_news(nlp):
    # A calm first chunk that closely matches a "normal operations" anchor used to cancel the disaster
    # in the second chunk: old logic scored 0.00, per-chunk logic scores 0.93.
    calm = ("Operations at the Port of Rotterdam are proceeding normally. Vessel turnaround times are within "
            "expected parameters and terminal capacity remains optimal. Air cargo capacity on the trans-Atlantic "
            "corridor remains high with no reported backlogs at major hubs.")
    assert nlp.get_semantic_score(calm + " Container ship Ever Given runs aground in the Suez Canal, "
                                  "blocking all traffic in both directions.") > 0.5

# TI7/TI8/TI9: CARF drops a threat only when the news is about OTHER modes
@pytest.mark.parametrize("text,mode,kept", [
    ("Maritime congestion reported at major transshipment hubs.", "sea", True),
    ("Ever Given blocks the Suez canal", "sea", True),
    ("Ever Given blocks the Suez canal.", "sea", True),
    ("Airport shut, all flights grounded", "sea", False),
    ("Airport shut, all flights grounded", "air", True),
    ("Rail strike halts locomotives", "road", False),
    ("Severe storm hits the region", "rail", True),   # no mode mentioned: keep
])
def test_carf(text, mode, kept):
    assert (CARFFilter().apply_filter(0.5, text, mode) > 0) == kept

# W1: no live news means no invented threat on any edge
def test_w1_no_invented_threat(monkeypatch):
    rr = _router()
    monkeypatch.setattr(rr.nlp, "warmup", lambda: setattr(rr.nlp, "_ready", True))
    monkeypatch.setattr(rr.nlp, "get_semantic_score", lambda text: 0.5)
    rr.run_background_warmup()
    assert all(d.get("base_threat", 0) == 0 for _, _, d in rr.unified_graph.edges(data=True)
               if d["transport_mode"] != "transfer")
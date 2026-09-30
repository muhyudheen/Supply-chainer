"""The trained delay models as the router uses them: batch prediction and delay drivers (SHAP).

Delay drivers are exact Shapley values against a calm baseline: the same leg with no cargo handling, no canal
or chokepoint, weather 0 and news 0. Only these five features differ between the leg and its baseline, so the
leg's delay splits into "calm transit" (the baseline's prediction: mode, distance, hubs, region) plus one share
per feature. With five features there are 2^5 = 32 on/off combinations, so the values are computed exactly
from 32 predictions per leg; a test checks they equal shap.TreeExplainer's interventional values.
"""
import itertools
from math import factorial

import numpy as np

from backend.ml.train import ARTIFACT, NAMES, load, load_metrics, predict_quantiles, encode

VARYING = ["cargo_handled", "arrives_canal", "chokepoint", "weather", "news"]
CALM = {"cargo_handled": 0, "arrives_canal": 0, "chokepoint": 0, "weather": 0.0, "news": 0.0}
LABELS = {"cargo_handled": "terminal dwell", "arrives_canal": "canal queue", "chokepoint": "chokepoint risk",
          "weather": "weather", "news": "news"}

_SUBSETS = list(itertools.product([0, 1], repeat=len(VARYING)))  # which features are switched to the leg's value
_INDEX = {s: i for i, s in enumerate(_SUBSETS)}


def _weight(size):
    """Shapley weight of adding one feature to a coalition of `size` others."""
    k = len(VARYING)
    return factorial(size) * factorial(k - size - 1) / factorial(k)


class DelayModel:
    def __init__(self, path=ARTIFACT):
        self.bundle = load(path)  # raises if the artifact is missing: no silent fallback (TI14)
        self.metrics = load_metrics()

    def predict(self, rows):
        """(n, 3) array of hours: p50, p85, p95 for each leg_features() row, sorted so they never cross."""
        return predict_quantiles(self.bundle, rows)

    def explain(self, rows, q):
        """For quantile model q (0, 1, 2): each leg's calm-transit hours and each VARYING feature's share.
        calm_h[i] + sum of phi[f][i] equals model q's raw prediction for row i."""
        batch = [{**row, **CALM, **{f: row[f] for f, on in zip(VARYING, s) if on}} for row in rows for s in _SUBSETS]
        v = self.bundle["models"][q].predict(encode(self.bundle, batch)).reshape(len(rows), len(_SUBSETS))
        phi = {f: np.zeros(len(rows)) for f in VARYING}
        for s in _SUBSETS:
            for j, f in enumerate(VARYING):
                if not s[j]:
                    with_f = s[:j] + (1,) + s[j + 1:]
                    phi[f] += _weight(sum(s)) * (v[:, _INDEX[with_f]] - v[:, _INDEX[s]])
        return v[:, _INDEX[(0,) * len(VARYING)]], phi

    def status(self):
        o = self.metrics["overall"]
        return {"trained_at": self.bundle["trained_at"], "n_rows": self.bundle["n_rows"],
                "sklearn_version": self.bundle["sklearn_version"], "data": self.bundle["data"],
                "coverage_p85": o["coverage"]["p85"],
                "coverage": o["coverage"], "pinball": o["pinball"], "quantiles": NAMES}

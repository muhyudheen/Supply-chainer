"""Round 7 step 2: the p50/p85/p95 leg-delay models (BUG_REPORT.md section 7, HANDOFF.md section 3).

Trains on a smaller seeded dataset than the shipped artifact so the suite stays quick.
"""
import importlib
import os

import numpy as np
import pytest
import sklearn

from backend.engine.multimodal_network import create_multimodal_network

N_ROWS = 20_000
SEED = 42


@pytest.fixture(scope="module")
def train():
    return importlib.import_module("backend.ml.train")


@pytest.fixture(scope="module")
def G():
    return create_multimodal_network()


@pytest.fixture(scope="module")
def split(train, G):
    df = importlib.import_module("backend.ml.dataset").build_dataset(n_rows=N_ROWS, seed=SEED, G=G)
    tr, te = train.group_split(df, seed=SEED)
    return df.iloc[tr], df.iloc[te]


@pytest.fixture(scope="module")
def bundle(train, split):
    return train.fit(split[0], seed=SEED)


@pytest.fixture(scope="module")
def metrics(train, bundle, split):
    return train.evaluate(bundle, split[0], split[1])


# MR4: whole routes are held out, so the score isn't inflated by legs the model saw in training
def test_mr4_split_holds_out_whole_routes(train, split):
    tr, te = split
    assert not set(train.route_key(tr)) & set(train.route_key(te))
    assert 0.15 < len(te) / (len(tr) + len(te)) < 0.25


# MR2: coverage per mode, on held-out routes (the old model was never evaluated)
@pytest.mark.parametrize("mode", ["sea", "air", "rail", "road"])
def test_mr2_coverage_per_mode_is_near_the_quantile(metrics, mode):
    for q in ("p50", "p85", "p95"):
        target = int(q[1:]) / 100
        got = metrics["per_mode"][mode]["coverage"][q]
        assert abs(got - target) < 0.05, (mode, q, got)


def test_quantiles_never_cross(train, bundle, split):
    pred = train.predict_quantiles(bundle, split[1])
    assert pred.shape == (len(split[1]), 3)
    assert (np.diff(pred, axis=1) >= 0).all()


def test_model_beats_a_constant_per_mode_quantile(metrics):
    for q in ("p50", "p85", "p95"):
        assert metrics["overall"]["pinball"][q] < metrics["overall"]["baseline_pinball"][q], q


# TI10/TI14: a category the model never saw is an error, not a silent guess
def test_ti10_unknown_category_raises(train, bundle, split):
    rows = split[1].head(3).copy()
    rows["region"] = "ATLANTIS"
    with pytest.raises(ValueError):
        train.predict_quantiles(bundle, rows)


def test_feature_names_are_the_shared_ones(train, bundle):
    features = importlib.import_module("backend.ml.features")
    assert bundle["features"] == features.FEATURES


# MR6/TI15: the shipped artifact carries its metadata and loads from any folder
def test_mr6_artifact_and_metrics_are_committed(train, G):
    assert os.path.isabs(train.ARTIFACT) and os.path.isabs(train.METRICS)
    b = train.load()
    assert b["quantiles"] == [0.5, 0.85, 0.95]
    assert b["seed"] == 42 and b["n_rows"] == 50_000
    assert b["sklearn_version"] == sklearn.__version__
    features = importlib.import_module("backend.ml.features")
    u, v = "PORT-SHANGHAI:sea", "PORT-CAIMEP:sea"
    row = features.leg_features(G, u, v, cargo_handled=False)
    pred = train.predict_quantiles(b, [row])
    assert pred.shape == (1, 3) and (pred >= 0).all()
    m = train.load_metrics()
    assert set(m["per_mode"]) == {"sea", "air", "rail", "road"}

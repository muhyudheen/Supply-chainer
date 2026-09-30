"""Round 7 step 1: the simulated leg-delay dataset (BUG_REPORT.md section 6, HANDOFF.md section 3).

Each test pins one dataset finding (DS1-DS11). The modules are imported inside fixtures, so a missing
module fails every test on its own instead of one collection error.
"""
import importlib
import os

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from backend.engine.multimodal_network import create_multimodal_network, load_canonical_hubs

N_ROWS = 20_000
SEED = 42


@pytest.fixture(scope="module")
def features():
    return importlib.import_module("backend.ml.features")


@pytest.fixture(scope="module")
def dataset():
    return importlib.import_module("backend.ml.dataset")


@pytest.fixture(scope="module")
def G():
    return create_multimodal_network()


@pytest.fixture(scope="module")
def df(dataset, G):
    return dataset.build_dataset(n_rows=N_ROWS, seed=SEED, G=G)


def _p(x, q):
    return float(np.percentile(x, q))


def _en_route_only(df):
    """Rows with no dwell and no incident: their delay is the en-route part alone."""
    return df[(df["cargo_handled"] == 0) & (df["arrives_canal"] == 0) & ~df["incident"]]


# 1. DS4: the news score is drawn before the delay and never computed from it
def test_ds4_no_leakage_on_calm_rows(df):
    calm = df[~df["incident"]]
    assert calm["news"].std() > 0  # calm rows still carry news noise, so the check below means something
    r = np.corrcoef(calm["news"], calm["delay_h"])[0, 1]
    assert abs(r) < 0.05, r


# 2. DS5: weather changes the delay (it had no effect: sea p85 56.5h clear vs 55.3h stormy).
#    Weather acts on the en-route part, so the check looks at rows without dwell.
def test_ds5_stormy_sea_is_slower_than_clear_sea(df):
    sea = _en_route_only(df[df["mode"] == "sea"])
    stormy, clear = sea[sea["weather"] >= 0.7], sea[sea["weather"] <= 0.1]
    assert len(stormy) > 200 and len(clear) > 200
    assert _p(stormy["delay_h"], 85) > 1.2 * _p(clear["delay_h"], 85)


# 3. DS6: distance changes the delay (Shanghai -> Singapore and Shanghai -> Rotterdam had the same).
#    Dwell doesn't depend on distance; the en-route part does.
@pytest.mark.parametrize("mode", ["sea", "air", "rail", "road"])
def test_ds6_long_legs_have_a_higher_p85(df, mode):
    m = _en_route_only(df[df["mode"] == mode])
    short = m[m["distance_km"] <= m["distance_km"].quantile(0.25)]
    long_ = m[m["distance_km"] >= m["distance_km"].quantile(0.75)]
    assert _p(long_["delay_h"], 85) > 1.2 * _p(short["delay_h"], 85)


# 4. DS3: the gamma matches both the stated median and the stated p90 (only the median was used)
def test_ds3_anchor_median_and_p90_within_10_percent(dataset):
    rng = np.random.default_rng(SEED)
    assert set(dataset.ANCHORS) == {"sea", "air", "rail", "road", "canal"}
    assert (dataset.ANCHORS["canal"]["median"], dataset.ANCHORS["canal"]["p90"]) == (14.0, 144.0)  # organizers' Suez
    for kind, a in dataset.ANCHORS.items():
        assert a["source"], kind  # DS1/DS2: every anchor says where its numbers come from
        x = dataset.sample_dwell(kind, rng, 200_000)
        assert abs(_p(x, 50) / a["median"] - 1) < 0.10, (kind, _p(x, 50), a["median"])
        assert abs(_p(x, 90) / a["p90"] - 1) < 0.10, (kind, _p(x, 90), a["p90"])


# Dwell (the anchors) applies only where cargo is handled at a port, terminal or airport
@pytest.mark.parametrize("mode", ["sea", "air", "rail", "road"])
def test_dwell_only_where_cargo_is_handled(features, df, mode):
    assert (df.loc[~df["dest_type"].isin(features.TERMINAL_TYPES), "cargo_handled"] == 0).all()
    m = df[(df["mode"] == mode) & (df["arrives_canal"] == 0) & ~df["incident"]]
    handled, passing = m[m["cargo_handled"] == 1], m[m["cargo_handled"] == 0]
    assert len(handled) > 200 and len(passing) > 200
    assert handled["delay_h"].median() > 5 * passing["delay_h"].median()


# Distribution hubs handle cargo too, so they get dwell when cargo is unloaded there
def test_distribution_hubs_count_as_terminals(features, df):
    assert "distribution_hub" in features.TERMINAL_TYPES
    assert (df.loc[df["dest_type"] == "distribution_hub", "cargo_handled"] == 1).any()


# Canal legs keep the normal incident rate: the canal anchor's p90 already holds the 2021 blockage
@pytest.mark.parametrize("u, v, doubled", [
    ("PORT-ALEXANDR:sea", "CHOKE-SUEZ:sea", False),  # into a canal
    ("CHOKE-SUEZ:sea", "PORT-ALEXANDR:sea", False),  # out of a canal
    ("PORT-SINGAPORE:sea", "CHOKE-MALACCA:sea", True),  # into a strait
    ("CHOKE-BABEL:sea", "CHOKE-SUEZ:sea", True),  # strait to canal: the strait counts
    ("PORT-CAIMEP:sea", "PORT-SINGAPORE:sea", False),  # no chokepoint
])
def test_canal_legs_use_the_normal_incident_rate(dataset, G, u, v, doubled):
    expected = dataset.CHOKEPOINT_INCIDENT_RATE if doubled else dataset.INCIDENT_RATE
    assert dataset.incident_rate(G, u, v) == expected


# The Suez anchor applies to canals (Suez, Panama), not to open straits
def test_canal_arrivals_wait_longer_than_strait_arrivals(df):
    calm = df[(df["dest_type"] == "choke_point") & ~df["incident"]]
    canal, strait = calm[calm["arrives_canal"] == 1], calm[calm["arrives_canal"] == 0]
    assert len(canal) > 30 and len(strait) > 30
    assert canal["delay_h"].median() > 2 * strait["delay_h"].median()


# Sanity: the delay stays a modest share of a long voyage (dwell at every port call would add 150h+)
def test_shanghai_rotterdam_p50_delay_under_a_quarter_of_travel_time(dataset, G):
    sea = G.edge_subgraph([(u, v) for u, v, d in G.edges(data=True) if d["transport_mode"] == "sea"])
    path = nx.shortest_path(sea, "PORT-SHANGHAI:sea", "PORT-ROTTERDAM:sea", weight="baseline_time")
    legs = list(zip(path, path[1:]))
    travel = sum(G[u][v]["baseline_time"] for u, v in legs)
    assert abs(travel - 545.1) < 1  # manual check 1 in HANDOFF.md
    rng = np.random.default_rng(SEED)
    p50 = sum(dataset.simulate_legs(G, [(u, v, i == len(legs) - 1)] * 4_000, rng)["delay_h"].median()
              for i, (u, v) in enumerate(legs))
    assert p50 < 0.25 * travel, p50


# 5. DS9: incidents actually happen (0.4% of rows had one)
def test_ds9_incident_rate(df):
    assert 0.03 <= df["incident"].mean() <= 0.08, df["incident"].mean()


# 6. TI11: every feature comes from leg_features(), the function the router will call too
def test_ti11_features_come_from_leg_features(features, df, G):
    assert [c for c in df.columns if c in features.FEATURES] == list(features.FEATURES)
    assert set(df.columns) == set(features.FEATURES) | {"delay_h", "incident", "u", "v"}
    for row in df.sample(300, random_state=SEED).to_dict("records"):
        again = features.leg_features(G, row["u"], row["v"], cargo_handled=bool(row["cargo_handled"]),
                                      weather=row["weather"], news=row["news"])
        assert again == {k: row[k] for k in features.FEATURES}


def test_ti10_features_hold_no_hub_names_or_ids(features, df):
    names = {s for h in load_canonical_hubs() for s in (h["id"], h["display_name"], h.get("parent_city"))}
    for col in features.FEATURES:
        if not pd.api.types.is_numeric_dtype(df[col]):
            assert not set(df[col].unique()) & names, col


def test_ti10_every_transit_leg_has_features(features, G):
    """The live app can ask about any leg of the graph, so no hub may be missing from a lookup table."""
    for u, v, d in G.edges(data=True):
        if d["type"] == "transit":
            f = features.leg_features(G, u, v, cargo_handled=True)
            assert f["weather"] == 0.0 and f["news"] == 0.0  # no live data means 0, the offline value


def test_ti14_unknown_inputs_raise(features, G):
    u, v = next((u, v) for u, v, d in G.edges(data=True) if d["type"] == "transfer")
    with pytest.raises(ValueError):
        features.leg_features(G, u, v, cargo_handled=False)  # a transfer is not a transit leg
    u, v = next((u, v) for u, v, d in G.edges(data=True) if d["type"] == "transit")
    with pytest.raises(ValueError):
        features.leg_features(G, u, v, cargo_handled=False, weather=1.5)


# 7. DS11/MR6: same seed, same dataset; paths don't depend on the current folder
def test_ds11_same_seed_same_dataset(dataset, G):
    a = dataset.build_dataset(n_rows=2_000, seed=7, G=G)
    b = dataset.build_dataset(n_rows=2_000, seed=7, G=G)
    c = dataset.build_dataset(n_rows=2_000, seed=8, G=G)
    assert a.equals(b)
    assert not a.equals(c)


def test_ds11_csv_path_is_next_to_the_code(dataset):
    assert os.path.isabs(dataset.DEFAULT_CSV)
    assert os.path.dirname(dataset.DEFAULT_CSV).startswith(os.path.dirname(os.path.abspath(dataset.__file__)))

"""Seeded builder for the leg-delay training data.

SIMULATED DATA (DS1, DS2). No delay records are read. Each row is a real transit leg of our route graph
(create_multimodal_network(): real hubs, real distances) with a delay drawn from the model below.
The dwell distributions are anchored to the dwell-time figures the organizers supplied in
Code/real_dataset_builder.py, with the source labels given there; we have not verified those sources.
Everything marked "assumed" is our modelling choice, not data.

Delay of a leg (hours beyond its baseline travel time):
    dwell at the arrival hub      only where cargo is handled (port, terminal, airport, distribution hub),
                                  or when arriving at a canal (the organizers' Suez anchor)
  + en-route variability          a share of the leg's baseline travel time, raised by weather
  + incident delay                on the few rows with an incident

Draw order (DS4): weather, incident and news are drawn first; the delay depends on them. No feature is
computed from the delay. On calm rows the news score is noise that doesn't depend on the delay.

Regenerate the CSV (git-ignored, DS11):  uv run python -m backend.ml.dataset
"""
import os
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import gamma

from backend.engine.multimodal_network import create_multimodal_network
from backend.engine.weather_integration import WMO_SEVERITY_MAPPING
from backend.ml.features import FEATURES, leg_features

DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "leg_delays.csv")
MODES = ["sea", "air", "rail", "road"]

# The organizers' dwell-time figures (hours), copied unchanged from Code/real_dataset_builder.py.
# Their labels: port = "World Bank LPI & UNCTAD Maritime Statistics (2023 Medians)", rail = "STB Rail
# Service Data (2022 Terminal Dwell Reports)", air = "IATA / FAA Ground Handling Benchmarks",
# road = "Road Border / Port Gate Statistics". The model has no hub names, so each mode's anchor is the
# median over that mode's figures.
ORGANIZER_DWELL = {
    "sea": {"Seattle": (28.0, 120.0), "Los Angeles": (42.0, 240.0), "New York": (34.0, 140.0),
            "Rotterdam": (26.0, 90.0), "Mumbai": (52.0, 180.0), "Singapore": (22.0, 70.0), "Shanghai": (30.0, 110.0)},
    "rail": {"Chicago": (28.5, 62.0), "Houston": (31.2, 74.0), "St. Louis": (22.4, 48.0), "Dallas": (24.8, 55.0)},
    "air": {"Atlanta": (12.0, 36.0), "Delhi": (18.0, 52.0), "Dubai": (8.0, 24.0)},
    "road": {"Default": (4.0, 18.0)},
}
_SOURCE = "organizers' figures in Code/real_dataset_builder.py ({}), median over {} locations; not verified by us"
ANCHORS = {
    mode: {"median": float(np.median([m for m, _ in figs.values()])),
           "p90": float(np.median([p for _, p in figs.values()])),
           "source": _SOURCE.format(mode, len(figs))}
    for mode, figs in ORGANIZER_DWELL.items()
}
ANCHORS["canal"] = {"median": 14.0, "p90": 144.0,
                    "source": "organizers' Suez Canal figure in Code/real_dataset_builder.py; p90 = the 6-day 2021 blockage"}

# En-route variability as a share of the baseline travel time (assumed): median 5%, p90 15%,
# multiplied by (1 + WEATHER_K[mode] * weather). Assumed: weather hurts sea and air most.
EN_ROUTE_SHARE = {"median": 0.05, "p90": 0.15}
WEATHER_K = {"sea": 1.0, "air": 0.8, "road": 0.5, "rail": 0.3}

# How often each WMO weather code is drawn (assumed); severities are the live provider's mapping
WEATHER_CODE_P = {0: .30, 1: .15, 2: .12, 3: .10, 45: .03, 48: .02, 51: .03, 53: .02, 61: .05, 63: .04, 65: .02,
                  71: .01, 73: .01, 80: .03, 81: .03, 82: .01, 95: .02, 96: .005, 99: .005}

# Incidents (DS9): 4% of legs, twice that on chokepoint legs (assumed), severity s uniform 0.5-1.
# Delay added = s * INCIDENT_H[mode], sized from the app's own scenarios (scenario_manager.py):
# sea 72-240h (median 144h), Dubai air congestion 48h, Chennai road flood 48h. There is no rail
# scenario, so rail takes 48h like the other land and air ones.
INCIDENT_RATE, CHOKEPOINT_INCIDENT_RATE = 0.04, 0.08
INCIDENT_H = {"sea": 144.0, "air": 48.0, "road": 48.0, "rail": 48.0}
CARGO_HANDLED_P = 0.5  # share of legs into a terminal where the cargo is unloaded (assumed; keeps both cases common)


@lru_cache(maxsize=None)
def fit_gamma(median, p90):
    """Gamma (shape, scale) whose median and p90 are both the stated ones (DS3: the old fit ignored the p90)."""
    ratio = p90 / median
    shape = brentq(lambda k: gamma.ppf(0.9, k) / gamma.ppf(0.5, k) - ratio, 0.01, 100)
    return shape, median / gamma.ppf(0.5, shape)


def sample_dwell(kind, rng, size):
    """Dwell hours at the arrival hub, for a mode anchor or "canal"."""
    shape, scale = fit_gamma(ANCHORS[kind]["median"], ANCHORS[kind]["p90"])
    return rng.gamma(shape, scale, size)


def simulate_legs(G, legs, rng):
    """One row per (u, v, cargo_handled) leg: draw weather, incident and news, then the delay."""
    n = len(legs)
    codes = list(WEATHER_CODE_P)
    weather = np.array([WMO_SEVERITY_MAPPING[c] for c in codes])[
        rng.choice(len(codes), n, p=list(WEATHER_CODE_P.values()))]
    rows = [leg_features(G, u, v, cargo_handled=h, weather=w) for (u, v, h), w in zip(legs, weather)]
    df = pd.DataFrame(rows, columns=FEATURES)

    # Incident and news first (DS4)
    rate = np.where(df["chokepoint"] == 1, CHOKEPOINT_INCIDENT_RATE, INCIDENT_RATE)
    incident = rng.random(n) < rate
    severity = rng.uniform(0.5, 1.0, n)
    calm_news = np.where(rng.random(n) < 0.15, rng.uniform(0.0, 0.3, n), 0.0)
    df["news"] = np.where(incident, np.clip(severity + rng.normal(0, 0.1, n), 0, 1), calm_news)

    # Then the delay
    mode = df["mode"].to_numpy()
    travel_h = np.array([G[u][v]["baseline_time"] for u, v, _ in legs])
    dwell = np.zeros(n)
    for kind, mask in [(m, (mode == m) & (df["cargo_handled"] == 1)) for m in MODES] + \
                      [("canal", df["arrives_canal"].to_numpy() == 1)]:
        dwell[mask] = sample_dwell(kind, rng, mask.sum())
    share_shape, share_scale = fit_gamma(EN_ROUTE_SHARE["median"], EN_ROUTE_SHARE["p90"])
    weather_k = np.array([WEATHER_K[m] for m in mode])
    en_route = travel_h * rng.gamma(share_shape, share_scale, n) * (1 + weather_k * df["weather"].to_numpy())
    incident_h = np.where(incident, severity * np.array([INCIDENT_H[m] for m in mode]), 0.0)

    df["delay_h"] = dwell + en_route + incident_h
    df["incident"] = incident
    df["u"] = [u for u, _, _ in legs]
    df["v"] = [v for _, v, _ in legs]
    return df


def build_dataset(n_rows=50_000, seed=42, G=None):
    """Rows are transit legs of the real graph, the same number per mode (road alone has 57% of the legs)."""
    G = G if G is not None else create_multimodal_network()
    rng = np.random.default_rng(seed)
    transit = sorted((u, v) for u, v, d in G.edges(data=True) if d["type"] == "transit")
    legs = []
    for i, m in enumerate(MODES):
        pool = [e for e in transit if G.edges[e]["transport_mode"] == m]
        k = n_rows // len(MODES) + (i < n_rows % len(MODES))
        picks = rng.choice(len(pool), k)
        handled = rng.random(k) < CARGO_HANDLED_P
        legs += [(*pool[j], bool(h)) for j, h in zip(picks, handled)]
    return simulate_legs(G, legs, rng)


if __name__ == "__main__":
    df = build_dataset()
    os.makedirs(os.path.dirname(DEFAULT_CSV), exist_ok=True)
    df.to_csv(DEFAULT_CSV, index=False)
    print(f"Wrote {len(df)} simulated rows to {DEFAULT_CSV} ({df['incident'].mean():.1%} with an incident)")

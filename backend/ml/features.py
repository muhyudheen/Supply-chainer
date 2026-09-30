"""The one feature function for the delay model, used by both the dataset builder and the router.

Training and serving call the same leg_features(), so a feature can't mean one thing in the data and
another in the app (the old model's inputs didn't exist in the live app: TI11). No hub names or IDs
are features, so the model works for any hub of the graph (TI10). Unknown inputs raise (TI14).
"""
from backend.engine.multimodal_network import load_sea_network

FEATURES = ["mode", "distance_km", "origin_type", "dest_type", "origin_importance", "dest_importance",
            "chokepoint", "arrives_canal", "cargo_handled", "region", "weather", "news"]
CATEGORICAL = ["mode", "origin_type", "dest_type", "region"]

# Hub types where cargo waits when it is unloaded or transferred (the dwell anchors); only chokepoints have none
TERMINAL_TYPES = {"port", "airport", "rail_hub", "rail_terminal", "distribution_hub"}
# Chokepoints with a booked, queued transit; the other chokepoints are open straits, capes or lanes
CANALS = {"CHOKE-SUEZ", "CHOKE-PANAMA"}

# Region of a land or air leg, by the arrival hub's country. Every country in canonical_hubs.json is
# listed; a missing one raises, so a new hub can't silently get a wrong region.
_REGIONS = {
    "SOUTH_ASIA": ["India", "Sri Lanka", "Pakistan", "Bangladesh"],
    "EAST_ASIA": ["China", "Japan", "South Korea", "Taiwan", "Hong Kong"],
    "SOUTHEAST_ASIA": ["Singapore", "Malaysia", "Vietnam", "Indonesia", "Thailand", "Philippines", "Myanmar",
                       "Cambodia"],
    "MIDDLE_EAST": ["UAE", "Oman", "Saudi Arabia", "Qatar", "Iran", "Israel", "Yemen"],
    "EUROPE": ["Germany", "Netherlands", "Italy", "Spain", "France", "UK", "Belgium", "Poland", "Greece", "Sweden",
               "Norway", "Finland", "Romania", "Slovenia", "Hungary", "Czech Republic", "Austria", "Iceland",
               "Lithuania", "Turkey"],
    "RUSSIA_CENTRAL_ASIA": ["Russia", "Kazakhstan", "Uzbekistan", "Azerbaijan", "Georgia", "Belarus"],
    "AFRICA": ["South Africa", "Egypt", "Kenya", "Djibouti", "Tanzania", "Morocco", "Nigeria", "Ivory Coast",
               "Mozambique", "Togo", "Ethiopia", "Namibia", "Angola", "Madagascar", "Somaliland", "Sudan", "Uganda",
               "Rwanda", "Burkina Faso"],
    "NORTH_AMERICA": ["USA", "Canada", "Mexico"],
    "LATIN_AMERICA": ["Panama", "Brazil", "Chile", "Argentina", "Peru", "Colombia", "Uruguay", "Ecuador", "Bolivia"],
    "OCEANIA": ["Australia", "New Zealand"],
}
COUNTRY_REGION = {c: r for r, countries in _REGIONS.items() for c in countries}

# Sea basin of each sea hub; a gate chokepoint (e.g. Suez) sits in two basins
_sea = load_sea_network()
SEA_BASINS = {h: {b} for h, b in _sea["basins"].items()}
SEA_BASINS.update({g: set(bs) for g, bs in _sea["gates"].items()})


def _sea_region(a, b):
    """The basin both ends share; for a leg between two open basins, the arrival's basin."""
    if a not in SEA_BASINS or b not in SEA_BASINS:
        raise ValueError(f"No sea basin for {a if a not in SEA_BASINS else b} in sea_network.json")
    return min(SEA_BASINS[a] & SEA_BASINS[b] or SEA_BASINS[b])


def _unit(name, x):
    if not 0.0 <= x <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {x}")
    return float(x)


def leg_features(G, u, v, *, cargo_handled, weather=0.0, news=0.0):
    """Features of the transit leg u -> v of the multimodal graph.

    cargo_handled: the cargo is unloaded or transferred where this leg ends (the next step is a transfer,
    or the trip ends there). It only counts at a port, terminal, airport or distribution hub; a ship
    calling at a port on the way, or passing a chokepoint, has no dwell.
    weather: severity 0-1 at the arrival hub (Open-Meteo's code mapped by WMO_SEVERITY_MAPPING; 0 offline).
    news: threat 0-1 on the NLP engine's scale (score_from_margin; 0 when there is no news).
    """
    if not G.has_edge(u, v) or G[u][v].get("type") != "transit":
        raise ValueError(f"{u} -> {v} is not a transit leg of the graph")
    edge, a, b = G[u][v], G.nodes[u], G.nodes[v]
    mode = edge["transport_mode"]
    if mode == "sea":
        region = _sea_region(a["physical_id"], b["physical_id"])
    elif b["country"] in COUNTRY_REGION:
        region = COUNTRY_REGION[b["country"]]
    else:
        raise ValueError(f"No region for country {b['country']!r}: add it to _REGIONS")
    return {
        "mode": mode,
        "distance_km": edge["distance"],
        "origin_type": a["type"],
        "dest_type": b["type"],
        "origin_importance": a["importance"],
        "dest_importance": b["importance"],
        "chokepoint": int("choke_point" in (a["type"], b["type"])),
        "arrives_canal": int(b["physical_id"] in CANALS),
        "cargo_handled": int(bool(cargo_handled) and b["type"] in TERMINAL_TYPES),
        "region": region,
        "weather": _unit("weather", weather),
        "news": _unit("news", news),
    }

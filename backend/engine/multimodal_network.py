import networkx as nx
import json
import os
import math
from typing import List, Dict, Any

MODE_PROFILES = {
    "road": {"speed": 80, "cost_per_km": 1.2, "cargo_restrictions": ["oversize_heavy"]},
    "rail": {"speed": 60, "cost_per_km": 0.5, "cargo_restrictions": []},
    "air": {"speed": 800, "cost_per_km": 15.0, "cargo_restrictions": ["hazardous_waste"]},
    "sea": {"speed": 35, "cost_per_km": 0.15, "cargo_restrictions": ["perishable_urgent"]}
}

PRIORITY_MULTIPLIERS = {
    "low": 1.2,
    "normal": 1.0,
    "urgent": 0.7
}

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def _travel_time(dist, mode):
    # Speeds in km/h based on freight benchmarks
    speed = MODE_PROFILES.get(mode, {}).get("speed", 50)
    
    # Road friction factor: Real trucking time includes standard stops/traffic
    if mode == "road":
        # Effective speed is lower than max highway speed due to freight regulations
        effective_speed = speed * 0.85 # 68 km/h effective
        return dist / effective_speed
    
    return dist / speed

def load_canonical_hubs():
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'canonical_hubs.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []

def load_sea_network():
    path = os.path.join(os.path.dirname(__file__), '..', 'data',
                        'sea_network.json')
    with open(path, 'r') as f:
        return json.load(f)
    
def _lane_distance(points):
    """Length of a sea lane that follows waypoints: the sum of the straight segments between them."""
    return sum(_haversine(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))


TRANSFER_PROFILES = {
    "port_to_rail": {"delay": 8.0, "cost": 180, "risk": 0.05},
    "road_to_air": {"delay": 6.0, "cost": 150, "risk": 0.02},
    "road_to_sea": {"delay": 14.0, "cost": 250, "risk": 0.08},
    "road_to_rail": {"delay": 4.0, "cost": 100, "risk": 0.03},
    "rail_to_road": {"delay": 4.0, "cost": 80, "risk": 0.02},
    "default": {"delay": 4.0, "cost": 100, "risk": 0.03}
}

# Country pairs within 200 km of each other but separated by sea: no truck road between them (N11)
WATER_SEPARATED = [{"UK", "France"}, {"UK", "Netherlands"}, {"Morocco", "Spain"},
                   {"Indonesia", "Singapore"}, {"Indonesia", "Malaysia"}]

def create_multimodal_network():
    """
    Supplychainer Unified Multimodal Optimization Graph.
    V3: Node Splitting Edition (The Forensic Fix).
    """
    G = nx.DiGraph()
    hubs = load_canonical_hubs()
    hub_lookup = {h["id"]: h for h in hubs}
    
    # Sea topology (N9): basins joined only through gate chokepoints; trunk lanes follow waypoints
    sea = load_sea_network()
    gates = sea["gates"]
    basins_of = {h: {b} for h, b in sea["basins"].items()}
    basins_of.update({g: set(bs) for g, bs in gates.items()})
    open_pairs = {frozenset(p) for p in sea["open_basin_pairs"]}
    trunk = {n for lane in sea["trunk_lanes"] for n in (lane["from"], lane["to"])}

    def sea_link_allowed(a, b):
        if a in trunk and b in trunk:
            return False  # replaced by a trunk lane that goes around land
        ba, bb = basins_of.get(a, set()), basins_of.get(b, set())
        return bool(ba & bb) or any(frozenset((x, y)) in open_pairs for x in ba for y in bb)

    # 1. Add Mode-Specific Virtual Nodes
    # Each hub H with modes M gets nodes H:m1, H:m2...
    for hub in hubs:
        hub_id = hub["id"]
        for mode in hub["modes"]:
            v_node = f"{hub_id}:{mode}"
            G.add_node(v_node,
                physical_id=hub_id,
                display_name=hub["display_name"], 
                type=hub["type"],
                country=hub["country"], 
                lat=hub["lat"], 
                lon=hub["lon"],
                importance=hub.get("importance", 5),
                mode=mode, 
                parent_city=hub.get("parent_city"))

    # 2. Add Intra-Hub Transfer Edges (The Friction Layer)
    for hub in hubs:
        hub_id = hub["id"]
        modes = hub["modes"]
        for i, m1 in enumerate(modes):
            for m2 in modes[i+1:]:
                u, v = f"{hub_id}:{m1}", f"{hub_id}:{m2}"
                
                # Determine transfer profile
                t_type = hub["type"]
                profile_key = "default"
                if t_type == "port" and (m1 == "rail" or m2 == "rail"): profile_key = "port_to_rail"
                elif t_type == "airport" and (m1 == "road" or m2 == "road"): profile_key = "road_to_air"
                elif t_type == "port" and (m1 == "road" or m2 == "road"): profile_key = "road_to_sea"
                
                profile = TRANSFER_PROFILES.get(profile_key, TRANSFER_PROFILES["default"])
                
                G.add_edge(u, v, baseline_time=profile["delay"], distance=0.1, 
                           transport_mode="transfer", type="transfer", 
                           cost=profile["cost"], risk=profile["risk"])
                G.add_edge(v, u, baseline_time=profile["delay"], distance=0.1, 
                           transport_mode="transfer", type="transfer", 
                           cost=profile["cost"], risk=profile["risk"])

    # 3. Add Strategic Intra-Mode Transit Edges
    for hub in hubs:
        u_base = hub["id"]
        for conn in hub.get("connections", []):
            v_base = conn["to"]
            mode = conn["mode"]
            
            if mode == 'sea' and not sea_link_allowed(u_base, v_base):
                continue
            
            u_vnode = f"{u_base}:{mode}"
            v_vnode = f"{v_base}:{mode}"
            
            if G.has_node(u_vnode) and G.has_node(v_vnode):
                h1, h2 = hub, hub_lookup[v_base]
                dist = _haversine(h1["lat"], h1["lon"], h2["lat"], h2["lon"])
                t = _travel_time(dist, mode)
                cost = dist * MODE_PROFILES[mode]["cost_per_km"]
                
                # Links are listed once in the data but work both ways (N7): add the reverse too.
                for a, b in ((u_vnode, v_vnode), (v_vnode, u_vnode)):
                    if not G.has_edge(a, b):
                        G.add_edge(a, b, baseline_time=t, distance=round(dist, 1),
                                   transport_mode=mode, type="transit", cost=cost)

    # 3b. Trunk sea lanes through the chokepoints, following waypoints around land (N9, N4)
    for lane in sea["trunk_lanes"]:
        a, b = hub_lookup[lane["from"]], hub_lookup[lane["to"]]
        dist = _lane_distance([(a["lat"], a["lon"]), *lane["waypoints"], (b["lat"], b["lon"])])
        for u, v in ((a["id"], b["id"]), (b["id"], a["id"])):
            G.add_edge(f"{u}:sea", f"{v}:sea", baseline_time=_travel_time(dist, "sea"), distance=round(dist, 1),
                       transport_mode="sea", type="transit", cost=dist * MODE_PROFILES["sea"]["cost_per_km"])

    # 3c. A sea hub left with no sea link joins every trunk hub or gate in its basin (e.g. Jeddah -> Bab-el-Mandeb, Suez).
    #     Hubs whose basin has none stay unconnected: the Caspian has no sea route to the ocean.
    anchors = trunk | set(gates)
    for hub_id, basins in basins_of.items():
        node = f"{hub_id}:sea"
        if hub_id in anchors or node not in G:
            continue
        if any(G[node][n]["transport_mode"] == "sea" for n in G.successors(node)):
            continue
        h = hub_lookup[hub_id]
        for x in anchors:
            if basins_of.get(x, set()) & basins:
                dist = _haversine(h["lat"], h["lon"], hub_lookup[x]["lat"], hub_lookup[x]["lon"])
                for u, v in ((hub_id, x), (x, hub_id)):
                    G.add_edge(f"{u}:sea", f"{v}:sea", baseline_time=_travel_time(dist, "sea"), distance=round(dist, 1),
                               transport_mode="sea", type="transit", cost=dist * MODE_PROFILES["sea"]["cost_per_km"])
    # 4. Local Road Auto-wire (<200km)
    for i, h1 in enumerate(hubs):
        if "road" not in h1["modes"]: continue
        for h2 in hubs[i+1:]:
            if "road" not in h2["modes"]: continue
            d = _haversine(h1["lat"], h1["lon"], h2["lat"], h2["lon"])
            if d < 200 and {h1["country"], h2["country"]} not in WATER_SEPARATED:
                u, v = f"{h1['id']}:road", f"{h2['id']}:road"
                if G.has_node(u) and G.has_node(v) and not G.has_edge(u, v):
                    t = _travel_time(d, "road")
                    cost = d * MODE_PROFILES["road"]["cost_per_km"]
                    G.add_edge(u, v, baseline_time=t, distance=round(d, 1), 
                               transport_mode="road", type="transit", cost=cost)
                    G.add_edge(v, u, baseline_time=t, distance=round(d, 1), 
                               transport_mode="road", type="transit", cost=cost)

    print(f"Split-Node Multimodal Network: {G.number_of_nodes()} virtual nodes, {G.number_of_edges()} edges")
    return G

def get_city_capabilities(G):
    city_data = {}
    for node, data in G.nodes(data=True):
        city = data.get("parent_city", data.get("display_name"))
        if city not in city_data:
            city_data[city] = {"id": data.get("physical_id"), "display_name": city, "country": data.get("country"), 
                               "has_port": False, "has_airport": False, "has_rail": False, "nodes": []}
        
        city_data[city]["nodes"].append(node)
        mode = data.get("mode")
        if mode == "sea": city_data[city]["has_port"] = True
        if mode == "air": city_data[city]["has_airport"] = True
        if mode == "rail": city_data[city]["has_rail"] = True

    return sorted(list(city_data.values()), key=lambda c: c["display_name"])

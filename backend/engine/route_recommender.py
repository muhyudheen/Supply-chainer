import networkx as nx
import numpy as np
import math
import time
from typing import List, Dict, Any, Optional
from .multimodal_network import (MODE_PROFILES, CARGO_REASONS, PRIORITY_MULTIPLIERS, create_multimodal_network,
                                 excluded_modes)
from .threat_intelligence import ThreatIntelligencePredictor, ContrastiveNLPEngine, CARFFilter
from .news_ingestion import DynamicNewsIngestor
from .node_resolver import NodeResolver
from .weather_integration import fetch_hub_weather
from ..ml.features import leg_features
from ..ml.predictor import DelayModel, LABELS, VARYING
from ..ml.train import NAMES

# R2: which quantile of the delay model each persona plans with
PERSONA_QUANTILE = {"FASTEST": 0, "BALANCED": 1, "SAFEST": 2}  # p50, p85, p95

class RouteRecommender:
    """
    Supplychainer Unified Multimodal Optimization Engine.
    V8: Virtual-Node Forensic Edition.
    """

    def __init__(self, network, predictor, simulator, scenario_mgr, demo_mode=False):
        self.network = network # Legacy
        self.predictor = predictor
        self.simulator = simulator
        self.scenario_mgr = scenario_mgr
        self.demo_mode = demo_mode
        self.is_warmed_up = False
        self.warmup_failed = False
        
        self.nlp = ContrastiveNLPEngine(lazy_load=True)
        self.carf = CARFFilter()
        self.news_ingestor = DynamicNewsIngestor()
        self.resolver = NodeResolver()
        
        print(f"[STARTUP] Initializing Split-Node Global Topology...")
        self.unified_graph = create_multimodal_network()

        # R2: the leg-delay model (backend/ml). Weather starts at 0 and is fetched at warm-up.
        self.delay_model = DelayModel()
        self.weather = {}
        self.weather_source = "offline (demo mode: not fetched)" if demo_mode else "offline (not fetched yet)"
        self._predict_delays()

        if self.demo_mode:
            self.is_warmed_up = True
            
        print(f"[STARTUP] Unified Engine Ready.")

    def _predict_delays(self):
        """Model delay (p50, p85, p95 hours) for every transit leg, with and without cargo handled at its end.
        Dijkstra can't see a leg's next step, so the extra dwell where cargo is handled is also kept per node
        (median over the legs arriving there) and charged on its transfer and arrival edges while routing."""
        G = self.unified_graph
        edges = [(u, v) for u, v, d in G.edges(data=True) if d["type"] == "transit"]
        # news: live news isn't wired yet (R4), so every leg's news score is 0
        rows = [leg_features(G, u, v, cargo_handled=h, weather=self.weather.get(G.nodes[v]["physical_id"], 0.0))
                for u, v in edges for h in (False, True)]
        pred = self.delay_model.predict(rows)
        extra = {}
        for i, (u, v) in enumerate(edges):
            passing, handled = pred[2 * i], pred[2 * i + 1]
            G[u][v]["delay_q"] = {False: tuple(map(float, passing)), True: tuple(map(float, handled))}
            extra.setdefault(v, []).append(handled - passing)
        for n in G.nodes:
            G.nodes[n]["dwell_q"] = tuple(map(float, np.maximum(np.median(extra[n], axis=0), 0))) if n in extra \
                else (0.0, 0.0, 0.0)

    def set_weather(self, severity_by_hub, source):
        """Use this weather (0-1 per hub id; missing hubs are 0) and re-predict every leg."""
        self.weather = dict(severity_by_hub)
        self.weather_source = source
        self._predict_delays()

    def refresh_weather(self, fetcher=fetch_hub_weather):
        """Live weather at every hub; if it can't be fetched, weather is 0 and the status says offline."""
        coords = {d["physical_id"]: (d["lat"], d["lon"]) for _, d in self.unified_graph.nodes(data=True)}
        try:
            w = fetcher(coords)
            self.set_weather(w, f"live Open-Meteo, {len(w)} hubs, fetched {time.strftime('%H:%M UTC', time.gmtime())}")
        except Exception as e:
            print(f"[WEATHER] Offline, using weather 0: {e}")
            self.set_weather({}, f"offline ({type(e).__name__}): weather 0 everywhere")

    def model_status(self):
        return {"delay_model": self.delay_model.status(), "weather_source": self.weather_source}

    def run_background_warmup(self):
        if self.is_warmed_up: return
        self.refresh_weather()
        print("[WARMUP] Calibrating global threat floor...")
        try:
            self.predictor.warmup()
            self.nlp.warmup()
            if not self.nlp._ready:
                raise RuntimeError("NLP engine failed to load; see the [NLP ENGINE] message above")

            
            # Baseline intelligence: no live news has been fetched for any edge yet, so there is
            # no evidence of a threat. Scoring the invented fallback sentences ("Maritime congestion
            # reported...") would put a fake threat on every edge of a mode (W1).
            for u, v, d in self.unified_graph.edges(data=True):
                if d.get("transport_mode") == "transfer": continue
                self.unified_graph[u][v]["base_threat"] = 0.0
                self.unified_graph[u][v]["base_news"] = "No live news for this corridor"
                
            self.is_warmed_up = True
            print("[WARMUP] Unified Calibration Complete.")
        except Exception as e:
            print(f"[WARMUP] Error during warmup: {e}")
            self.warmup_failed = True

    def recommend(self, source: str, destination: str, transport_preference: str = "any", 
                  routing_policy: str = "STRICT", cargo_type: str = "general", 
                  priority: str = "normal", scenario: str = None, 
                  overrides: dict = None) -> dict:
        
        t0 = time.perf_counter()
        overrides = overrides or {}
        avoid_hubs = overrides.get("avoid_chokepoints", [])
        cost_ceiling = overrides.get("cost_ceiling", 999999)
        max_delay = overrides.get("max_delay", 9999)
        
        # 1. Resolve Entry/Exit (Virtual Nodes)
        res_s = self.resolver.resolve_entry_nodes(source)
        res_d = self.resolver.resolve_entry_nodes(destination)
        
        # M13: "status" is the HTTP code main.py sends with the error (400 bad input, 404 no route)
        if "error" in res_s: return {"error": res_s["error"], "status": 400}
        if "error" in res_d: return {"error": res_d["error"], "status": 400}
        
        SRC, DST = "__SOURCE__", "__DEST__"
        
        # 2. Scenario Activation
        if scenario and scenario not in self.scenario_mgr.SCENARIOS:  # M7: a typo must not mean "no scenario"
            return {"error": f"Unknown scenario '{scenario}'. Valid: {', '.join(self.scenario_mgr.SCENARIOS)}", "status": 400}
        active_scenario = self.scenario_mgr.SCENARIOS.get(scenario) if scenario else None
        disruptions = self.scenario_mgr.get_disruptions(scenario)
        # R9: threat 1.0 means closed, not just slow: those hubs are taken out of the graph
        closed_hubs = sorted(p for p, d in disruptions.items() if d["threat"] >= 1.0)

        def disruption_at(node_data):
            """S2: a scenario only hits arrivals in its own mode (a road flood doesn't slow ships)."""
            d = disruptions.get(node_data.get("physical_id"))
            return d if d and node_data.get("mode") == d["mode"] else None
        
        blocked_modes = excluded_modes(cargo_type)

        # R6: cargo type and priority are checked and reported, not silently ignored
        cargo_types = ["general", *CARGO_REASONS]
        if cargo_type not in cargo_types:
            return {"error": f"Unknown cargo_type '{cargo_type}'. Valid: {', '.join(cargo_types)}", "status": 400}
        if priority not in PRIORITY_MULTIPLIERS:
            return {"error": f"Unknown priority '{priority}'. Valid: {', '.join(PRIORITY_MULTIPLIERS)}", "status": 400}
        cargo_rule = f"{cargo_type} cargo can't go by {', '.join(blocked_modes)}: {CARGO_REASONS.get(cargo_type, '')}"
        if transport_preference in blocked_modes:
            return {"error": cargo_rule, "status": 400}
        balanced_time_weight = 0.3
        cargo_rules = {
            "cargo_type": cargo_type,
            "excluded_modes": blocked_modes,
            "reasons": [f"{m}: {CARGO_REASONS[cargo_type]}" for m in blocked_modes],
            "priority": priority,
            "balanced_time_weight": round(balanced_time_weight, 2),
        }

        # 3. Persona Optimization
        candidates = []
        for persona in ["FASTEST", "SAFEST", "BALANCED"]:
            qi = PERSONA_QUANTILE[persona]
            try:
                # Build Persona Graph (Applying STRICT constraints)
                G_p = self.unified_graph.copy()
                
                # Apply Hub Avoidance and closures (Prune all virtual nodes for the hub)
                for hub_id in [*avoid_hubs, *closed_hubs]:
                    nodes_to_remove = [n for n, d in G_p.nodes(data=True) if d.get("physical_id") == hub_id]
                    G_p.remove_nodes_from(nodes_to_remove)
                
                # Apply Transport Preference
                if transport_preference != "any" and routing_policy == "STRICT":
                    allowed_modes = [transport_preference, "transfer", "road"]
                    edges_to_remove = []
                    for u, v, d in G_p.edges(data=True):
                        if d["transport_mode"] not in allowed_modes:
                            edges_to_remove.append((u, v))
                    G_p.remove_edges_from(edges_to_remove)
                    
                if blocked_modes:
                    G_p.remove_edges_from([(u, v) for u, v, d in G_p.edges(data=True) if d["transport_mode"] in blocked_modes])

                # L1: the trip may start and end in any mode at origin/destination, at no cost
                for n in res_s["nodes"]:
                    if n in G_p: G_p.add_edge(SRC, n, baseline_time=0, cost=0, transport_mode="access", type="access", base_threat=0)
                for n in res_d["nodes"]:
                    if n in G_p: G_p.add_edge(n, DST, baseline_time=0, cost=0, transport_mode="access", type="access", base_threat=0)

                def weight_func(u, v, d):
                    mode = d["transport_mode"]
                    base_t = d["baseline_time"]
                    base_c = d.get("cost", 0)
                    
                    # Intelligence Factor (Mapped to physical node)
                    hit = disruption_at(G_p.nodes[v])
                    
                    threat = d.get("base_threat", 0.05)
                    delay = 0
                    
                    if hit:
                        threat = max(threat, hit["threat"])
                        delay += hit["delay"]

                    # R2: the model's delay at this persona's quantile; dwell is charged where cargo is handled
                    if d["type"] == "transit":
                        delay += d["delay_q"][False][qi]
                    elif d["type"] == "transfer" or v == DST:
                        delay += G_p.nodes[u].get("dwell_q", (0.0, 0.0, 0.0))[qi]
                    
                    if persona == "FASTEST":
                        return base_t + delay
                    elif persona == "SAFEST":
                        risk_penalty = 1.0 + (threat * 12.0)
                        return (base_t + delay) * risk_penalty
                    else: # BALANCED (ECONOMIC leaning)
                        # High cost penalty for transfers and expensive modes
                        time_weight = balanced_time_weight
                        cost_weight = 0.5
                        risk_weight = 0.2
                        return (base_t + delay)*time_weight + (base_c / 150.0)*cost_weight + (threat * 40.0)*risk_weight

                path = nx.dijkstra_path(G_p, SRC, DST, weight=weight_func)
                
                # Compose Multimodal Path Details
                legs = []
                total_time, total_cost, max_threat = 0, 0, 0
                range_sums, model_rows = np.zeros(3), []
                trace = {
                    "eta": {"transit": 0, "transfer": 0, "scenario": 0, "predicted_delay": 0},
                    "cost": {"transit": 0, "transfer": 0, "scenario": 0},
                    "risk": {"baseline": 0, "scenario": 0}
                }

                for i in range(len(path)-1):
                    u, v = path[i], path[i+1]
                    if u == SRC or v == DST: continue
                    d = G_p[u][v]
                    mode = d["transport_mode"]
                    v_data = G_p.nodes[v]
                    p_id = v_data.get("physical_id")
                    
                    base_time = d["baseline_time"]
                    l_time = base_time
                    base_cost = d.get("cost", 0)
                    l_cost = base_cost
                    base_threat = d.get("base_threat", 0.05)
                    l_threat = base_threat
                    l_news = d.get("base_news", "Standard conditions")
                    l_source = "FALLBACK"
                    
                    hit = disruption_at(v_data)
                    if hit:
                        l_time += hit["delay"]
                        l_threat = max(l_threat, hit["threat"])
                        l_news = hit["reason"]
                        l_source = "SCENARIO"
                        trace["eta"]["scenario"] += hit["delay"]
                        trace["risk"]["scenario"] = max(trace["risk"]["scenario"], l_threat)
                        surcharge = base_cost * 0.1  # R11: the surcharge is charged, not just reported
                        l_cost += surcharge
                        trace["cost"]["scenario"] += surcharge

                    # R2: the model's delay for this leg; cargo is handled where the next step is a transfer or the end
                    handled, q = False, (0.0, 0.0, 0.0)
                    if d["type"] == "transit":
                        handled = path[i + 2] == DST or G_p[v][path[i + 2]]["type"] == "transfer"
                        q = d["delay_q"][handled]
                        l_time += q[0]  # every card shows p50, so cards compare like with like
                        trace["eta"]["predicted_delay"] += q[0]
                        range_sums += q
                        model_rows.append(leg_features(G_p, u, v, cargo_handled=handled,
                                                       weather=self.weather.get(p_id, 0.0)))
                    
                    # R10: the buckets get base hours; the scenario delay is only in the scenario bucket
                    if d["type"] == "transfer":
                        trace["eta"]["transfer"] += base_time
                        trace["cost"]["transfer"] += base_cost
                    else:
                        trace["eta"]["transit"] += base_time
                        trace["cost"]["transit"] += base_cost
                        # R12: baseline is the leg's own threat, before any scenario
                        trace["risk"]["baseline"] = max(trace["risk"]["baseline"], base_threat)

                    total_time += l_time
                    total_cost += l_cost
                    max_threat = max(max_threat, l_threat)
                    
                    legs.append({
                        "from": G_p.nodes[u].get("physical_id", u),
                        "to": p_id,
                        "to_name": v_data.get("display_name", p_id),
                        "mode": mode.upper(),
                        "type": d["type"],
                        "eta": round(l_time, 1),
                        "cost": round(l_cost, 2),
                        "threat": round(l_threat, 2),
                        "reason": l_news,
                        "intel_source": l_source,
                        "delay": {n: round(float(x), 1) for n, x in zip(NAMES, q)},
                        "cargo_handled": handled
                    })

                if total_cost > cost_ceiling or total_time > (max_delay * 24): continue
                schedule = total_time - trace["eta"]["predicted_delay"]  # transit + transfer + scenario
                eta_range = {n: round(float(schedule + x), 1) for n, x in zip(NAMES, range_sums)}
                trace["delay_drivers"] = self._delay_drivers(model_rows, qi)
                trace["eta"] = {k: round(v, 1) for k, v in trace["eta"].items()}
                trace["cost"] = {k: round(v, 2) for k, v in trace["cost"].items()}

                candidates.append({
                    "persona": persona,
                    "primary_mode": "MULTIMODAL",
                    "legs": legs,
                    "adjusted_eta": round(total_time, 1),
                    "eta_range": eta_range,
                    "total_cost": round(total_cost, 2),
                    "threat_level": round(max_threat, 2),
                    "audit_trace": trace,
                    "override_applied": bool(avoid_hubs or cost_ceiling < 999999)
                })

            except nx.NetworkXNoPath:
                continue
            except Exception as e:
                print(f"[ROUTING ERROR] {persona}: {e}")

        if not candidates:
            error = "No valid multimodal route found under the current constraints."
            if blocked_modes:  # R6: say which cargo rule removed the options
                error += f" {cargo_rule}"
            return {"error": error, "status": 404}

        # R18: explanations compare the routes against each other, using only real numbers
        by_persona = {c["persona"]: c for c in candidates}
        for c in candidates:
            c["explanation"] = self._explain(c, by_persona) + self._explain_range(c)

        # Deduplicate and sort. R17: a persona that picked the same route (same stops and modes)
        # is listed on the card that shows it, instead of being dropped without a word.
        final = []
        seen = {}
        for c in sorted(candidates, key=lambda x: x["adjusted_eta"]):
            path_sig = tuple((l["to"], l["mode"]) for l in c["legs"])
            if path_sig in seen:
                seen[path_sig]["also_best_for"].append(c["persona"])
            else:
                c["also_best_for"] = []
                final.append(c)
                seen[path_sig] = c
        for c in final:
            if c["also_best_for"]:
                c["explanation"] += f" Also the {' and '.join(c['also_best_for'])} choice: no other route did better on that."

        return {
            "origin": source, "destination": destination,
            "active_scenario": active_scenario["name"] if active_scenario else None,
            "closed_hubs": closed_hubs,
            "cargo_rules": cargo_rules,
            "recommendations": final[:3]
        }

    def _delay_drivers(self, rows, qi):
        """SHAP for the route: calm transit hours plus each feature's share (exact Shapley values, backend/ml/predictor.py)."""
        calm, phi = self.delay_model.explain(rows, qi)
        drivers = sorted(({"feature": f, "label": LABELS[f], "hours": round(float(phi[f].sum()), 2)} for f in VARYING),
                         key=lambda x: -abs(x["hours"]))
        return {"quantile": NAMES[qi], "calm_transit_h": round(float(calm.sum()), 2), "drivers": drivers,
                "total_h": round(float(calm.sum() + sum(phi[f].sum() for f in VARYING)), 2)}

    @staticmethod
    def _explain_range(c):
        """The ETA range and the two biggest delay drivers, as numbers read off the card."""
        r = c["eta_range"]
        text = f" ETA range: p50 {r['p50']}h, p85 {r['p85']}h, p95 {r['p95']}h."
        top = [x for x in c["audit_trace"]["delay_drivers"]["drivers"] if x["hours"] >= 0.5][:2]
        if top:
            text += f" Biggest delay drivers ({c['audit_trace']['delay_drivers']['quantile']}): " + ", ".join(f"{x['label']} +{x['hours']:.1f}h" for x in top) + "."
        return text

    @staticmethod
    def _explain(c, by_persona):
        """R18: every number here is read off the routes (no fixed percentages)."""
        eta, cost, threat = c["adjusted_eta"], c["total_cost"], c["threat_level"]
        transfers = sum(leg["type"] == "transfer" for leg in c["legs"])
        facts = f"{eta}h, ${cost:,.0f}, peak threat {threat}, {transfers} transfer{'s' if transfers != 1 else ''}."
        fast = by_persona.get("FASTEST")

        if c["persona"] == "FASTEST" or not fast:
            slower = [o for o in by_persona.values() if o["adjusted_eta"] > eta]
            if not slower:
                return f"Fastest route: {facts}"
            nxt = min(slower, key=lambda o: o["adjusted_eta"])
            return f"Fastest route: {facts} {nxt['adjusted_eta'] - eta:.1f}h quicker than {nxt['persona']}."

        dt, dc = eta - fast["adjusted_eta"], cost - fast["total_cost"]
        vs_fast = f"{dt:+.1f}h and ${abs(dc):,.0f} {'more' if dc >= 0 else 'less'} than FASTEST"
        if c["persona"] == "SAFEST":
            # R20: only claim to avoid FASTEST's threat when ours is actually lower.
            ft = fast["threat_level"]
            if threat < ft:
                risk = f"Avoids FASTEST's peak threat of {ft}"
            elif threat == ft:
                risk = f"Same peak threat as FASTEST ({ft})"
            else:
                risk = f"Higher peak threat than FASTEST ({ft})"
            # R2: SAFEST plans with p95, so say what that bought against FASTEST's bad case
            tail = fast["eta_range"]["p95"] - c["eta_range"]["p95"]
            tail_text = f"p95 is {abs(tail):.1f}h {'lower' if tail > 0 else 'higher'} than FASTEST's" if tail \
                else "p95 is the same as FASTEST's"
            return f"Lowest-risk route: {facts} {risk}, for {vs_fast}. Its {tail_text}."
        return f"Cost-time balance: {facts} {vs_fast}."

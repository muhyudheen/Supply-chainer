import json
import os
from typing import Dict, Optional, Any

class NodeResolver:
    """
    Supplychainer Unified Node Resolver.
    V4: Virtual Node Edition (Forensic Fix).
    """
    def __init__(self, locations_path: str = None, hubs_path: str = None):
        if not locations_path:
            locations_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'canonical_locations.json')
        if not hubs_path:
            hubs_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'canonical_hubs.json')
            
        self.location_map = {}
        if os.path.exists(locations_path):
            with open(locations_path, 'r') as f:
                self.location_map = json.load(f)
                
        self.hubs = []
        if os.path.exists(hubs_path):
            with open(hubs_path, 'r') as f:
                self.hubs = json.load(f)

    def resolve_node_to_entry_point(self, location_or_id: str) -> Dict[str, Any]:
        """
        Resolves a location to its primary virtual entry node in the Split Graph.
        """
        physical_id = None
        current_hub = next((h for h in self.hubs if h["id"] == location_or_id), None)
        
        # City level
        if location_or_id in self.location_map:
            physical_id = self.location_map[location_or_id].get("road")
            if not physical_id:
                physical_id = list(self.location_map[location_or_id].values())[0]
        
        # ID level
        elif current_hub:
            physical_id = location_or_id

        if not physical_id:
            return {"id": None, "error": f"Entry point unavailable for {location_or_id}"}

        # For the split graph, we usually enter through 'road' (DC) or the hub's primary mode
        target_hub = next((h for h in self.hubs if h["id"] == physical_id), None)
        if not target_hub:
            return {"id": None, "error": f"Physical Hub mapping corrupted for {physical_id}"}
            
        entry_mode = "road" if "road" in target_hub["modes"] else target_hub["modes"][0]
        return {"id": f"{physical_id}:{entry_mode}"}
    
    def resolve_entry_nodes(self, location_or_id: str) -> Dict[str, Any]:
        """Every node a trip may start or end at: all modes of a hub (for a hub ID),
        or each of a city's per-mode hubs (for a city name). Fixes L1."""
        hubs_by_id = {h["id"]: h for h in self.hubs}
        if location_or_id in self.location_map:
            pairs = [(hub_id, mode) for mode, hub_id in self.location_map[location_or_id].items()]
        elif location_or_id in hubs_by_id:
            pairs = [(location_or_id, mode) for mode in hubs_by_id[location_or_id]["modes"]]
        else:
            return {"error": f"Entry point unavailable for {location_or_id}"}
        nodes = [f"{h}:{m}" for h, m in pairs if h in hubs_by_id and m in hubs_by_id[h]["modes"]]
        return {"nodes": nodes} if nodes else {"error": f"Physical Hub mapping corrupted for {location_or_id}"}

    def resolve_node(self, location_or_id: str, mode: str = "any") -> str:
        """Legacy support"""
        res = self.resolve_node_to_entry_point(location_or_id)
        return res.get("id")

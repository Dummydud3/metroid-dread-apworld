"""
Reachability helpers for Metroid Bread.

Live generation uses worlds.metroid_bread.dread_logic.DreadLogic.
This module remains for offline scripts (generate_rules_*.py) that import
ReachabilityAnalyzer; prefer DreadLogic for new code.
"""

from pathlib import Path
from typing import Dict, Set, List, Tuple, FrozenSet, Optional
from .logic_parser import RandovaniaLogicParser

try:
    from .Events import EVENT_RESOURCE_TO_ITEM
except ImportError:
    EVENT_RESOURCE_TO_ITEM = {}


class ReachabilityAnalyzer:
    """Legacy BFS analyzer used by offline rule generators."""

    def __init__(self, parser: RandovaniaLogicParser):
        self.parser = parser
        self.cache = {}

    def evaluate_requirement(self, req: Dict, items: FrozenSet[str]) -> bool:
        if not req:
            return True
        req_type = req.get("type")
        if req_type == "trivial":
            return True
        if req_type == "impossible":
            return False
        if req_type == "resource":
            data = req.get("data", {})
            resource_type = data.get("type")
            resource_name = data.get("name")
            negate = data.get("negate", False)
            ap_item = self.parser._map_resource_to_ap_item(resource_type, resource_name)
            if resource_type == "events":
                ap_item = EVENT_RESOURCE_TO_ITEM.get(resource_name, ap_item)
            if ap_item is None:
                # Always-on items / misc handled as satisfied unless negated misc
                if resource_type == "misc":
                    has = False
                else:
                    has = True
            else:
                has = ap_item in items
            return (not has) if negate else has
        if req_type == "template":
            template_name = req.get("data")
            if template_name in self.parser.templates:
                template_req = self.parser.templates[template_name].get("requirement")
                return self.evaluate_requirement(template_req, items)
            return True
        if req_type == "and":
            req_items = req.get("data", {}).get("items", [])
            return all(self.evaluate_requirement(item, items) for item in req_items)
        if req_type == "or":
            req_items = req.get("data", {}).get("items", [])
            if not req_items:
                return False
            return any(self.evaluate_requirement(item, items) for item in req_items)
        return True

    def get_reachable_nodes(self, starting_node: Tuple[str, str, str], items: FrozenSet[str]) -> Set[Tuple[str, str, str]]:
        reachable = set()
        queue = [starting_node]
        reachable.add(starting_node)
        while queue:
            current = queue.pop(0)
            region, area, node = current
            connections = self.parser.get_node_connections(region, area, node)
            for target_region, target_area, target_node, requirement in connections:
                target = (target_region, target_area, target_node)
                if target in reachable:
                    continue
                if self.evaluate_requirement(requirement, items):
                    reachable.add(target)
                    queue.append(target)
        return reachable

    def get_reachable_pickups(self, starting_node: Tuple[str, str, str], items: FrozenSet[str]) -> Set[Tuple[str, str, str]]:
        all_reachable = self.get_reachable_nodes(starting_node, items)
        pickups = set()
        for region, area, node in all_reachable:
            if region not in self.parser.regions:
                continue
            region_data = self.parser.regions[region]
            if "areas" not in region_data or area not in region_data["areas"]:
                continue
            area_data = region_data["areas"][area]
            if "nodes" not in area_data or node not in area_data["nodes"]:
                continue
            node_data = area_data["nodes"][node]
            if node_data.get("node_type") == "pickup":
                pickups.add((region, area, node))
        return pickups

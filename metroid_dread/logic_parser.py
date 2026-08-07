
import json
import os
import pkgutil
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional

LOGIC_DATABASE_DIRNAME = "logic_database"

REGION_FILES: Tuple[str, ...] = (
    "Artaria.json", "Cataris.json", "Dairon.json", "Burenia.json",
    "Ferenia.json", "Ghavoran.json", "Hanubia.json", "Elun.json", "Itorash.json",
)

_PACKAGE = __package__ or None

def read_database_bytes(filename: str, fallback_dir: Optional[Path]) -> bytes:
    if _PACKAGE:
        try:
            data = pkgutil.get_data(_PACKAGE, f"{LOGIC_DATABASE_DIRNAME}/{filename}")
        except OSError:
            data = None
        if data is not None:
            return data

    if fallback_dir is not None:
        return (fallback_dir / filename).read_bytes()

    raise FileNotFoundError(
        f"Could not locate logic database file '{filename}' via package '{_PACKAGE}' "
        "or filesystem fallback."
    )

class RandovaniaLogicParser:
    
    def __init__(self, logic_db_path: str = ""):
        self.logic_db_path = Path(logic_db_path) if logic_db_path else None
        self.header = None
        self.regions = {}
        self.templates = {}
        self.resources = {}
        self.dock_weaknesses = {}
        
    def load_database(self):
        print("Loading Randovania logic database...")
        
        header_bytes = read_database_bytes("header.json", self.logic_db_path)
        self.header = json.loads(header_bytes.decode("utf-8"))
        
        if "resource_database" in self.header:
            self.resources = self.header["resource_database"]
            
            if "requirement_template" in self.resources:
                self.templates = self.resources["requirement_template"]
        
        if "dock_weakness_database" in self.header:
            self.dock_weaknesses = self.header["dock_weakness_database"]
        
        for region_file in REGION_FILES:
            try:
                region_bytes = read_database_bytes(region_file, self.logic_db_path)
            except (FileNotFoundError, OSError):
                continue
            region_data = json.loads(region_bytes.decode("utf-8"))
            self.regions[region_data["name"]] = region_data
            print(f"  Loaded {region_data['name']}")
        
        print(f"[OK] Loaded {len(self.regions)} regions")
        print(f"[OK] Loaded {len(self.resources.get('items', {}))} items")
        print(f"[OK] Loaded {len(self.templates)} requirement templates")
        
    def get_pickup_locations(self) -> List[Tuple[str, str, str, str]]:
        locations = []
        
        for region_name, region_data in self.regions.items():
            if "areas" not in region_data:
                continue
            
            for area_name, area_data in region_data["areas"].items():
                if "nodes" not in area_data:
                    continue
                
                for node_name, node_data in area_data["nodes"].items():
                    if node_data.get("node_type") == "pickup":
                        pickup_index = node_data.get("extra", {}).get("pickup_index", 0)
                        locations.append((region_name, area_name, node_name, pickup_index))
        
        return locations
    
    def get_dock_connections(self) -> List[Tuple[str, str, str, str, str, str, Any]]:
        connections = []
        
        for region_name, region_data in self.regions.items():
            if "areas" not in region_data:
                continue
            
            for area_name, area_data in region_data["areas"].items():
                if "nodes" not in area_data:
                    continue
                
                for node_name, node_data in area_data["nodes"].items():
                    if node_data.get("node_type") == "dock":
                        default_conn = node_data.get("default_connection")
                        if default_conn:
                            target_region = default_conn.get("region", region_name)
                            target_area = default_conn["area"]
                            target_node = default_conn["node"]
                            
                            dock_weakness = node_data.get("default_dock_weakness")
                            requirement = self._get_dock_weakness_requirement(dock_weakness)
                            
                            connections.append((
                                region_name, area_name, node_name,
                                target_region, target_area, target_node,
                                requirement
                            ))
        
        return connections
    
    def get_node_connections(self, region_name: str, area_name: str, node_name: str) -> List[Tuple[str, str, str, Any]]:
        connections = []
        
        if region_name not in self.regions:
            return connections
        
        region = self.regions[region_name]
        if "areas" not in region or area_name not in region["areas"]:
            return connections
        
        area = region["areas"][area_name]
        if "nodes" not in area or node_name not in area["nodes"]:
            return connections
        
        node = area["nodes"][node_name]
        node_type = node.get("node_type")
        node_connections = node.get("connections", {})
        
        if node_type == "dock":
            default_conn = node.get("default_connection")
            
            if default_conn:
                target_region = default_conn.get("region", region_name)
                target_area = default_conn.get("area")
                target_node = default_conn.get("node")
                
                dock_weakness = node.get("default_dock_weakness", "Power Beam Door")
                requirement = self._get_dock_weakness_requirement(dock_weakness)
                
                connections.append((target_region, target_area, target_node, requirement))
        
        for target_node_name, requirement in node_connections.items():
            connections.append((region_name, area_name, target_node_name, requirement))
        
        return connections
    
    def get_starting_nodes(self) -> List[Tuple[str, str, str]]:
        starting_nodes = []
        
        for region_name, region_data in self.regions.items():
            if "areas" not in region_data:
                continue
            
            for area_name, area_data in region_data["areas"].items():
                if "nodes" not in area_data:
                    continue
                
                for node_name, node_data in area_data["nodes"].items():
                    if node_data.get("valid_starting_location", False):
                        starting_nodes.append((region_name, area_name, node_name))
        
        return starting_nodes
    
    def _get_dock_weakness_requirement(self, weakness_name: Optional[str]) -> Dict:
        if not weakness_name or weakness_name == "Power Beam Door":
            return {"type": "trivial"}
        
        if "dock_weakness_database" not in self.header:
            return {"type": "impossible"}
        
        dock_db = self.header["dock_weakness_database"]
        
        if "types" in dock_db and "door" in dock_db["types"]:
            door_items = dock_db["types"]["door"].get("items", {})
            if weakness_name in door_items:
                door_data = door_items[weakness_name]
                if "lock" in door_data and door_data["lock"]:
                    lock_req = door_data["lock"].get("requirement")
                    if lock_req:
                        return lock_req
                return door_data.get("requirement", {"type": "trivial"})
        
        if "types" in dock_db and "tunnel" in dock_db["types"]:
            tunnel_items = dock_db["types"]["tunnel"].get("items", {})
            if weakness_name in tunnel_items:
                tunnel_data = tunnel_items[weakness_name]
                return tunnel_data.get("requirement", {"type": "trivial"})
        
        return {"type": "trivial"}
    
    def resolve_requirement(self, req: Any, context: str = "") -> Optional[str]:
        if req is None:
            return "True"
        
        if isinstance(req, dict):
            req_type = req.get("type")
            
            if req_type == "trivial":
                return "True"
            
            if req_type == "impossible":
                return "False"
            
            if req_type == "resource":
                data = req.get("data", {})
                resource_type = data.get("type")
                resource_name = data.get("name")
                amount = data.get("amount", 1)
                negate = data.get("negate", False)
                
                ap_item = self._map_resource_to_ap_item(resource_type, resource_name)
                if not ap_item:
                    return None
                
                if amount == 1:
                    result = f"state.has('{ap_item}', player)"
                else:
                    result = f"state.has('{ap_item}', player, {amount})"
                
                if negate:
                    result = f"not ({result})"
                
                return result
            
            if req_type == "template":
                template_name = req.get("data")
                if template_name in self.templates:
                    return self.resolve_requirement(self.templates[template_name], f"template:{template_name}")
                return None
            
            if req_type == "and":
                items = req.get("data", {}).get("items", [])
                sub_reqs = [self.resolve_requirement(item, f"{context}/and") for item in items]
                sub_reqs = [r for r in sub_reqs if r is not None and r != "True"]
                
                if not sub_reqs:
                    return "True"
                if "False" in sub_reqs:
                    return "False"
                if len(sub_reqs) == 1:
                    return sub_reqs[0]
                
                return "(" + " and ".join(sub_reqs) + ")"
            
            if req_type == "or":
                items = req.get("data", {}).get("items", [])
                sub_reqs = [self.resolve_requirement(item, f"{context}/or") for item in items]
                sub_reqs = [r for r in sub_reqs if r is not None and r != "False"]
                
                if not sub_reqs:
                    return "False"
                if "True" in sub_reqs:
                    return "True"
                if len(sub_reqs) == 1:
                    return sub_reqs[0]
                
                return "(" + " or ".join(sub_reqs) + ")"
        
        return None
    
    def _map_resource_to_ap_item(self, resource_type: str, resource_name: str) -> Optional[str]:
        if resource_type == "items":
            item_mapping = {
                "Power": None,
                "Wide": "Wide Beam",
                "Plasma": "Plasma Beam",
                "Wave": "Wave Beam",
                "Hyper": None,
                "Charge": "Charge Beam",
                "Diffusion": "Diffusion Beam",
                "Grapple": "Grapple Beam",
                "MissileLauncher": None,
                "Supers": "Super Missile",
                "Ice": "Ice Missile",
                "Storm": "Storm Missile",
                "MissileAmmo": None,
                "Cloak": "Phantom Cloak",
                "Flash": "Flash Shift",
                "Pulse": "Pulse Radar",
                "Morph": "Morph Ball",
                "Bomb": "Bomb",
                "Cross": "Cross Bomb",
                "MainPB": "Power Bomb",
                "PBAmmo": "Power Bomb",
                "Magnet": "Spider Magnet",
                "Speed": "Speed Booster",
                "Spin": "Spin Boost",
                "Space": "Space Jump",
                "Screw": "Screw Attack",
                "Slide": None,
                "PowerSuit": None,
                "Varia": "Varia Suit",
                "Gravity": "Gravity Suit",
                "HyperSuit": None,
                "ETank": "Energy Tank",
                "EFragment": "Energy Part",
                "FlashUpgrade": "Flash Shift Upgrade",
                "SpeedBoostUpgrade": "Speed Booster Upgrade",
                "Nothing": None,
                "Metroidnization": None,
            }
            
            mapped = item_mapping.get(resource_name)
            if mapped:
                return mapped
            
            return None
        
        elif resource_type == "events":
            try:
                from .Events import EVENT_RESOURCE_TO_ITEM
                return EVENT_RESOURCE_TO_ITEM.get(resource_name)
            except ImportError:
                return f"Event - {resource_name}"

        elif resource_type == "tricks":
            return None

        elif resource_type == "damage":
            return None

        return None

def main():
    logic_path = Path(__file__).parent / "logic_database"
    parser = RandovaniaLogicParser(logic_path)
    parser.load_database()
    
    locations = parser.get_pickup_locations()
    print(f"\n[OK] Found {len(locations)} pickup locations")
    
    print("\nExample locations:")
    for i, (region, area, node, idx) in enumerate(locations[:5]):
        print(f"  {region} - {area} - {node} (pickup #{idx})")
    
    connections = parser.get_dock_connections()
    print(f"\n[OK] Found {len(connections)} dock connections (doors/teleporters)")
    
    print("\nExample connections:")
    for i, (sr, sa, sn, tr, ta, tn, req) in enumerate(connections[:5]):
        print(f"  {sr}/{sa}/{sn} -> {tr}/{ta}/{tn}")

if __name__ == "__main__":
    main()

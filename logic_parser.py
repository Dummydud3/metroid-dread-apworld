"""
Randovania Logic Database Parser for Archipelago
Parses Randovania's logic JSON files and converts them to Archipelago rules
"""

import json
import os
import pkgutil
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional

# Name of the folder (relative to this file) that holds the logic database.
LOGIC_DATABASE_DIRNAME = "logic_database"

# Fixed list of region files that make up the logic database. Kept as an
# explicit list (rather than directory globbing) so files can be read via
# pkgutil, which works both from a plain folder *and* from inside a zipped
# .apworld (globbing a directory living inside a zip is not reliably
# supported the way filesystem globbing is).
REGION_FILES: Tuple[str, ...] = (
    "Artaria.json", "Cataris.json", "Dairon.json", "Burenia.json",
    "Ferenia.json", "Ghavoran.json", "Hanubia.json", "Elun.json", "Itorash.json",
)

# This module's own package, e.g. "worlds.metroid_bread". When the world is
# installed as a .apworld and loaded via zipimport, this is still set
# correctly, and pkgutil.get_data() knows how to pull files out of the zip
# using the loader's get_data() (unlike plain open(), which only understands
# real filesystem paths). When this file is executed directly as a script
# (e.g. `python logic_parser.py` from inside worlds/metroid_bread/ for local
# tooling), __package__ is empty and we fall back to filesystem access.
_PACKAGE = __package__ or None


def read_database_bytes(filename: str, fallback_dir: Optional[Path]) -> bytes:
    """Read a logic_database file in a way that works both as a loose folder
    and packaged inside a .apworld zip.
    """
    if _PACKAGE:
        try:
            data = pkgutil.get_data(_PACKAGE, f"{LOGIC_DATABASE_DIRNAME}/{filename}")
        except (OSError, ValueError):
            # ValueError: "<pkg>.__spec__ is None" from incomplete synthetic packages.
            data = None
        if data is not None:
            return data

    # Fallback: plain filesystem read, used for standalone dev scripts that
    # import this module outside of the `worlds` package, or point at an
    # arbitrary logic_db_path (e.g. a Randovania checkout).
    if fallback_dir is not None:
        return (fallback_dir / filename).read_bytes()

    raise FileNotFoundError(
        f"Could not locate logic database file '{filename}' via package '{_PACKAGE}' "
        "or filesystem fallback."
    )


class RandovaniaLogicParser:
    """Parse Randovania logic database and convert to Archipelago rules"""
    
    def __init__(self, logic_db_path: str = ""):
        self.logic_db_path = Path(logic_db_path) if logic_db_path else None
        self.header = None
        self.regions = {}
        self.templates = {}
        self.resources = {}
        self.dock_weaknesses = {}
        
    def load_database(self):
        """Load all logic database files"""
        print("Loading Randovania logic database...")
        
        # Load header (resources, templates, tricks)
        header_bytes = read_database_bytes("header.json", self.logic_db_path)
        self.header = json.loads(header_bytes.decode("utf-8"))
        
        # Extract resources
        if "resource_database" in self.header:
            self.resources = self.header["resource_database"]
            
            # Templates are nested inside resource_database
            if "requirement_template" in self.resources:
                self.templates = self.resources["requirement_template"]
        
        # Extract dock weaknesses (door types)
        if "dock_weakness_database" in self.header:
            self.dock_weaknesses = self.header["dock_weakness_database"]
        
        # Load all region files
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
        """
        Get all pickup locations across all regions
        Returns: List of (region, area, node_name, pickup_index) tuples
        """
        locations = []
        
        for region_name, region_data in self.regions.items():
            if "areas" not in region_data:
                continue
            
            for area_name, area_data in region_data["areas"].items():
                if "nodes" not in area_data:
                    continue
                
                for node_name, node_data in area_data["nodes"].items():
                    # Check if this is a pickup node
                    if node_data.get("node_type") == "pickup":
                        # Extract pickup index from extra data
                        pickup_index = node_data.get("extra", {}).get("pickup_index", 0)
                        locations.append((region_name, area_name, node_name, pickup_index))
        
        return locations
    
    def get_dock_connections(self) -> List[Tuple[str, str, str, str, str, str, Any]]:
        """
        Get all dock (door/teleporter) connections between areas/regions
        Returns: List of (source_region, source_area, source_node, target_region, target_area, target_node, requirement) tuples
        """
        connections = []
        
        for region_name, region_data in self.regions.items():
            if "areas" not in region_data:
                continue
            
            for area_name, area_data in region_data["areas"].items():
                if "nodes" not in area_data:
                    continue
                
                for node_name, node_data in area_data["nodes"].items():
                    # Check if this is a dock node (door/teleporter)
                    if node_data.get("node_type") == "dock":
                        # Get default connection
                        default_conn = node_data.get("default_connection")
                        if default_conn:
                            target_region = default_conn.get("region", region_name)
                            target_area = default_conn["area"]
                            target_node = default_conn["node"]
                            
                            # Get door requirement (dock weakness)
                            dock_weakness = node_data.get("default_dock_weakness")
                            requirement = self._get_dock_weakness_requirement(dock_weakness)
                            
                            connections.append((
                                region_name, area_name, node_name,
                                target_region, target_area, target_node,
                                requirement
                            ))
        
        return connections
    
    def get_node_connections(self, region_name: str, area_name: str, node_name: str) -> List[Tuple[str, str, str, Any]]:
        """
        Get all connections FROM a specific node
        Returns: List of (target_region, target_area, target_node, requirement) tuples
        
        This handles both:
        1. Internal connections (to other nodes in same area)
        2. Dock connections (doors/tunnels to other areas via default_connection)
        """
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
        
        # Handle dock nodes specially
        if node_type == "dock":
            # Docks have a default_connection that specifies where they lead
            default_conn = node.get("default_connection")
            
            if default_conn:
                target_region = default_conn.get("region", region_name)
                target_area = default_conn.get("area")
                target_node = default_conn.get("node")
                
                # Prefer RDV open-requirement overrides (story locks, etc.)
                override = node.get("override_default_open_requirement")
                if override is not None:
                    requirement = override
                else:
                    dock_weakness = node.get("default_dock_weakness", "Power Beam Door")
                    requirement = self._get_dock_weakness_requirement(dock_weakness)
                
                connections.append((target_region, target_area, target_node, requirement))
        
        # Also add internal connections (to other nodes in same area)
        for target_node_name, requirement in node_connections.items():
            # Target is in the same area
            connections.append((region_name, area_name, target_node_name, requirement))
        
        return connections
    
    def get_starting_nodes(self) -> List[Tuple[str, str, str]]:
        """
        Get all valid starting locations (spawn points)
        Returns: List of (region, area, node) tuples
        """
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
        """Get the requirement for a dock weakness (door type)"""
        if not weakness_name or weakness_name == "Power Beam Door":
            # Power beam doors have no requirement (always accessible)
            return {"type": "trivial"}
        
        # Look up the door type in dock_weakness_database
        if "dock_weakness_database" not in self.header:
            return {"type": "impossible"}
        
        dock_db = self.header["dock_weakness_database"]
        
        # Search through door types
        if "types" in dock_db and "door" in dock_db["types"]:
            door_items = dock_db["types"]["door"].get("items", {})
            if weakness_name in door_items:
                door_data = door_items[weakness_name]
                # Return the lock requirement if it exists, otherwise the base requirement
                if "lock" in door_data and door_data["lock"]:
                    lock_req = door_data["lock"].get("requirement")
                    if lock_req:
                        return lock_req
                return door_data.get("requirement", {"type": "trivial"})
        
        # Check tunnel types
        if "types" in dock_db and "tunnel" in dock_db["types"]:
            tunnel_items = dock_db["types"]["tunnel"].get("items", {})
            if weakness_name in tunnel_items:
                tunnel_data = tunnel_items[weakness_name]
                return tunnel_data.get("requirement", {"type": "trivial"})
        
        # Unknown door type - assume trivial for now
        return {"type": "trivial"}
    
    def resolve_requirement(self, req: Any, context: str = "") -> Optional[str]:
        """
        Convert a Randovania requirement into an Archipelago rule lambda string
        Returns a Python expression that can be evaluated
        """
        if req is None:
            return "True"
        
        if isinstance(req, dict):
            req_type = req.get("type")
            
            # Trivial requirement (always true)
            if req_type == "trivial":
                return "True"
            
            # Impossible requirement (never true)
            if req_type == "impossible":
                return "False"
            
            # Resource requirement (need specific item/ability)
            if req_type == "resource":
                data = req.get("data", {})
                resource_type = data.get("type")
                resource_name = data.get("name")
                amount = data.get("amount", 1)
                negate = data.get("negate", False)
                
                # Map Randovania resource names to Archipelago item names
                ap_item = self._map_resource_to_ap_item(resource_type, resource_name)
                if not ap_item:
                    return None  # Unknown resource, skip
                
                if amount == 1:
                    result = f"state.has('{ap_item}', player)"
                else:
                    result = f"state.has('{ap_item}', player, {amount})"
                
                if negate:
                    result = f"not ({result})"
                
                return result
            
            # Template requirement (reference to a predefined template)
            if req_type == "template":
                template_name = req.get("data")
                if template_name in self.templates:
                    return self.resolve_requirement(self.templates[template_name], f"template:{template_name}")
                return None  # Unknown template
            
            # AND requirement (all sub-requirements must be true)
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
            
            # OR requirement (any sub-requirement can be true)
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
        """
        Map Randovania resource names to Archipelago item names
        Comprehensive mapping of all items, events, and tricks
        """
        if resource_type == "items":
            # Direct item mapping from Randovania short names to AP names
            item_mapping = {
                # Beams
                "Power": None,
                "Wide": "Wide Beam",
                "Plasma": "Plasma Beam",
                "Wave": "Wave Beam",
                "Hyper": None,
                "Charge": "Charge Beam",
                "Diffusion": "Diffusion Beam",
                "Grapple": "Grapple Beam",
                # Missiles
                "MissileLauncher": None,
                "Supers": "Super Missile",
                "Ice": "Ice Missile",
                "Storm": "Storm Missile",
                "MissileAmmo": "__missile_ammo__",
                # Aeion
                "Cloak": "Phantom Cloak",
                "Flash": "Flash Shift",
                "Pulse": "Pulse Radar",
                # Morph / bombs
                "Morph": "Morph Ball",
                "Bomb": "Bomb",
                "Cross": "Cross Bomb",
                "MainPB": "Power Bomb",
                "PBAmmo": "Power Bomb",
                # Movement
                "Magnet": "Spider Magnet",
                "Speed": "Speed Booster",
                "Spin": "Spin Boost",
                "Space": "Space Jump",
                "Screw": "Screw Attack",
                "Slide": None,
                # Suits
                "PowerSuit": None,
                "Varia": "Varia Suit",
                "Gravity": "Gravity Suit",
                "HyperSuit": None,
                # Tanks
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
            
            # Check for progressive items
            # If using progressive options, we need to map to progressive names
            # For now, return the individual items
            return None
        
        elif resource_type == "events":
            # Map to AP event item names (see Events.py / dread_logic.py)
            try:
                from .Events import EVENT_RESOURCE_TO_ITEM
                return EVENT_RESOURCE_TO_ITEM.get(resource_name)
            except ImportError:
                return f"Event - {resource_name}"

        elif resource_type == "tricks":
            # Evaluated via options in dread_logic (not inventory items)
            return None

        elif resource_type == "damage":
            # Evaluated via suits / Suitless trick in dread_logic
            return None

        return None


def main():
    """Test the parser"""
    logic_path = Path(__file__).parent / "logic_database"
    parser = RandovaniaLogicParser(logic_path)
    parser.load_database()
    
    # Get all pickup locations
    locations = parser.get_pickup_locations()
    print(f"\n[OK] Found {len(locations)} pickup locations")
    
    # Show a few examples
    print("\nExample locations:")
    for i, (region, area, node, idx) in enumerate(locations[:5]):
        print(f"  {region} - {area} - {node} (pickup #{idx})")
    
    # Get all dock connections
    connections = parser.get_dock_connections()
    print(f"\n[OK] Found {len(connections)} dock connections (doors/teleporters)")
    
    # Show a few examples
    print("\nExample connections:")
    for i, (sr, sa, sn, tr, ta, tn, req) in enumerate(connections[:5]):
        print(f"  {sr}/{sa}/{sn} -> {tr}/{ta}/{tn}")


if __name__ == "__main__":
    main()

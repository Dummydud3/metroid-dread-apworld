"""Door-lock randomizer for Metroid Dread (working-simple).

Enumerates physical doors from logic_database dock nodes, rolls BASIC lock
types with a start-frontier guard, mutates default_dock_weakness in-memory,
and emits open-dread-rando door_patches.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

NodeId = Tuple[str, str, str]

REGION_TO_SCENARIO: Dict[str, str] = {
    "Artaria": "s010_cave",
    "Cataris": "s020_magma",
    "Dairon": "s030_baselab",
    "Burenia": "s040_aqua",
    "Ghavoran": "s050_forest",
    "Elun": "s060_quarantine",
    "Ferenia": "s070_basesanc",
    "Hanubia": "s080_shipyard",
    "Itorash": "s090_skybase",
}

BASIC_DOOR_TYPES = frozenset({
    "power_beam", "charge_beam", "grapple_beam",
    "wide_beam", "wave_beam", "plasma_beam", "missile", "super_missile",
})

SHIELDED_DOOR_TYPES = frozenset({
    "wide_beam", "plasma_beam", "wave_beam", "missile", "super_missile",
})

SHIELD_IDS_PER_SCENARIO = 100
SHIELD_BUDGET_MARGIN = 10

WEAKNESS_DOOR_TYPE: Dict[str, str] = {
    "Access Open": "frame",
    "Access Permanently Closed": "closed",
    "Power Beam Door": "power_beam",
    "Charge Beam Door": "charge_beam",
    "Wide Beam Door": "wide_beam",
    "Plasma Beam Door": "plasma_beam",
    "Wave Beam Door": "wave_beam",
    "Missile Door": "missile",
    "Super Missile Door": "super_missile",
    "Sensor Lock Door": "phantom_cloak",
    "Grapple Beam Door": "grapple_beam",
    "Phase Shift Door": "phase_shift",
    "Ice Missile Door": "ice_missile",
    "Diffusion Beam Door": "diffusion_beam",
    "Storm Missile Door": "storm_missile",
    "Bomb Door": "bomb",
    "Cross Bomb Door": "cross_bomb",
    "Power Bomb Door": "power_bomb",
}

ALL_DOOR_WEAKNESS_NAMES = frozenset(WEAKNESS_DOOR_TYPE)

DEFAULT_DOORS_TO_CHANGE = frozenset({
    "Access Open", "Charge Beam Door", "Grapple Beam Door", "Missile Door",
    "Plasma Beam Door", "Power Beam Door", "Sensor Lock Door",
    "Super Missile Door", "Wave Beam Door", "Wide Beam Door",
})

DEFAULT_CHANGE_DOORS_TO = frozenset(
    name for name, dt in WEAKNESS_DOOR_TYPE.items() if dt in BASIC_DOOR_TYPES
)

# Assignments: physical_key -> weakness name
PhysicalKey = Tuple[str, str]  # (scenario, actor)


def _iter_door_docks(parser) -> Iterable[Tuple[NodeId, dict]]:
    for region_name, region in parser.regions.items():
        for area_name, area in (region.get("areas") or {}).items():
            for node_name, node in (area.get("nodes") or {}).items():
                if node.get("node_type") != "dock":
                    continue
                if node.get("dock_type") != "door":
                    continue
                yield (region_name, area_name, node_name), node


def physical_key_for_node(region: str, node: dict) -> Optional[PhysicalKey]:
    actor = (node.get("extra") or {}).get("actor_name")
    if not actor:
        return None
    # open-dread-rando door_patches need Mercury actor instance names
    # (doorpowerpower_000). Logic DB also has symbolic labels like
    # "Door006 (CG-CG)" — skip those until we have an actor map.
    if not str(actor).startswith("door"):
        return None
    scenario = REGION_TO_SCENARIO.get(region)
    if not scenario:
        return None
    return (scenario, actor)


def collect_physical_doors(parser) -> Dict[PhysicalKey, List[Tuple[NodeId, dict]]]:
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]] = defaultdict(list)
    for node_id, node in _iter_door_docks(parser):
        if node.get("exclude_from_dock_rando"):
            continue
        key = physical_key_for_node(node_id[0], node)
        if key is None:
            continue
        groups[key].append((node_id, node))
    return groups


def start_frontier_keys(logic, start_inventory) -> Set[PhysicalKey]:
    """Doors the starting kit can already traverse (keep vanilla for fill)."""
    reachable = logic.get_reachable_nodes(start_inventory)
    protected: Set[PhysicalKey] = set()
    parser = logic.parser
    for node_id in reachable:
        region, area, name = node_id
        try:
            node = parser.regions[region]["areas"][area]["nodes"][name]
        except KeyError:
            continue
        if node.get("node_type") != "dock" or node.get("dock_type") != "door":
            continue
        weakness = node.get("default_dock_weakness") or "Power Beam Door"
        req = parser._get_dock_weakness_requirement(weakness)
        if not logic.evaluate_requirement(req, start_inventory):
            continue
        conn = node.get("default_connection") or {}
        dest = (
            conn.get("region", region),
            conn.get("area"),
            conn.get("node"),
        )
        if dest[1] is None or dest[2] is None:
            continue
        if dest not in reachable:
            continue
        key = physical_key_for_node(region, node)
        if key:
            protected.add(key)
    return protected


def roll_assignments(
    logic,
    rng,
    *,
    doors_to_change: Iterable[str],
    change_doors_to: Iterable[str],
    mode: str = "individual_doors",
) -> Dict[PhysicalKey, str]:
    """Return { (scenario, actor): weakness_name }. Empty when vanilla."""
    if mode in ("vanilla", "off", None) or mode == 0:
        return {}

    change_from = set(doors_to_change) & ALL_DOOR_WEAKNESS_NAMES
    change_to = [
        w for w in change_doors_to
        if w in ALL_DOOR_WEAKNESS_NAMES and WEAKNESS_DOOR_TYPE.get(w) in BASIC_DOOR_TYPES
    ]
    if not change_from or not change_to:
        return {}

    groups = collect_physical_doors(logic.parser)
    start_inv = logic.inventory_from_counts({})
    protected = start_frontier_keys(logic, start_inv)

    # Per-scenario shield budget (each shielded door costs 2 ids).
    shield_used: Dict[str, int] = defaultdict(int)
    for key, sides in groups.items():
        scenario, _ = key
        weakness = sides[0][1].get("default_dock_weakness") or "Power Beam Door"
        dt = WEAKNESS_DOOR_TYPE.get(weakness)
        if dt in SHIELDED_DOOR_TYPES:
            shield_used[scenario] += 2

    assignments: Dict[PhysicalKey, str] = {}
    eligible_keys = []
    for key, sides in groups.items():
        if key in protected:
            continue
        vanilla = sides[0][1].get("default_dock_weakness") or "Power Beam Door"
        if vanilla not in change_from:
            continue
        eligible_keys.append(key)

    rng.shuffle(eligible_keys)
    for key in eligible_keys:
        scenario, _ = key
        pool = list(change_to)
        rng.shuffle(pool)
        chosen = None
        for weakness in pool:
            dt = WEAKNESS_DOOR_TYPE[weakness]
            cost = 2 if dt in SHIELDED_DOOR_TYPES else 0
            if cost and shield_used[scenario] + cost > SHIELD_IDS_PER_SCENARIO - SHIELD_BUDGET_MARGIN:
                continue
            chosen = weakness
            shield_used[scenario] += cost
            break
        if chosen is None:
            continue
        assignments[key] = chosen

    return assignments


def apply_assignments(parser, assignments: Dict[PhysicalKey, str]) -> None:
    """Mutate dock default_dock_weakness in the loaded logic graph."""
    if not assignments:
        return
    for node_id, node in _iter_door_docks(parser):
        key = physical_key_for_node(node_id[0], node)
        if key is None or key not in assignments:
            continue
        node["default_dock_weakness"] = assignments[key]


def assignments_to_door_patches(assignments: Dict[PhysicalKey, str]) -> List[dict]:
    patches = []
    for (scenario, actor), weakness in sorted(assignments.items()):
        door_type = WEAKNESS_DOOR_TYPE.get(weakness)
        if not door_type:
            continue
        patches.append({
            "actor": {"scenario": scenario, "actor": actor},
            "door_type": door_type,
        })
    return patches

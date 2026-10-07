"""Door-lock randomizer for Metroid Bread."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple  # Use Any for slot-data helpers.

from worlds.metroid_bread.logic import door_rando_db as _door_db

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

BASIC_DOOR_TYPES = _door_db.BASIC_ODR_DOOR_TYPES

# Never place Presence doors; ODR cannot add them.
ODR_CANNOT_ADD_DOOR_TYPES = _door_db.ODR_CANNOT_ADD_DOOR_TYPES

# Each shielded door needs two shield IDs in its scenario.
SHIELDED_DOOR_TYPES = frozenset({
    "wide_beam",
    "plasma_beam",
    "wave_beam",
    "missile",
    "super_missile",
    "ice_missile",
    "storm_missile",
    "diffusion_beam",
    "bomb",
    "cross_bomb",
    "power_bomb",
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

# Sensors may be replaced, but must not be placed as new doors.
DEFAULT_DOORS_TO_CHANGE = _door_db.header_change_from()

# Allowed new door types exclude Sensor, Phase, and Closed.
DEFAULT_CHANGE_DOORS_TO = _door_db.basic_change_to_weaknesses()

# Map each physical door key to its new weakness.
PhysicalKey = Tuple[str, str]  # Identify a door by scenario and actor.


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
    """Return (scenario, actor) only for ODR-patchable Mercury door actors."""
    if not _door_db.is_patchable_door_source_node(node):
        return None
    actor = (node.get("extra") or {}).get("actor_name")
    scenario = REGION_TO_SCENARIO.get(region)
    if not scenario or not actor:
        return None
    return (scenario, str(actor))


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


def incompatible_weaknesses_for_key(
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
    key: PhysicalKey,
) -> Set[str]:
    """Union of ``incompatible_dock_weaknesses`` on both sides of a physical door."""
    bans: Set[str] = set()
    for _nid, node in groups.get(key) or ():
        bans.update(node.get("incompatible_dock_weaknesses") or [])
    return bans


def roll_assignments(
    logic,
    rng,
    *,
    doors_to_change: Iterable[str],
    change_doors_to: Iterable[str],
    mode: str = "individual_doors",
    start_counts: Optional[Dict[str, int]] = None,
) -> Dict[PhysicalKey, str]:
    """Pre-fill unlock assignments for Individual Doors (locks assigned post-fill)."""
    if mode in ("vanilla", "off", None) or mode == 0:
        return {}

    from worlds.metroid_bread.logic import DoorRandoAssigner

    result = DoorRandoAssigner.pre_fill_roll(
        logic,
        rng,
        doors_to_change=doors_to_change,
        change_doors_to=change_doors_to,
        start_counts=start_counts,
    )
    return dict(result.assignments)


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
    """Serialize assignments to ODR ``door_patches``, dropping non-patchable actors."""
    patches = []
    for (scenario, actor), weakness in sorted(assignments.items()):
        if not _door_db.is_odr_patchable_door_actor(str(actor)):
            continue
        door_type = WEAKNESS_DOOR_TYPE.get(weakness)
        if not door_type or door_type in ODR_CANNOT_ADD_DOOR_TYPES:
            continue
        patches.append({
            "actor": {"scenario": scenario, "actor": actor},
            "door_type": door_type,
        })
    return patches


DOOR_TYPE_TO_WEAKNESS: Dict[str, str] = {
    door_type: weakness
    for weakness, door_type in WEAKNESS_DOOR_TYPE.items()
    if door_type not in ("frame", "closed")
}


def assignments_from_slot_data(entries: Any) -> Dict[PhysicalKey, str]:
    """Deserialize door_assignments from patch_extras / slot_data."""
    out: Dict[PhysicalKey, str] = {}
    if not entries:
        return out
    if isinstance(entries, dict):
        # Accept a flat door-to-lock map or nested settings.
        for key, weakness in entries.items():
            if isinstance(key, str) and "/" in key and isinstance(weakness, str):
                scenario, actor = key.split("/", 1)
                out[(scenario, actor)] = weakness
        return out
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            scenario = entry.get("scenario")
            actor = entry.get("actor")
            weakness = entry.get("weakness")
            if not weakness and entry.get("door_type"):
                weakness = DOOR_TYPE_TO_WEAKNESS.get(str(entry["door_type"]))
            if scenario and actor and weakness:
                out[(str(scenario), str(actor))] = str(weakness)
    return out


def apply_assignments_from_slot_data(parser, entries: Any) -> int:
    """Apply serialized door assignments onto a fresh parser. Returns count."""
    assignments = assignments_from_slot_data(entries)
    if not assignments:
        # Also accept ODR's door_patches format.
        if isinstance(entries, list):
            patched = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                actor = entry.get("actor")
                if isinstance(actor, dict) and entry.get("door_type"):
                    patched.append(
                        {
                            "scenario": actor.get("scenario"),
                            "actor": actor.get("actor"),
                            "door_type": entry.get("door_type"),
                        }
                    )
            assignments = assignments_from_slot_data(patched)
    if not assignments:
        return 0
    apply_assignments(parser, assignments)
    return len(assignments)


# Use this easy lock to open enough checks near the start.
SOFT_WEAKNESS = "Power Beam Door"
# Leave doors already this easy unchanged.
_ALREADY_SOFT = frozenset({"Power Beam Door", "Access Open"})


def _pickup_count_in_nodes(
    pickup_nodes: Dict[str, NodeId],
    active: Set[str],
    reachable: Set[NodeId],
) -> int:
    return sum(
        1
        for name, node in pickup_nodes.items()
        if name in active and node in reachable
    )


def score_doors_by_new_checks(
    logic,
    assignments: Dict[PhysicalKey, str],
    *,
    pickup_nodes: Dict[str, NodeId],
    active_names: Set[str],
    inventory_counts: Dict[str, int],
    goal_node: NodeId,
    protected: Optional[Set[PhysicalKey]] = None,
    max_candidates: int = 48,
) -> List[Tuple[int, PhysicalKey]]:
    """Score assigned doors by how many extra active pickups become reachable"""
    if not assignments:
        return []

    protected = protected or set()
    inv = logic.inventory_from_counts(dict(inventory_counts))
    baseline_nodes = logic.get_reachable_nodes(inv)
    baseline_pickups = _pickup_count_in_nodes(pickup_nodes, active_names, baseline_nodes)
    baseline_goal = goal_node in baseline_nodes

    candidates = [
        key for key, weakness in assignments.items()
        if key not in protected and weakness not in _ALREADY_SOFT
    ]
    # Limit the doors scored so generation stays responsive.
    if len(candidates) > max_candidates:
        # Use actor-name hashes to choose a repeatable spread of doors.
        candidates = sorted(candidates, key=lambda k: k[1])[:max_candidates]

    scored: List[Tuple[int, PhysicalKey]] = []
    parser = logic.parser
    for key in candidates:
        apply_assignments(parser, {key: SOFT_WEAKNESS})
        logic.rebuild_graph()
        nodes = logic.get_reachable_nodes(inv)
        pickups = _pickup_count_in_nodes(pickup_nodes, active_names, nodes)
        goal = goal_node in nodes
        delta = pickups - baseline_pickups
        score = delta
        if goal and not baseline_goal:
            score += 1000
        scored.append((score, key))
        # Restore the original lock before testing the next door.
        apply_assignments(parser, {key: assignments[key]})
        logic.rebuild_graph()

    scored.sort(key=lambda pair: (-pair[0], pair[1][0], pair[1][1]))
    return scored


def soften_assignments(
    assignments: Dict[PhysicalKey, str],
    keys: Iterable[PhysicalKey],
    soft_weakness: str = SOFT_WEAKNESS,
) -> List[PhysicalKey]:
    """Set the given doors to an easy weakness. Returns keys actually changed."""
    changed: List[PhysicalKey] = []
    for key in keys:
        if key not in assignments:
            continue
        if assignments[key] == soft_weakness:
            continue
        assignments[key] = soft_weakness
        changed.append(key)
    return changed


def pick_doors_to_soften(
    scored: List[Tuple[int, PhysicalKey]],
    *,
    top_k: int = 6,
    assignments: Optional[Dict[PhysicalKey, str]] = None,
) -> List[PhysicalKey]:
    """Choose top-K doors to soften for fill repair."""
    if not scored or top_k <= 0:
        return []
    from worlds.metroid_bread.logic.DoorRandoAssigner import LOCK_TIER

    def sort_key(pair: Tuple[int, PhysicalKey]) -> Tuple[int, int, str, str]:
        score, key = pair
        weakness = (assignments or {}).get(key, "")
        tier = LOCK_TIER.get(weakness, 3)
        return (-score, tier, key[0], key[1])

    positive = [(score, key) for score, key in scored if score > 0]
    ordered = sorted(positive if positive else scored, key=sort_key)
    return [key for _score, key in ordered[:top_k]]

"""Door-lock randomizer for Metroid Dread (working-simple).

Enumerates physical doors from logic_database dock nodes, rolls BASIC lock
types with a start-frontier guard, mutates default_dock_weakness in-memory,
and emits open-dread-rando door_patches.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple  # Any used by slot_data helpers

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
    start_counts: Optional[Dict[str, int]] = None,
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
    # Include any guaranteed starting items, otherwise the frontier we keep
    # vanilla is smaller than what the player actually opens with.
    start_inv = logic.inventory_from_counts(dict(start_counts or {}))
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
        # {"s010_cave/door…": "Plasma Beam Door"} or nested
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
        # Fall back to ODR door_patches shape if present.
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


# Easy lock used when density-softening doors to rescue fill / start reachability.
SOFT_WEAKNESS = "Power Beam Door"
# Doors already this open do not need softening.
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
    """
    Score assigned doors by how many extra active pickups become reachable
    (and whether the goal opens) if the door is softened to Power Beam.

    Returns (score, key) pairs sorted best-first. Score is
    ``1000`` if softening newly reaches the goal, else the pickup delta.
    """
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
    # Prefer evaluating a bounded set so generate_early stays responsive.
    if len(candidates) > max_candidates:
        # Deterministic trim: keep a spread by hashing actor name.
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
        # Restore this door to its rolled weakness before the next trial.
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
) -> List[PhysicalKey]:
    """Choose top-K doors; prefer positive scores, else still take top-K."""
    if not scored or top_k <= 0:
        return []
    positive = [key for score, key in scored if score > 0]
    if positive:
        return positive[:top_k]
    return [key for _score, key in scored[:top_k]]

"""Light RDV-style Individual Doors assigner for Metroid Bread.

Pre-fill: unlock ~``to_shuffle_proportion`` of eligible docks (Power Beam).
Item fill proceeds on the opened graph.
Post-fill: for each shuffled door, treat it as blocked, grow reach inventory
(same family as soften / start-frontier BFS), and only assign lock types that
inventory can open — honoring ``incompatible_dock_weaknesses`` and the basic
beam/missile/grapple pool.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from BaseClasses import CollectionState

from . import DoorRando
from . import door_rando_db as db

PhysicalKey = DoorRando.PhysicalKey
NodeId = DoorRando.NodeId

UNLOCKED = "Power Beam Door"


def incompatible_weaknesses_for_key(
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
    key: PhysicalKey,
) -> Set[str]:
    bans: Set[str] = set()
    for _nid, node in groups.get(key) or ():
        bans.update(node.get("incompatible_dock_weaknesses") or [])
    return bans


def eligible_physical_keys(
    logic,
    *,
    doors_to_change: Iterable[str],
    start_counts: Optional[Dict[str, int]] = None,
) -> List[PhysicalKey]:
    """Physical doors eligible for Individual Doors shuffle (pre-fill)."""
    change_from = set(doors_to_change) & DoorRando.ALL_DOOR_WEAKNESS_NAMES
    if not change_from:
        change_from = set(db.header_change_from())
    groups = DoorRando.collect_physical_doors(logic.parser)
    start_inv = logic.inventory_from_counts(dict(start_counts or {}))
    protected = DoorRando.start_frontier_keys(logic, start_inv)

    eligible: List[PhysicalKey] = []
    for key, sides in groups.items():
        if key in protected:
            continue
        vanilla = sides[0][1].get("default_dock_weakness") or UNLOCKED
        if vanilla not in change_from:
            continue
        eligible.append(key)
    return eligible


def select_shuffled_keys(
    eligible: List[PhysicalKey],
    rng,
    *,
    proportion: Optional[float] = None,
) -> List[PhysicalKey]:
    """Pick ~proportion of eligible docks (RDV ``to_shuffle_proportion``)."""
    if not eligible:
        return []
    prop = db.to_shuffle_proportion() if proportion is None else float(proportion)
    prop = max(0.0, min(1.0, prop))
    keys = list(eligible)
    rng.shuffle(keys)
    n = int(len(keys) * prop)
    if prop > 0.0 and len(keys) > 0 and n < 1:
        n = 1
    return keys[:n]


def pre_fill_unlock_assignments(
    shuffled_keys: Iterable[PhysicalKey],
) -> Dict[PhysicalKey, str]:
    """Force shuffled docks to unlocked before item fill."""
    unlocked = db.unlocked_weakness()
    return {key: unlocked for key in shuffled_keys}


def _target_pool(change_doors_to: Iterable[str]) -> List[str]:
    requested = set(change_doors_to) & DoorRando.ALL_DOOR_WEAKNESS_NAMES
    if not requested:
        requested = set(db.basic_change_to_weaknesses())
    basic = db.basic_change_to_weaknesses()
    pool = [
        w for w in requested
        if w in basic
        and DoorRando.WEAKNESS_DOOR_TYPE.get(w) not in db.ODR_CANNOT_ADD_DOOR_TYPES
    ]
    unlocked = db.unlocked_weakness()
    if unlocked not in pool and unlocked in DoorRando.ALL_DOOR_WEAKNESS_NAMES:
        pool.append(unlocked)
    return pool


def _shield_budget_ok(
    weakness: str,
    scenario: str,
    shield_used: Dict[str, int],
) -> bool:
    dt = DoorRando.WEAKNESS_DOOR_TYPE.get(weakness)
    cost = 2 if dt in DoorRando.SHIELDED_DOOR_TYPES else 0
    if not cost:
        return True
    return (
        shield_used[scenario] + cost
        <= DoorRando.SHIELD_IDS_PER_SCENARIO - DoorRando.SHIELD_BUDGET_MARGIN
    )


def filter_targets_for_door(
    pool: Iterable[str],
    *,
    key: PhysicalKey,
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
    inventory: FrozenSet[str],
    logic,
    shield_used: Dict[str, int],
) -> List[str]:
    """Reach + incompat + shield filter (unlocked always kept when present)."""
    scenario, _ = key
    bans = incompatible_weaknesses_for_key(groups, key)
    unlocked = db.unlocked_weakness()
    allowed: List[str] = []
    for weakness in pool:
        if weakness in bans:
            continue
        dt = DoorRando.WEAKNESS_DOOR_TYPE.get(weakness)
        if not dt or dt in db.ODR_CANNOT_ADD_DOOR_TYPES:
            continue
        if not _shield_budget_ok(weakness, scenario, shield_used):
            continue
        if weakness == unlocked:
            allowed.append(weakness)
            continue
        req = logic.parser._get_dock_weakness_requirement(weakness)
        if logic.evaluate_requirement(req, inventory):
            allowed.append(weakness)
    if unlocked in pool and unlocked not in allowed and unlocked not in bans:
        if _shield_budget_ok(unlocked, scenario, shield_used):
            allowed.append(unlocked)
    if not allowed:
        allowed = [unlocked]
    return allowed


def inventory_reaching_blocked_door(
    world,
    key: PhysicalKey,
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
) -> FrozenSet[str]:
    """
    Grow collection (sphere-style) while the door is permanently closed.

    Returns the logic inventory when any side of the physical door becomes
    reachable. Falls back to start-kit inventory if the door never opens in.
    """
    logic = world.logic
    parser = logic.parser
    sides = groups.get(key) or []
    node_ids = [nid for nid, _ in sides]
    if not node_ids:
        return logic.inventory_from_counts({})

    blocked = db.locked_weakness()
    previous = {
        key: (sides[0][1].get("default_dock_weakness") or UNLOCKED)
    }
    DoorRando.apply_assignments(parser, {key: blocked})
    logic.rebuild_graph()

    state = CollectionState(world.multiworld)
    remaining = {
        loc for loc in world.multiworld.get_filled_locations()
        if loc.player == world.player
    }
    result = None
    for _ in range(len(remaining) + 8):
        inv = logic.inventory_from_state(state)
        reachable = logic.get_reachable_nodes(inv)
        if any(nid in reachable for nid in node_ids):
            result = inv
            break
        sphere = [loc for loc in remaining if loc.can_reach(state)]
        if not sphere:
            break
        for loc in sphere:
            if loc.item:
                state.collect(loc.item, True, loc)
            remaining.discard(loc)

    DoorRando.apply_assignments(parser, previous)
    logic.rebuild_graph()

    if result is not None:
        return result
    from . import StartKit
    return logic.inventory_from_counts(StartKit.kit_counts(world.start_kit or []))


def post_fill_assign(
    world,
    shuffled_keys: Iterable[PhysicalKey],
    rng,
    *,
    change_doors_to: Iterable[str],
) -> Dict[PhysicalKey, str]:
    """Assign reach-gated locks to pre-unlocked shuffled docks after item fill."""
    keys = list(shuffled_keys)
    if not keys:
        return {}

    logic = world.logic
    groups = DoorRando.collect_physical_doors(logic.parser)
    pool = _target_pool(change_doors_to)

    shield_used = defaultdict(int)
    shuffled_set = set(keys)
    for key, sides in groups.items():
        if key in shuffled_set:
            continue
        weakness = sides[0][1].get("default_dock_weakness") or UNLOCKED
        dt = DoorRando.WEAKNESS_DOOR_TYPE.get(weakness)
        if dt in DoorRando.SHIELDED_DOOR_TYPES:
            shield_used[key[0]] += 2

    assignments = {}
    for key in keys:
        if key not in groups:
            continue
        inv = inventory_reaching_blocked_door(world, key, groups)
        candidates = filter_targets_for_door(
            pool,
            key=key,
            groups=groups,
            inventory=inv,
            logic=logic,
            shield_used=shield_used,
        )
        chosen = rng.choice(candidates)
        assignments[key] = chosen
        dt = DoorRando.WEAKNESS_DOOR_TYPE.get(chosen)
        if dt in DoorRando.SHIELDED_DOOR_TYPES:
            shield_used[key[0]] += 2
        DoorRando.apply_assignments(logic.parser, {key: chosen})
        logic.rebuild_graph()

    return assignments


def pre_fill_roll(
    logic,
    rng,
    *,
    doors_to_change: Iterable[str],
    change_doors_to: Iterable[str],
    start_counts: Optional[Dict[str, int]] = None,
    proportion: Optional[float] = None,
) -> Tuple[Dict[PhysicalKey, str], List[PhysicalKey]]:
    """
    Select shuffled docks and return unlocked assignments + key list.

    ``change_doors_to`` is accepted for API symmetry; targets are applied in
    ``post_fill_assign``.
    """
    del change_doors_to  # applied post-fill
    eligible = eligible_physical_keys(
        logic, doors_to_change=doors_to_change, start_counts=start_counts
    )
    shuffled = select_shuffled_keys(eligible, rng, proportion=proportion)
    return pre_fill_unlock_assignments(shuffled), shuffled

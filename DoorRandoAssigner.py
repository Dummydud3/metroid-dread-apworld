"""Individual Doors assigner for Metroid Bread (RDV-aligned dual mandate).

Philosophy
----------
Doors are progression infrastructure, not cosmetics. Door lock rando must:

1. **Reroute** — Change how ZDR is traversed vs vanilla (meaningful locks on
   real docks; vanilla door identities are not sacred).
2. **Assist fill** — Deliberately open the graph where assumed fill is starved
   (sphere-0 / early expansion), instead of only unlocking at random then
   soft-failing back to Power Beam.

Pipeline (AP-practical two-phase, RDV Individual Doors timing):

- Classify eligible docks: protected / fill_assist / reroute.
- Pre-fill: force-unlock fill_assist + unlock the reroute set for assumed fill.
- Item fill on the opened graph.
- Post-fill: paint *interesting* reach-gated locks on the reroute set only
  (Power Beam is not a normal random outcome).
- Soften remains emergency-only for fill / preflight repair.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Set, Tuple

from BaseClasses import CollectionState

from . import DoorRando
from . import door_rando_db as db

PhysicalKey = DoorRando.PhysicalKey
NodeId = DoorRando.NodeId

UNLOCKED = "Power Beam Door"
OPEN_WEAKNESSES = frozenset({"Power Beam Door", "Access Open"})

# Prefer harder locks when several candidates remain reachable.
LOCK_TIER: Dict[str, int] = {
    "Missile Door": 1,
    "Bomb Door": 1,
    "Charge Beam Door": 2,
    "Super Missile Door": 3,
    "Ice Missile Door": 3,
    "Wide Beam Door": 4,
    "Plasma Beam Door": 4,
    "Cross Bomb Door": 4,
    "Diffusion Beam Door": 4,
    "Wave Beam Door": 5,
    "Grapple Beam Door": 5,
    "Power Bomb Door": 5,
    "Storm Missile Door": 5,
}

# Cap how many high-delta docks we force-open to help assumed fill.
FILL_ASSIST_CAP = 10

# Score at least this many new active pickups to qualify as fill_assist.
FILL_ASSIST_MIN_DELTA = 1


class PreFillResult(NamedTuple):
    """Pre-fill unlock map plus the three dock classes for gen / probe / soften."""

    assignments: Dict[PhysicalKey, str]
    reroute_keys: List[PhysicalKey]
    fill_assist_keys: List[PhysicalKey]
    protected_keys: List[PhysicalKey]


def incompatible_weaknesses_for_key(
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
    key: PhysicalKey,
) -> Set[str]:
    bans: Set[str] = set()
    for _nid, node in groups.get(key) or ():
        bans.update(node.get("incompatible_dock_weaknesses") or [])
    return bans


def protected_physical_keys(
    logic,
    *,
    start_counts: Optional[Dict[str, int]] = None,
) -> Set[PhysicalKey]:
    """Start-frontier docks — never shuffle (sphere-0 safety)."""
    start_inv = logic.inventory_from_counts(dict(start_counts or {}))
    return DoorRando.start_frontier_keys(logic, start_inv)


def eligible_physical_keys(
    logic,
    *,
    doors_to_change: Iterable[str],
    start_counts: Optional[Dict[str, int]] = None,
    protected: Optional[Set[PhysicalKey]] = None,
) -> List[PhysicalKey]:
    """Physical doors eligible for Individual Doors (excludes protected)."""
    change_from = set(doors_to_change) & DoorRando.ALL_DOOR_WEAKNESS_NAMES
    if not change_from:
        change_from = set(db.header_change_from())
    groups = DoorRando.collect_physical_doors(logic.parser)
    if protected is None:
        protected = protected_physical_keys(logic, start_counts=start_counts)

    eligible: List[PhysicalKey] = []
    for key, sides in groups.items():
        if key in protected:
            continue
        vanilla = sides[0][1].get("default_dock_weakness") or UNLOCKED
        if vanilla not in change_from:
            continue
        eligible.append(key)
    return eligible


def _pickup_count(logic, inventory: FrozenSet[str], active: Optional[Set[str]] = None) -> int:
    nodes = logic.get_reachable_nodes(inventory)
    if active is None:
        return sum(1 for _name, node in logic.pickup_nodes.items() if node in nodes)
    return sum(
        1
        for name, node in logic.pickup_nodes.items()
        if node in nodes and name in active
    )


def score_unlock_delta(
    logic,
    key: PhysicalKey,
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
    *,
    start_counts: Dict[str, int],
    active: Optional[Set[str]] = None,
    reachable: Optional[Set[NodeId]] = None,
    inventory: Optional[FrozenSet[str]] = None,
    baseline_pickups: Optional[int] = None,
) -> int:
    """Extra active pickups reachable if ``key`` is forced to Power Beam.

    Only scores docks already on the start-kit frontier (at least one side
    reachable). Unlocking a distant dock cannot help assumed fill yet.
    Leaves the graph restored to the prior weakness.
    """
    sides = groups.get(key) or []
    if not sides:
        return 0
    previous = sides[0][1].get("default_dock_weakness") or UNLOCKED
    if previous in OPEN_WEAKNESSES:
        return 0

    inv = inventory if inventory is not None else logic.inventory_from_counts(dict(start_counts))
    if reachable is None:
        reachable = logic.get_reachable_nodes(inv)
    if not any(nid in reachable for nid, _node in sides):
        return 0

    baseline = (
        baseline_pickups
        if baseline_pickups is not None
        else _pickup_count(logic, inv, active)
    )

    unlocked = db.unlocked_weakness()
    DoorRando.apply_assignments(logic.parser, {key: unlocked})
    logic.rebuild_graph()
    try:
        after = _pickup_count(logic, inv, active)
    finally:
        DoorRando.apply_assignments(logic.parser, {key: previous})
        logic.rebuild_graph()
    return max(0, after - baseline)


def _pick_best_assist_key(
    logic,
    eligible: List[PhysicalKey],
    groups: Dict[PhysicalKey, List[Tuple[NodeId, dict]]],
    *,
    start_counts: Dict[str, int],
    taken: Set[PhysicalKey],
    active: Optional[Set[str]] = None,
) -> Optional[Tuple[int, PhysicalKey]]:
    """Best remaining frontier locked dock by pickup unlock-delta."""
    inv = logic.inventory_from_counts(dict(start_counts))
    reachable = logic.get_reachable_nodes(inv)
    baseline = _pickup_count(logic, inv, active)
    best: Optional[Tuple[int, PhysicalKey]] = None
    for key in eligible:
        if key in taken:
            continue
        delta = score_unlock_delta(
            logic,
            key,
            groups,
            start_counts=start_counts,
            active=active,
            reachable=reachable,
            inventory=inv,
            baseline_pickups=baseline,
        )
        if delta < FILL_ASSIST_MIN_DELTA:
            continue
        if best is None or delta > best[0] or (
            delta == best[0] and key < best[1]
        ):
            best = (delta, key)
    return best


def classify_docks(
    logic,
    rng,
    *,
    doors_to_change: Iterable[str],
    start_counts: Optional[Dict[str, int]] = None,
    assist_cap: int = FILL_ASSIST_CAP,
    reroute_proportion: Optional[float] = None,
    active: Optional[Set[str]] = None,
) -> Tuple[Set[PhysicalKey], List[PhysicalKey], List[PhysicalKey]]:
    """
    Return (protected, fill_assist_keys, reroute_keys).

    fill_assist: greedy cascade of highest unlock-delta frontier docks
    (force-open for fill). Each unlock can expose new frontier candidates.
    reroute: high proportion of the remainder (get interesting post-fill locks).
    """
    counts = dict(start_counts or {})
    protected = protected_physical_keys(logic, start_counts=counts)
    eligible = eligible_physical_keys(
        logic,
        doors_to_change=doors_to_change,
        start_counts=counts,
        protected=protected,
    )
    groups = DoorRando.collect_physical_doors(logic.parser)

    assist: List[PhysicalKey] = []
    assist_set: Set[PhysicalKey] = set()
    assist_vanilla: Dict[PhysicalKey, str] = {}
    cap = max(0, int(assist_cap))
    unlocked = db.unlocked_weakness()
    # Greedy cascade: unlock best frontier dock, rescore, repeat.
    for _ in range(cap):
        picked = _pick_best_assist_key(
            logic,
            eligible,
            groups,
            start_counts=counts,
            taken=assist_set,
            active=active,
        )
        if picked is None:
            break
        _delta, key = picked
        sides = groups.get(key) or []
        vanilla = (sides[0][1].get("default_dock_weakness") or UNLOCKED) if sides else UNLOCKED
        assist_vanilla[key] = vanilla
        DoorRando.apply_assignments(logic.parser, {key: unlocked})
        logic.rebuild_graph()
        assist.append(key)
        assist_set.add(key)

    # Restore vanilla for scoring mutations; pre_fill_roll re-applies unlocks.
    if assist_vanilla:
        DoorRando.apply_assignments(logic.parser, assist_vanilla)
        logic.rebuild_graph()

    remainder = [key for key in eligible if key not in assist_set]
    prop = (
        db.reroute_shuffle_proportion()
        if reroute_proportion is None
        else float(reroute_proportion)
    )
    prop = max(0.0, min(1.0, prop))
    remainder = list(remainder)
    rng.shuffle(remainder)
    n = int(len(remainder) * prop)
    if prop > 0.0 and remainder and n < 1:
        n = 1
    reroute = remainder[:n]
    return protected, assist, reroute


def select_shuffled_keys(
    eligible: List[PhysicalKey],
    rng,
    *,
    proportion: Optional[float] = None,
) -> List[PhysicalKey]:
    """Pick ~proportion of eligible docks (legacy helper; prefer classify_docks)."""
    if not eligible:
        return []
    prop = (
        db.reroute_shuffle_proportion()
        if proportion is None
        else float(proportion)
    )
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
    """Force docks to unlocked before item fill."""
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
    # Keep unlocked in the pool for sole-legal-choice fallback only.
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
    """Reach + incompat + shield filter."""
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
        if weakness == unlocked or weakness in OPEN_WEAKNESSES:
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


def interesting_lock_candidates(candidates: List[str]) -> List[str]:
    """Drop Power Beam / Access Open unless that is the only legal choice."""
    interesting = [c for c in candidates if c not in OPEN_WEAKNESSES]
    return interesting if interesting else list(candidates)


def weighted_lock_choice(rng, candidates: List[str]) -> str:
    """Bias toward higher-tier (harder) locks among still-legal candidates."""
    pool = interesting_lock_candidates(candidates)
    if len(pool) == 1:
        return pool[0]
    weights: List[int] = []
    for name in pool:
        tier = LOCK_TIER.get(name, 3)
        # Square tier so Wave/Grapple win more often than Missile when both ok.
        weights.append(max(1, tier * tier))
    total = sum(weights)
    roll = rng.randrange(total)
    acc = 0
    for name, w in zip(pool, weights):
        acc += w
        if roll < acc:
            return name
    return pool[-1]


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
    fill_assist_keys: Optional[Iterable[PhysicalKey]] = None,
) -> Dict[PhysicalKey, str]:
    """
    Assign reach-gated locks to the *reroute* set after item fill.

    Fill-assist docks stay Power Beam. Open weaknesses are excluded from the
    random choice unless they are the only legal option.
    """
    reroute = list(shuffled_keys)
    assist = list(fill_assist_keys or [])
    unlocked = db.unlocked_weakness()
    assignments: Dict[PhysicalKey, str] = {key: unlocked for key in assist}

    if not reroute:
        return assignments

    logic = world.logic
    groups = DoorRando.collect_physical_doors(logic.parser)
    pool = _target_pool(change_doors_to)

    shield_used: Dict[str, int] = defaultdict(int)
    touched = set(reroute) | set(assist)
    for key, sides in groups.items():
        if key in touched:
            continue
        weakness = sides[0][1].get("default_dock_weakness") or UNLOCKED
        dt = DoorRando.WEAKNESS_DOOR_TYPE.get(weakness)
        if dt in DoorRando.SHIELDED_DOOR_TYPES:
            shield_used[key[0]] += 2

    for key in reroute:
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
        chosen = weighted_lock_choice(rng, candidates)
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
    assist_cap: int = FILL_ASSIST_CAP,
    active: Optional[Set[str]] = None,
) -> PreFillResult:
    """
    Classify docks, force-unlock fill assists, unlock the reroute set for fill.

    ``change_doors_to`` is accepted for API symmetry; targets are applied in
    ``post_fill_assign``.
    """
    del change_doors_to  # applied post-fill
    protected, assist, reroute = classify_docks(
        logic,
        rng,
        doors_to_change=doors_to_change,
        start_counts=start_counts,
        assist_cap=assist_cap,
        reroute_proportion=proportion,
        active=active,
    )
    unlock_keys = list(dict.fromkeys([*assist, *reroute]))
    assignments = pre_fill_unlock_assignments(unlock_keys)
    return PreFillResult(
        assignments=assignments,
        reroute_keys=list(reroute),
        fill_assist_keys=list(assist),
        protected_keys=sorted(protected),
    )

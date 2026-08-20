"""
Victory-implies-clearance for Metroid Bread.

Clearable checks are pickups reachable from the chosen start with a full
inventory under the rolled logic (doors / transports / tricks). Raven Beak's
access rule (see Rules.py) requires a fraction of those checks to be
reachable with the current collection state:

- Defeat Raven Beak goal: ceil(0.9 * N)  (>=90%)
- 100% goal: all N clearable checks
- All Bosses goal: >=90% clearance, plus every non-RB boss node in logic

so the assumed fill cannot open victory on a tiny early softball.

post_fill re-checks the same invariant after placement.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List, Sequence, Set, Tuple

from BaseClasses import CollectionState, Location
from Fill import FillError

if TYPE_CHECKING:
    from . import MetroidBreadWorld

VICTORY_LOCATION = "Raven Beak"
_GOAL_NODE = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")
NodeId = Tuple[str, str, str]

# Default fraction of clearable checks that must be in logic when Raven Beak opens.
CLEARANCE_RATIO = 0.90
# GameGoal.option_one_hundred_percent / option_all_bosses
_GOAL_ONE_HUNDRED_PERCENT = 1
_GOAL_ALL_BOSSES = 2


def clearance_ratio_for_world(world: "MetroidBreadWorld") -> float:
    """Clearance ratio required when Raven Beak becomes reachable."""
    try:
        goal = int(world.options.game_goal.value)
    except Exception:
        goal = 0
    if goal == _GOAL_ONE_HUNDRED_PERCENT:
        return 1.0
    # All Bosses keeps the standard 90% pickup clearance; boss-node reachability
    # is enforced separately in Rules.py via bosses.inventory_reaches_all_boss_nodes.
    return CLEARANCE_RATIO


def required_clearance_count(clearable_count: int, ratio: float = CLEARANCE_RATIO) -> int:
    """Minimum clearable checks that must be reachable at victory."""
    if clearable_count <= 0:
        return 0
    if ratio >= 1.0:
        return clearable_count
    return max(1, math.ceil(ratio * clearable_count))


def allowed_missing_at_victory(clearable_count: int, ratio: float = CLEARANCE_RATIO) -> int:
    """How many clearable checks may still be locked when Raven Beak opens."""
    return max(0, clearable_count - required_clearance_count(clearable_count, ratio))


def clearable_pickup_names(world: "MetroidBreadWorld") -> List[str]:
    """Pickup checks reachable with full inventory from the world's start."""
    nodes = world.logic.get_reachable_nodes(
        world.logic.inventory_from_counts(world._full_inventory_counts())
    )
    active = set(world.active_location_names())
    names: List[str] = []
    for name, node in world.logic.pickup_nodes.items():
        if name == VICTORY_LOCATION:
            continue
        if name in active and node in nodes:
            names.append(name)
    names.sort()
    return names


def clearable_pickup_nodes(world: "MetroidBreadWorld") -> Tuple[NodeId, ...]:
    names = clearable_pickup_names(world)
    return tuple(world.logic.pickup_nodes[name] for name in names)


def real_check_locations(world: "MetroidBreadWorld") -> List[Location]:
    """Player pickup checks (addressed locations), excluding events / victory."""
    return [
        loc
        for loc in world.multiworld.get_locations(world.player)
        if loc.address is not None
    ]


def eventually_reachable_checks(world: "MetroidBreadWorld") -> Set[Location]:
    """Real checks obtainable after fill via max sphere sweep (diagnostics)."""
    state = CollectionState(world.multiworld)
    remaining = set(world.multiworld.get_filled_locations())
    for _ in range(len(remaining) + 4):
        sphere = [loc for loc in remaining if loc.can_reach(state)]
        if not sphere:
            break
        for loc in sphere:
            if loc.item:
                state.collect(loc.item, True, loc)
            remaining.discard(loc)
    return {loc for loc in real_check_locations(world) if loc.can_reach(state)}


def collection_state_at_victory(world: "MetroidBreadWorld") -> CollectionState:
    """
    Sweep spheres until Raven Beak is reachable; return that collection state.

    Raises FillError if Raven Beak never becomes reachable.
    """
    multiworld = world.multiworld
    player = world.player
    try:
        victory = multiworld.get_location(VICTORY_LOCATION, player)
    except KeyError as exc:
        raise FillError(
            f"Metroid Bread ({multiworld.get_player_name(player)}): "
            "Raven Beak location is missing after fill."
        ) from exc

    state = CollectionState(multiworld)
    remaining = set(multiworld.get_filled_locations())

    for _ in range(len(remaining) + 4):
        if victory.can_reach(state):
            return state
        sphere = [loc for loc in remaining if loc.can_reach(state)]
        if not sphere:
            break
        for loc in sphere:
            if loc.item:
                state.collect(loc.item, True, loc)
            remaining.discard(loc)

    raise FillError(
        f"Metroid Bread ({multiworld.get_player_name(player)}): "
        "Raven Beak is unreachable after fill."
    )


def missing_checks_at_victory(world: "MetroidBreadWorld") -> List[str]:
    """Clearable checks still locked when Raven Beak's AP location opens."""
    clearable = set(clearable_pickup_names(world))
    state = collection_state_at_victory(world)
    missing = []
    for loc in real_check_locations(world):
        if loc.name in clearable and not loc.can_reach(state):
            missing.append(loc.name)
    return sorted(missing)


def assert_victory_implies_full_clearance(world: "MetroidBreadWorld") -> None:
    """
    Hard generation guarantee: Raven Beak reachability implies the goal's
    clearance ratio of clearable checks.

    Raises FillError when too many clearable pickups are still locked at the
    first collection state that can reach Raven Beak.
    """
    ratio = clearance_ratio_for_world(world)
    clearable_n = len(clearable_pickup_names(world))
    missing = missing_checks_at_victory(world)
    allowed = allowed_missing_at_victory(clearable_n, ratio)
    if len(missing) > allowed:
        preview = ", ".join(missing[:12])
        more = f" (+{len(missing) - 12} more)" if len(missing) > 12 else ""
        player_name = world.multiworld.get_player_name(world.player)
        required = required_clearance_count(clearable_n, ratio)
        pct = int(ratio * 100)
        raise FillError(
            f"Metroid Bread ({player_name}): Raven Beak is reachable while "
            f"{len(missing)} clearable check(s) are not "
            f"(victory must imply >={pct}% clearance: "
            f"need {required}/{clearable_n}, allow {allowed} missing). "
            f"Missing e.g.: {preview}{more}"
        )

    try:
        goal = int(world.options.game_goal.value)
    except Exception:
        goal = 0
    if goal == _GOAL_ALL_BOSSES:
        from . import bosses

        state = collection_state_at_victory(world)
        locked = bosses.missing_bosses_at_state(world, state)
        # Raven Beak itself is reachable by definition here; only non-RB matter.
        locked = [n for n in locked if n != "Raven Beak"]
        if locked:
            player_name = world.multiworld.get_player_name(world.player)
            preview = ", ".join(locked[:12])
            raise FillError(
                f"Metroid Bread ({player_name}): All Bosses goal — Raven Beak "
                f"opens while boss node(s) are still locked: {preview}"
            )


def raven_beak_sphere_index(world: "MetroidBreadWorld") -> int:
    """
    0-based sphere index containing Raven Beak, or -1 if unreachable / dumped
    into the unreachable set.
    """
    multiworld = world.multiworld
    player = world.player
    try:
        victory = multiworld.get_location(VICTORY_LOCATION, player)
    except KeyError:
        return -1

    saw_empty = False
    for index, sphere in enumerate(multiworld.get_spheres()):
        if not sphere:
            saw_empty = True
            continue
        if victory in sphere:
            return -1 if saw_empty else index
    return -1


def inventory_reaches_victory_and_clearance(
    world: "MetroidBreadWorld",
    state: CollectionState,
    clearable_nodes: Sequence[NodeId] | None = None,
) -> bool:
    """True when Boss Raven Beak is in logic and clearance ratio is met."""
    logic = world.logic
    if clearable_nodes is None:
        clearable_nodes = clearable_pickup_nodes(world)
    reachable = logic.get_reachable_nodes(logic.inventory_from_state(state))
    if _GOAL_NODE not in reachable:
        return False
    if not clearable_nodes:
        return True
    reached = sum(1 for node in clearable_nodes if node in reachable)
    ratio = clearance_ratio_for_world(world)
    return reached >= required_clearance_count(len(clearable_nodes), ratio)


def assert_graph_preflight(world: "MetroidBreadWorld") -> None:
    """
    Fail fast if the rolled door/transport graph cannot support a seed.

    Checks (full inventory from start):
    - Raven Beak boss node is reachable
    - At least one clearable pickup exists
    """
    player_name = world.multiworld.get_player_name(world.player)
    nodes = world.logic.get_reachable_nodes(
        world.logic.inventory_from_counts(world._full_inventory_counts())
    )
    if _GOAL_NODE not in nodes:
        doors = "on" if world.door_assignments else "off"
        transports = "on" if world.transport_matching else "off"
        raise FillError(
            f"Metroid Bread ({player_name}): Raven Beak is unreachable even "
            f"with a full inventory under the rolled graph "
            f"(door_lock_rando={doors}, transport_rando={transports}). "
            f"Re-roll doors/transports or relax those options."
        )
    clearable = clearable_pickup_names(world)
    if not clearable:
        raise FillError(
            f"Metroid Bread ({player_name}): no clearable pickup checks from "
            f"the starting location under the rolled logic graph."
        )


def assert_location_capacity(world: "MetroidBreadWorld") -> None:
    """
    Fail fast when progression (+ locked DNA) cannot fit in active locations.
    """
    player = world.player
    player_name = world.multiworld.get_player_name(player)
    active = set(world.active_location_names())
    # Locations still open for the main fill (not already locked in pre_fill).
    open_locs = [
        loc
        for loc in world.multiworld.get_locations(player)
        if loc.address is not None and loc.name in active and not loc.item
    ]
    prog_in_pool = [
        item
        for item in world.multiworld.itempool
        if item.player == player and item.advancement
    ]
    if len(prog_in_pool) > len(open_locs):
        raise FillError(
            f"Metroid Bread ({player_name}): not enough open locations for "
            f"progression items ({len(prog_in_pool)} progression vs "
            f"{len(open_locs)} open checks). Enable boss pickups, lower DNA, "
            f"or reduce stacked progressives."
        )

"""Randovania Individual Doors placement for Metroid Bread.

This follows ``distribute_pre_fill_weaknesses`` / ``distribute_post_fill_weaknesses``
in Randovania's ``dock_weakness_distributor.py`` (DockRandoMode.DOCKS), using
Bread's logic graph. It does not run when the YAML option is off.

Gaps vs Randovania (documented, not papered over):

- The per-door "first reach" inventory is Bread's sphere frontier: every item
  collected in earlier spheres, at the first sphere that can stand on either
  side while the door is sealed. Randovania uses the single resolver state
  that first touched either side, which can know fewer items and therefore
  under-lock. The item that sits only behind the sealed door is still excluded.
- There is no 250-step resolver timeout. A door Bread can reach is locked from
  that inventory. Randovania leaves the door Power Beam when the search hits
  250 steps. Unreachable doors still stay Power Beam.
- The all-blue solvability check is a full sphere sweep to Raven Beak, not
  Randovania's 500-step cap. An unsolvable open-door game aborts. A solvable
  one is not aborted for being expensive.
- ``Access Permanently Closed`` (weight 2) is implemented, but Bread's Change
  Doors To list does not include it and the patcher rejects ``door_type``
  ``closed``, so it is not rolled.
- Four Central Unit open frames have no actor. Logic can retarget them.
  ``door_patches`` skips them, matching Randovania's exporter.
- The RNG is the world's ``self.random`` after item fill, not Randovania's
  permalink ``Random``. The draws themselves match: shuffle, ``int(n * 0.6)``,
  shuffle, ``pop``, then one ``rng.choices`` via the same weighted helper.
- Bread still enforces victory-implies-clearance after the locks. Randovania
  does not.
"""
from __future__ import annotations

import time
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

from BaseClasses import CollectionState
from Fill import FillError

from worlds.metroid_bread.logic import DoorRando
from worlds.metroid_bread.logic import door_rando_db as db

NodeId = DoorRando.NodeId
PhysicalKey = DoorRando.PhysicalKey

UNLOCKED = "Power Beam Door"
SEALED = "Access Permanently Closed"


class RdvDoorPair(NamedTuple):
    """One two-way connection. ``dock`` is the side region order hits first."""

    dock: NodeId
    target: NodeId
    dock_vanilla: str
    target_vanilla: str


class PreFillResult(NamedTuple):
    pairs: List[RdvDoorPair]
    unlock_nodes: List[NodeId]
    assignments: Dict[PhysicalKey, str]


def _node(parser, nid: NodeId) -> dict:
    region, area, name = nid
    return parser.regions[region]["areas"][area]["nodes"][name]


def _connection_target(region: str, node: dict) -> Optional[NodeId]:
    conn = node.get("default_connection") or {}
    area = conn.get("area")
    name = conn.get("node")
    if not area or not name:
        return None
    return (conn.get("region", region), area, name)


def _iter_dock_nodes(parser):
    for region_name, region in parser.regions.items():
        areas = region.get("areas") or {}
        if not isinstance(areas, dict):
            continue
        for area_name, area in areas.items():
            nodes = (area or {}).get("nodes") or {}
            if not isinstance(nodes, dict):
                continue
            for node_name, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                if node.get("node_type") != "dock":
                    continue
                yield (region_name, area_name, node_name), node


def _all_dock_links(parser):
    """Dock nodes whose target is also a dock, in region-list order."""
    links = []
    for nid, node in _iter_dock_nodes(parser):
        tid = _connection_target(nid[0], node)
        if tid is None:
            continue
        try:
            tnode = _node(parser, tid)
        except KeyError:
            continue
        if not isinstance(tnode, dict) or tnode.get("node_type") != "dock":
            continue
        links.append((nid, node, tid, tnode))
    return links


def _change_from_set(doors_to_change: Iterable[str]) -> Set[str]:
    requested = set(doors_to_change) & DoorRando.ALL_DOOR_WEAKNESS_NAMES
    if not requested:
        requested = set(db.header_change_from())
    return requested


def _change_to_set(change_doors_to: Iterable[str]) -> Set[str]:
    requested = set(change_doors_to) & DoorRando.ALL_DOOR_WEAKNESS_NAMES
    if not requested:
        requested = set(DoorRando.DEFAULT_CHANGE_DOORS_TO)
    return requested


def actor_key(region: str, node: dict) -> Optional[PhysicalKey]:
    """Patchable ``(scenario, actor)``. Nodes with no actor return None."""
    extra = node.get("extra") or {}
    actor = extra.get("actor_name")
    if not actor:
        return None
    if not db.is_odr_patchable_door_actor(str(actor), extra.get("actor_def")):
        return None
    scenario = DoorRando.REGION_TO_SCENARIO.get(region)
    if not scenario:
        return None
    return (scenario, str(actor))


def _rollable_target(name: str) -> bool:
    """True when the patcher can emit this weakness. Power Beam is always ok.

    Access Permanently Closed and open frames are legal in Randovania's
    database but Bread's patcher rejects ``closed`` / ``frame``.
    """
    if name == UNLOCKED:
        return True
    door_type = DoorRando.WEAKNESS_DOOR_TYPE.get(name)
    if not door_type or door_type in DoorRando.ODR_CANNOT_ADD_DOOR_TYPES:
        return False
    return door_type in db.BASIC_ODR_DOOR_TYPES


def collect_pairs(parser, doors_to_change: Iterable[str]) -> Tuple[List[RdvDoorPair], List[NodeId]]:
    """Eligible doors plus same-type partners, collapsed to one pair each."""
    change_from = _change_from_set(doors_to_change)
    links = _all_dock_links(parser)

    unlock: List[NodeId] = []
    unlock_set: Set[NodeId] = set()
    for nid, node, _tid, _tnode in links:
        if node.get("dock_type") != "door":
            continue
        if node.get("exclude_from_dock_rando"):
            continue
        vanilla = node.get("default_dock_weakness") or ""
        if vanilla not in change_from:
            continue
        unlock.append(nid)
        unlock_set.add(nid)

    if db.force_change_two_way():
        for nid, node, tid, tnode in links:
            if nid in unlock_set or tid not in unlock_set:
                continue
            if node.get("dock_type") != tnode.get("dock_type"):
                continue
            unlock.append(nid)
            unlock_set.add(nid)

    seen_reps: Set[NodeId] = set()
    pairs: List[RdvDoorPair] = []
    for nid, node, tid, tnode in links:
        if nid not in unlock_set:
            continue
        if tid in seen_reps:
            continue
        seen_reps.add(nid)
        pairs.append(
            RdvDoorPair(
                dock=nid,
                target=tid,
                dock_vanilla=node.get("default_dock_weakness") or "",
                target_vanilla=(tnode.get("default_dock_weakness") or ""),
            )
        )
    return pairs, unlock


def _refresh_dock_edge(logic, nid: NodeId) -> None:
    """Keep the live adjacency edge in step with ``default_dock_weakness``."""
    parser = logic.parser
    try:
        node = _node(parser, nid)
    except KeyError:
        return
    if node.get("override_default_open_requirement") is not None:
        return
    target = _connection_target(nid[0], node)
    if target is None:
        return
    edges = logic._adj.get(nid)
    if not edges:
        return
    req = parser._get_dock_weakness_requirement(node.get("default_dock_weakness"))
    for index, (dest, _old) in enumerate(edges):
        if dest == target:
            edges[index] = (dest, req)
            return


def _set_node_weakness(logic, nid: NodeId, weakness: str) -> None:
    node = _node(logic.parser, nid)
    node["default_dock_weakness"] = weakness
    _refresh_dock_edge(logic, nid)


def _write_node_ids(pair: RdvDoorPair, change_from: Set[str]) -> List[NodeId]:
    nodes = [pair.dock]
    if pair.target == pair.dock:
        return nodes
    if pair.target_vanilla in change_from or db.force_change_two_way():
        nodes.append(pair.target)
    return nodes


def _seal_node_ids(pair: RdvDoorPair) -> List[NodeId]:
    nodes = [pair.dock]
    if pair.target != pair.dock:
        nodes.append(pair.target)
    return nodes


def commit_weakness(
    logic,
    node_ids: Iterable[NodeId],
    weakness: str,
    assignments: Dict[PhysicalKey, str],
) -> None:
    """Write one weakness onto both sides and every node that shares the actor."""
    parser = logic.parser
    keys: List[PhysicalKey] = []
    for nid in node_ids:
        try:
            node = _node(parser, nid)
        except KeyError:
            continue
        _set_node_weakness(logic, nid, weakness)
        key = actor_key(nid[0], node)
        if key and key not in keys:
            keys.append(key)
    if keys:
        patch = {key: weakness for key in keys}
        assignments.update(patch)
        DoorRando.apply_assignments(parser, patch)
        key_set = set(keys)
        for nid, node in DoorRando._iter_door_docks(parser):
            key = actor_key(nid[0], node)
            if key in key_set:
                _refresh_dock_edge(logic, nid)
    logic._reachable_cache.clear()


def pre_fill(logic, *, doors_to_change: Iterable[str]) -> PreFillResult:
    """Set every eligible door and same-type partner to Power Beam. No RNG."""
    pairs, unlock = collect_pairs(logic.parser, doors_to_change)
    assignments: Dict[PhysicalKey, str] = {}
    for nid in unlock:
        try:
            node = _node(logic.parser, nid)
        except KeyError:
            continue
        node["default_dock_weakness"] = UNLOCKED
        key = actor_key(nid[0], node)
        if key:
            assignments[key] = UNLOCKED
    logic.rebuild_graph()
    return PreFillResult(pairs=pairs, unlock_nodes=list(unlock), assignments=assignments)


def reapply_unlocked(logic, unlock_nodes: Iterable[NodeId], assignments: Dict[PhysicalKey, str]) -> None:
    """Put a fresh parser back to the pre-fill Power Beam graph."""
    for nid in unlock_nodes:
        try:
            _node(logic.parser, nid)["default_dock_weakness"] = UNLOCKED
        except KeyError:
            continue
    if assignments:
        DoorRando.apply_assignments(logic.parser, assignments)
    logic.rebuild_graph()


def _door_items(parser) -> dict:
    header = parser.header or {}
    types = (header.get("dock_weakness_database") or {}).get("types") or {}
    return ((types.get("door") or {}).get("items") or {})


def weakness_satisfied(logic, weakness: str, inventory) -> bool:
    """Both the crossing requirement and the one-time lock, when present."""
    data = _door_items(logic.parser).get(weakness)
    if not isinstance(data, dict):
        return False
    if not logic.evaluate_requirement(data.get("requirement"), inventory):
        return False
    lock = data.get("lock")
    if isinstance(lock, dict) and lock.get("requirement") is not None:
        return logic.evaluate_requirement(lock.get("requirement"), inventory)
    return True


def _incompatible(parser, pair: RdvDoorPair) -> Set[str]:
    bans: Set[str] = set()
    for nid in (pair.dock, pair.target):
        try:
            node = _node(parser, nid)
        except KeyError:
            continue
        bans.update(node.get("incompatible_dock_weaknesses") or [])
    return bans


def _dock_area_reach(parser, start: NodeId) -> Set[Tuple[str, str]]:
    """Areas reachable by dock hops, ignoring item requirements.

    Same idea as Randovania ``distances_to_node`` with no dock types ignored.
    """
    edges: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
    for nid, _node_obj, tid, _tnode in _all_dock_links(parser):
        src = (nid[0], nid[1])
        dst = (tid[0], tid[1])
        edges.setdefault(src, set()).add(dst)
    start_area = (start[0], start[1])
    reached = {start_area}
    queue = [start_area]
    while queue:
        current = queue.pop()
        for nxt in edges.get(current, ()):
            if nxt in reached:
                continue
            reached.add(nxt)
            queue.append(nxt)
    return reached


def _arrival_inventory(world, side_ids: List[NodeId]):
    """Sphere-frontier inventory when either side is first reachable.

    Returns None when neither side is reachable with the placed items.
    The door must already be sealed by the caller.
    """
    logic = world.logic
    state = CollectionState(world.multiworld)
    remaining = {
        loc
        for loc in world.multiworld.get_filled_locations()
        if loc.player == world.player
    }
    for _ in range(len(remaining) + 8):
        inv = logic.inventory_from_state(state)
        reachable = logic.get_reachable_nodes(inv)
        if any(nid in reachable for nid in side_ids):
            return inv
        sphere = [loc for loc in remaining if loc.can_reach(state)]
        if not sphere:
            return None
        for loc in sphere:
            if loc.item:
                state.collect(loc.item, True, loc)
            remaining.discard(loc)
    return None


def _both_sides_connect(logic, inventory, arrival: NodeId, other: NodeId) -> bool:
    """True when each side can reach the other without crossing the sealed door."""
    if other not in logic.get_reachable_nodes(inventory, start=arrival):
        return False
    return arrival in logic.get_reachable_nodes(inventory, start=other)


def _weighted_weaknesses(
    logic,
    pair: RdvDoorPair,
    change_to: Set[str],
    inventory,
    *,
    reached: Set[NodeId],
) -> Dict[str, float]:
    weighted: Dict[str, float] = {UNLOCKED: 1.0}
    if inventory is None:
        return weighted

    exclusions = _incompatible(logic.parser, pair)
    locked = db.locked_weakness()
    # Use the main side if reachable; otherwise use the reachable target side.
    if pair.dock in reached:
        arrival, other = pair.dock, pair.target
    elif pair.target in reached:
        arrival, other = pair.target, pair.dock
    else:
        return weighted

    if (
        locked in change_to
        and locked not in exclusions
        and _rollable_target(locked)
        and other in reached
        and _both_sides_connect(logic, inventory, arrival, other)
    ):
        weighted[locked] = 2.0

    exclusions.update(weighted.keys())
    satisfied = []
    for name in sorted(change_to - exclusions):
        if not _rollable_target(name):
            continue
        if weakness_satisfied(logic, name, inventory):
            satisfied.append(name)
    for name in satisfied:
        weighted[name] = 1.0
    return weighted


def select_weighted(rng, weighted: Dict[str, float]) -> str:
    """One draw, matching ``random_lib.select_element_with_weight``."""
    item_list = list(weighted.keys())
    weights = [max(weighted[item], 0.0) for item in item_list]
    return rng.choices(item_list, weights)[0]


def post_fill_locks(
    world,
    pairs: List[RdvDoorPair],
    rng,
    *,
    doors_to_change: Iterable[str],
    change_doors_to: Iterable[str],
    assignments: Dict[PhysicalKey, str],
) -> dict:
    """Lock ``int(n * 0.6)`` pairs. Earlier choices are visible to later doors."""
    from worlds.metroid_bread.logic import victory_clearance

    change_from = _change_from_set(doors_to_change)
    change_to = _change_to_set(change_doors_to)
    started = time.perf_counter()
    stats = {
        "pairs": len(pairs),
        "kept": 0,
        "solved_open": False,
        "skipped_unconnected": 0,
        "unreachable": 0,
        "seconds": 0.0,
    }
    if not pairs:
        stats["solved_open"] = True
        stats["seconds"] = time.perf_counter() - started
        return stats

    try:
        victory_clearance.collection_state_at_victory(world)
    except FillError as exc:
        raise FillError(
            "Unable to solve game with all Randovania door-rando doors "
            f"unlocked. {exc}"
        ) from exc
    stats["solved_open"] = True

    proportion = float(db.to_shuffle_proportion())
    pool = list(pairs)
    if proportion < 1.0:
        rng.shuffle(pool)
        limit = int(len(pool) * proportion)
        pool = pool[:limit]
    rng.shuffle(pool)
    stats["kept"] = len(pool)

    areas = _dock_area_reach(world.logic.parser, world.logic.starting_node)
    logic = world.logic
    only_unlocked = change_to == {UNLOCKED}

    while pool:
        pair = pool.pop()
        dock_area = (pair.dock[0], pair.dock[1])
        target_area = (pair.target[0], pair.target[1])
        skip = only_unlocked or (
            dock_area not in areas and target_area not in areas
        )
        if skip and dock_area not in areas and target_area not in areas and not only_unlocked:
            stats["skipped_unconnected"] += 1

        write_ids = _write_node_ids(pair, change_from)
        if skip:
            chosen = select_weighted(rng, {UNLOCKED: 1.0})
            commit_weakness(logic, write_ids, chosen, assignments)
            continue

        seal_ids = _seal_node_ids(pair)
        previous: Dict[NodeId, str] = {}
        for nid in seal_ids:
            try:
                previous[nid] = _node(logic.parser, nid).get("default_dock_weakness") or UNLOCKED
            except KeyError:
                continue
            _set_node_weakness(logic, nid, SEALED)
        logic._reachable_cache.clear()

        committed = False
        try:
            inv = _arrival_inventory(world, seal_ids)
            if inv is None:
                stats["unreachable"] += 1
                weighted = {UNLOCKED: 1.0}
                reached: Set[NodeId] = set()
            else:
                reached = logic.get_reachable_nodes(inv)
                weighted = _weighted_weaknesses(
                    logic,
                    pair,
                    change_to,
                    inv,
                    reached=reached,
                )
            chosen = select_weighted(rng, weighted)
            commit_weakness(logic, write_ids, chosen, assignments)
            committed = True
        finally:
            if not committed:
                for nid, weakness in previous.items():
                    try:
                        _set_node_weakness(logic, nid, weakness)
                    except KeyError:
                        continue
                logic._reachable_cache.clear()

    # Show the new lock on every node sharing this actor.
    # Include nodes not used to represent the door.
    conflicts = 0
    for nid, node in DoorRando._iter_door_docks(logic.parser):
        key = actor_key(nid[0], node)
        if key is None or key not in assignments:
            continue
        if node.get("default_dock_weakness") != assignments[key]:
            conflicts += 1
            _set_node_weakness(logic, nid, assignments[key])
    stats["actor_conflicts_fixed"] = conflicts
    logic._reachable_cache.clear()
    # Rebuild links once before checking access to victory.
    logic.rebuild_graph()
    stats["seconds"] = time.perf_counter() - started
    return stats

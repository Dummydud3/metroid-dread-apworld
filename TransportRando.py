"""Transport (elevator/shuttle) randomizer for Metroid Bread (working-simple)."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from .DoorRando import REGION_TO_SCENARIO

NodeId = Tuple[str, str, str]
SideId = str  # "Region/Area/Node"

# Ghavoran Elun shuttle has a cutscene actor plus a non-cutscene twin that must
# stay in sync for the map / usable to update correctly (matches Randovania).
_FLIPPER_CUTSCENE_ACTOR = "wagontrain_quarantine_with_cutscene_000"
_FLIPPER_PLAIN_ACTOR = "wagontrain_quarantine_000"

# Itorash must stay on its vanilla Hanubia capsule. Pairing it with Cataris /
# Artaria (or any mid-game elevator) lets DNA-0 seeds reach Raven Beak after a
# couple of local checks once StartKit has handed out Power Bomb.
_LOCKED_TRANSPORT_REGIONS = frozenset({"Itorash"})


def _is_shufflable(meta: dict) -> bool:
    region = meta["node_id"][0]
    if region in _LOCKED_TRANSPORT_REGIONS:
        return False
    vanilla = meta.get("vanilla_dest") or ()
    if vanilla and vanilla[0] in _LOCKED_TRANSPORT_REGIONS:
        return False
    return True


def _side_id(node_id: NodeId) -> SideId:
    return f"{node_id[0]}/{node_id[1]}/{node_id[2]}"


def _arrival_spawn(extra: dict, actor: str) -> str:
    """Local platform/spawn to land on when arriving at this transport.

    Must be start_point_actor_name (same as Randovania). Never use
    target_spawn_point — that is the *vanilla remote* platform and points
    shuffled elevators at actors that do not exist in the destination scenario
    (guest null-deref / Ryujinx Invalid memory at 0x0).
    """
    start = extra.get("start_point_actor_name")
    if isinstance(start, str) and start.strip():
        return start.strip()
    # Last resort: the teleporter actor itself (some docks share the name).
    if isinstance(actor, str) and actor.strip():
        return actor.strip()
    raise ValueError(
        "transport dock missing start_point_actor_name and actor_name; "
        f"extra keys={sorted(extra)}"
    )


def _connection_label(meta: dict) -> str:
    """Human-readable destination label for map icons / room-name overlay.

    Strip '.' so ODR icon ids (RDV_TRANSPORT_{name without spaces}) stay safe —
    e.g. 'Hanubia - E.M.M.I.' → 'Hanubia - EMMI'.
    """
    if meta.get("transporter_name"):
        raw = str(meta["transporter_name"])
    else:
        region, area, _node = meta["node_id"]
        raw = f"{region} - {area}"
    return raw.replace(".", "").strip() or "Unknown"


def _iter_transport_docks(parser):
    for region_name, region in parser.regions.items():
        for area_name, area in (region.get("areas") or {}).items():
            area_extra = area.get("extra") or {}
            for node_name, node in (area.get("nodes") or {}).items():
                if node.get("node_type") != "dock":
                    continue
                dock_type = node.get("dock_type")
                if dock_type not in ("elevator", "shuttle"):
                    continue
                extra = node.get("extra") or {}
                actor = extra.get("actor_name")
                if not actor:
                    continue
                scenario = REGION_TO_SCENARIO.get(region_name)
                if not scenario:
                    continue
                conn = node.get("default_connection") or {}
                yield {
                    "side_id": _side_id((region_name, area_name, node_name)),
                    "node_id": (region_name, area_name, node_name),
                    "node": node,
                    "type": dock_type,
                    "scenario": scenario,
                    "actor": actor,
                    # Arrival spawn in *this* scenario (local platform).
                    "arrival_spawn": _arrival_spawn(extra, actor),
                    "asset_id": area_extra.get("asset_id"),
                    "transporter_name": extra.get("transporter_name"),
                    "vanilla_dest": (
                        conn.get("region", region_name),
                        conn.get("area"),
                        conn.get("node"),
                    ),
                }


def collect_transports(parser) -> Dict[SideId, dict]:
    return {t["side_id"]: t for t in _iter_transport_docks(parser)}


def roll_matching(transports: Dict[SideId, dict], rng, mode: str = "randomized") -> Dict[SideId, SideId]:
    if mode in ("off", "vanilla", None) or mode == 0:
        return {}
    by_type: Dict[str, List[SideId]] = defaultdict(list)
    for sid, meta in transports.items():
        if not _is_shufflable(meta):
            continue
        by_type[meta["type"]].append(sid)
    matching: Dict[SideId, SideId] = {}
    for _typ, sides in by_type.items():
        # Retry a few shuffles so we can avoid same-scenario pairs (game assumes
        # a scenario change on transport use; same-scenario has crashed in AP play).
        best: Dict[SideId, SideId] = {}
        best_cross = -1
        for _attempt in range(24):
            order = list(sides)
            order.sort()
            rng.shuffle(order)
            trial: Dict[SideId, SideId] = {}
            cross = 0
            for i in range(0, len(order) - 1, 2):
                a, b = order[i], order[i + 1]
                trial[a] = b
                trial[b] = a
                if transports[a]["scenario"] != transports[b]["scenario"]:
                    cross += 1
            if cross > best_cross:
                best = trial
                best_cross = cross
            if cross == len(order) // 2:
                break
        matching.update(best)
    return matching


def apply_matching(parser, transports: Dict[SideId, dict], matching: Dict[SideId, SideId]) -> None:
    """Rewrite default_connection targets for shuffled transports."""
    if not matching:
        return
    for src_id, dest_id in matching.items():
        src = transports.get(src_id)
        dest = transports.get(dest_id)
        if not src or not dest:
            continue
        dr, da, dn = dest["node_id"]
        src["node"]["default_connection"] = {
            "region": dr,
            "area": da,
            "node": dn,
        }


def apply_matching_from_slot_data(parser, matching: Optional[Dict[SideId, SideId]]) -> int:
    """
    Apply a serialized transport_matching dict onto a fresh parser graph.

    Returns how many sides were rewritten. Used by the AP client tracker so
    in-logic / minimap paint match shuffled elevators in the patched game.
    """
    if not matching:
        return 0
    transports = collect_transports(parser)
    apply_matching(parser, transports, matching)
    return sum(1 for sid in matching if sid in transports)


def _elevator_entry(src: dict, dest: dict) -> dict:
    dest_actor = dest.get("arrival_spawn") or dest.get("actor")
    if not dest_actor or not dest.get("scenario"):
        raise ValueError(
            f"elevator entry missing destination fields: src={src.get('side_id')} "
            f"dest={dest.get('side_id')} scenario={dest.get('scenario')} actor={dest_actor}"
        )
    return {
        "teleporter": {"scenario": src["scenario"], "actor": src["actor"]},
        "destination": {
            "scenario": dest["scenario"],
            "actor": dest_actor,
        },
        "connection_name": _connection_label(dest),
        "source_camera": src.get("asset_id"),
    }


def matching_to_elevators(
    matching: Dict[SideId, SideId],
    transports: Dict[SideId, dict],
) -> List[dict]:
    elevators = []
    seen = set()
    for src_id, dest_id in matching.items():
        if src_id in seen:
            continue
        seen.add(src_id)
        seen.add(dest_id)
        src = transports[src_id]
        dest = transports[dest_id]
        elevators.append(_elevator_entry(src, dest))
        elevators.append(_elevator_entry(dest, src))

    # Keep the non-cutscene Flipper twin synced when the cutscene shuttle is shuffled.
    flipper = [
        e for e in elevators
        if e["teleporter"]["actor"] == _FLIPPER_CUTSCENE_ACTOR
    ]
    for entry in flipper:
        twin = deepcopy(entry)
        twin["teleporter"] = dict(twin["teleporter"])
        twin["teleporter"]["actor"] = _FLIPPER_PLAIN_ACTOR
        elevators.append(twin)

    return elevators


def roll_connected_matching(
    logic,
    rng,
    mode: str = "randomized",
    attempts: int = 40,
) -> Tuple[Dict[SideId, SideId], Dict[SideId, dict]]:
    """
    Roll a transport matching that does not regress full-loadout reachability.
    Returns (matching, transports). matching may be {} on failure / off.
    """
    transports = collect_transports(logic.parser)
    if mode in ("off", "vanilla", None) or mode == 0 or not transports:
        return {}, transports

    # Full-ish loadout for regression check.
    full_counts = {
        "Morph Ball": 1, "Bomb": 1, "Cross Bomb": 1, "Power Bomb": 1,
        "Charge Beam": 1, "Wide Beam": 1, "Plasma Beam": 1, "Wave Beam": 1,
        "Diffusion Beam": 1, "Grapple Beam": 1, "Ice Missile": 1,
        "Storm Missile": 1, "Super Missile": 1, "Varia Suit": 1, "Gravity Suit": 1,
        "Phantom Cloak": 1, "Flash Shift Upgrade": 3, "Pulse Radar": 1,
        "Speed Booster": 1, "Spider Magnet": 1, "Spin Boost": 1, "Space Jump": 1,
        "Screw Attack": 1, "Energy Tank": 12, "Missile Tank": 20, "Power Bomb Tank": 5,
    }
    def refresh() -> None:
        # Dock targets are baked into the adjacency cache, so a plain cache
        # clear would leave the reachability check looking at the old graph.
        logic.rebuild_graph()

    baseline_inv = logic.inventory_from_counts(full_counts)
    baseline = logic.get_reachable_nodes(baseline_inv)
    baseline_pickups = {
        name for name, node in logic.pickup_nodes.items() if node in baseline
    }

    for _ in range(attempts):
        matching = roll_matching(transports, rng, mode="randomized")
        # Apply temporarily
        backups = {}
        for sid, meta in transports.items():
            backups[sid] = dict(meta["node"].get("default_connection") or {})
        apply_matching(logic.parser, transports, matching)
        ok = False
        try:
            inv = logic.inventory_from_counts(full_counts)
            refresh()
            reach = logic.get_reachable_nodes(inv)
            pickups = {name for name, node in logic.pickup_nodes.items() if node in reach}
            ok = baseline_pickups <= pickups
        finally:
            if not ok:
                for sid, conn in backups.items():
                    transports[sid]["node"]["default_connection"] = conn
                refresh()
        if ok:
            return matching, transports

    return {}, transports

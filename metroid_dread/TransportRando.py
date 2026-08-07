"""Transport (elevator/shuttle) randomizer for Metroid Dread (working-simple)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .DoorRando import REGION_TO_SCENARIO

NodeId = Tuple[str, str, str]
SideId = str  # "Region/Area/Node"


def _side_id(node_id: NodeId) -> SideId:
    return f"{node_id[0]}/{node_id[1]}/{node_id[2]}"


def _iter_transport_docks(parser):
    for region_name, region in parser.regions.items():
        for area_name, area in (region.get("areas") or {}).items():
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
                    "target_spawn": extra.get("target_spawn_point")
                        or extra.get("start_point_actor_name")
                        or actor,
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
        by_type[meta["type"]].append(sid)
    matching: Dict[SideId, SideId] = {}
    for _typ, sides in by_type.items():
        order = list(sides)
        order.sort()
        rng.shuffle(order)
        for i in range(0, len(order) - 1, 2):
            a, b = order[i], order[i + 1]
            matching[a] = b
            matching[b] = a
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
        elevators.append({
            "teleporter": {"scenario": src["scenario"], "actor": src["actor"]},
            "destination": {
                "scenario": dest["scenario"],
                "actor": dest.get("target_spawn") or dest["actor"],
            },
        })
        elevators.append({
            "teleporter": {"scenario": dest["scenario"], "actor": dest["actor"]},
            "destination": {
                "scenario": src["scenario"],
                "actor": src.get("target_spawn") or src["actor"],
            },
        })
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

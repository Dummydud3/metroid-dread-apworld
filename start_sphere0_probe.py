#!/usr/bin/env python3
"""
Probe StartKit / sphere-0 for Hub YAML validation.

Usage (from Archipelago repo root or with PYTHONPATH set):
  py -3.12 -m worlds.metroid_bread.start_sphere0_probe
  # JSON request on stdin → JSON response on stdout

Request keys:
  starting_location: default | random_save_station | option_key
  starting_kit_items: 0–5
  tricks: {option_name: level int}
  door_lock_rando / transport_rando: 0|1 (or string)
    door_lock_rando=1 applies Individual Doors pre-fill unlocks (same as gen)
    transport_rando=1 rolls a connected elevator/shuttle matching
  doors_to_change / change_doors_to: option-set lists (door rando pools)
  accessibility: items | full | minimal (Full runs uncleared-logic check)
  progressive_* / include_boss_pickups / … optional overrides
  seed: int (StartKit shuffle + door/transport rolls)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Flat Hub runtime extracts put this script next to world Options.py. Running as
# a script prepends that directory to sys.path *ahead of* PYTHONPATH, so
# `import Options` resolves to the world module instead of ap_core/Options and
# BaseClasses dies with a circular ImportError. Fix path order before any
# world / AP imports.
_WORLD_DIR = Path(__file__).resolve().parent
_AP_CORE = _WORLD_DIR / "ap_core"


def _bootstrap_import_path() -> Path:
    """Prefer ap_core (AP Options/BaseClasses) over the world script directory."""
    env_core = (os.environ.get("DREAD_HUB_AP_ROOT") or "").strip()
    core = Path(env_core) if env_core else _AP_CORE
    if not (core / "Options.py").is_file():
        core = _AP_CORE
    core_s = str(core.resolve()) if core.is_dir() else ""
    world_s = str(_WORLD_DIR.resolve())

    cleaned: List[str] = []
    for entry in sys.path:
        if entry in ("", "."):
            try:
                if Path.cwd().resolve() == _WORLD_DIR.resolve():
                    continue
            except OSError:
                pass
        try:
            resolved = str(Path(entry).resolve()) if entry else entry
        except OSError:
            resolved = entry
        if resolved == world_s:
            continue
        if core_s and resolved == core_s:
            continue
        cleaned.append(entry)
    sys.path[:] = cleaned
    if core_s:
        sys.path.insert(0, core_s)

    # Repo checkout: worlds/metroid_bread → Archipelago root (for optional tools).
    # Flat runtime: parents[2] is ProgramData/Archipelago — harmless if unused.
    root = _WORLD_DIR.parents[2]
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.append(root_s)
    return root


_ROOT = _bootstrap_import_path()

TRICK_KEYS = (
    "knowledge_tricks",
    "movement_tricks",
    "combat_tricks",
    "slide_jump",
    "wall_jump_tricks",
    "infinite_bomb_jump",
    "water_bomb_jump",
    "water_space_jump",
    "single_wall_wall_jump",
    "diagonal_bomb_jump",
    "cross_bomb_launch",
    "grapple_movement",
    "speedbooster_conservation",
    "short_boost",
    "flash_shift_skip",
    "heat_cold_runs",
    "climb_sloped_tunnels",
    "climb_sloped_surfaces",
    "floor_clip",
    "damage_boost",
    "pseudo_wave",
    "diffusion_abuse",
    "stand_on_frozen_enemy",
    "cross_bomb_skip",
    "ledge_warp",
)

_BOSS_EMMI_LOCATION_SUBSTR = (
    "Corpius Arena",
    "Kraid Arena",
    "Drogyga Arena",
    "Escue Arena",
    "Golzuna Arena",
    "Central Unit Access",
    "Purple EMMI Arena",
    "Orange EMMI Introduction",
    "Yellow EMMI Introduction",
    "Proto EMMI Introduction",
    "Above Z-57 Fight - Pickup (Z-57)",
)

_OPTION_DEFAULTS: Dict[str, int] = {
    "door_lock_rando": 0,
    "transport_rando": 0,
    "nerf_power_bombs": 0,
    "game_goal": 0,
    "include_boss_pickups": 1,
    "start_with_pulse_radar": 1,
    "progressive_beams": 1,
    "progressive_charge": 1,
    "progressive_missiles": 0,
    "progressive_bombs": 1,
    "progressive_suit": 1,
    "progressive_spin": 1,
    "vanilla_flash_shift_behaviour": 1,
    "flash_shift_upgrade_requires_main_item": 1,
    "flash_shift_upgrade_count": 3,
    "flash_shift_included_ammo": 2,
    "flash_shift_upgrade_amount": 1,
    "starting_missiles": 15,
    "starting_power_bombs": 0,
    "energy_per_tank": 100,
    "energy_tanks": 8,
    "energy_parts": 16,
    "missile_tanks": 35,
    "missile_plus_tanks": 10,
    "power_bomb_tanks": 12,
    "immediate_energy_parts": 1,
    "constant_heat_damage": 20,
    "constant_cold_damage": 20,
    "missile_tank_ammo": 2,
    "missile_plus_tank_ammo": 10,
    "power_bomb_tank_ammo": 1,
    "starting_kit_items": 0,
}


class _Opt:
    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = int(value)

    def __bool__(self) -> bool:
        return bool(self.value)

    def __int__(self) -> int:
        return int(self.value)


class _Options:
    def __init__(self, values: Dict[str, int]) -> None:
        self._values = dict(values)

    def __getattr__(self, name: str) -> _Opt:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Opt(self._values.get(name, 0))


class StubWorld:
    player = 1

    def __init__(self, values: Dict[str, int], *, seed: int = 0) -> None:
        _ensure_metroid_bread_importable()
        from worlds.metroid_bread.Locations import location_table
        from worlds.metroid_bread.dread_logic import DreadLogic

        self.options = _Options(values)
        self.random = random.Random(seed)
        self._location_table = location_table
        with contextlib.redirect_stdout(io.StringIO()):
            self.logic = DreadLogic(self)

    def active_location_names(self) -> List[str]:
        names = list(self._location_table.keys())
        if not self.options.include_boss_pickups:
            names = [
                n
                for n in names
                if not any(s in n for s in _BOSS_EMMI_LOCATION_SUBSTR)
            ]
        return names


def _as_int(raw: Any, default: int = 0) -> int:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).strip().lower()
    aliases = {
        "off": 0,
        "vanilla": 0,
        "disabled": 0,
        "false": 0,
        "on": 1,
        "true": 1,
        "randomized": 1,
        "individual_doors": 1,
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
        "expert": 4,
        "ludicrous": 5,
    }
    if text in aliases:
        return aliases[text]
    try:
        return int(text)
    except ValueError:
        return default


def build_option_values(req: Dict[str, Any]) -> Dict[str, int]:
    values = dict(_OPTION_DEFAULTS)
    for key in TRICK_KEYS:
        # Match Options / Hub defaults: Combat Beginner, others Disabled.
        values[key] = 1 if key == "combat_tricks" else 0
    tricks = req.get("tricks") or {}
    if isinstance(tricks, dict):
        for key, raw in tricks.items():
            values[str(key)] = _as_int(raw, 0)
    for key in (
        "door_lock_rando",
        "transport_rando",
        "include_boss_pickups",
        "start_with_pulse_radar",
        "starting_kit_items",
        "progressive_beams",
        "progressive_charge",
        "progressive_missiles",
        "progressive_bombs",
        "progressive_suit",
        "progressive_spin",
        "starting_missiles",
        "starting_power_bombs",
        "energy_per_tank",
        "energy_tanks",
        "energy_parts",
        "missile_tanks",
        "missile_plus_tanks",
        "power_bomb_tanks",
        "immediate_energy_parts",
        "nerf_power_bombs",
        "constant_heat_damage",
        "constant_cold_damage",
        "missile_tank_ammo",
        "missile_plus_tank_ammo",
        "power_bomb_tank_ammo",
    ):
        if key in req:
            raw = req[key]
            if isinstance(raw, bool):
                values[key] = 1 if raw else 0
            else:
                values[key] = _as_int(raw, values.get(key, 0))
    # Nested Metroid Bread block from full YAML dump
    nested = req.get("Metroid Bread") or req.get("options") or {}
    if isinstance(nested, dict):
        for key, raw in nested.items():
            if key in values or key in TRICK_KEYS or key.startswith("progressive_"):
                if isinstance(raw, bool):
                    values[str(key)] = 1 if raw else 0
                else:
                    values[str(key)] = _as_int(raw, values.get(str(key), 0))
    return values


def _ensure_metroid_bread_importable() -> None:
    """
    Register stub worlds / worlds.metroid_bread packages so we can import StartKit
    without executing worlds/__init__.py (which loads every AP world + bsdiff4).
    """
    import types

    # Re-assert ap_core precedence (script-dir / cwd may have been re-inserted).
    _bootstrap_import_path()
    # If world Options.py was already partially imported, drop it so BaseClasses
    # can load AP Options from ap_core.
    opt = sys.modules.get("Options")
    if opt is not None:
        opt_file = str(getattr(opt, "__file__", "") or "").replace("\\", "/")
        if opt_file.endswith("/Options.py") and "/ap_core/" not in opt_file:
            del sys.modules["Options"]
            for key in list(sys.modules):
                if key == "BaseClasses" or key.startswith("BaseClasses."):
                    del sys.modules[key]

    worlds_dir = _ROOT / "worlds"
    mb_dir = _WORLD_DIR
    marker = "_mb_probe_stub"

    worlds_mod = sys.modules.get("worlds")
    if worlds_mod is None or not getattr(worlds_mod, marker, False):
        for key in [k for k in list(sys.modules) if k == "worlds" or k.startswith("worlds.")]:
            del sys.modules[key]
        worlds_mod = types.ModuleType("worlds")
        worlds_mod.__path__ = [str(worlds_dir)]
        worlds_mod.__file__ = str(worlds_dir / "__init__.py")
        worlds_mod.__package__ = "worlds"
        setattr(worlds_mod, marker, True)
        sys.modules["worlds"] = worlds_mod

    pkg = "worlds.metroid_bread"
    if pkg not in sys.modules or not getattr(sys.modules[pkg], marker, False):
        mb_mod = types.ModuleType(pkg)
        mb_mod.__path__ = [str(mb_dir)]
        mb_mod.__file__ = str(mb_dir / "__init__.py")
        mb_mod.__package__ = pkg
        setattr(mb_mod, marker, True)
        sys.modules[pkg] = mb_mod


def _as_option_set(raw: Any, default: Any) -> set:
    """Parse Hub/YAML option-set payloads into a string set."""
    if raw is None:
        return set(default)
    if isinstance(raw, dict):
        out = {str(k) for k, v in raw.items() if v}
        return out or set(default)
    if isinstance(raw, (list, tuple, set, frozenset)):
        out = {str(x) for x in raw if str(x).strip()}
        return out or set(default)
    text = str(raw).strip()
    if not text:
        return set(default)
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                out = {str(x) for x in parsed if str(x).strip()}
                return out or set(default)
        except json.JSONDecodeError:
            pass
    return {s.strip() for s in text.split(",") if s.strip()} or set(default)


def parse_accessibility(req: Dict[str, Any]) -> str:
    """Normalize Hub/YAML accessibility to items|full|minimal."""
    raw = req.get("accessibility")
    nested = req.get("Metroid Bread") or req.get("options") or {}
    if raw is None and isinstance(nested, dict):
        raw = nested.get("accessibility")
    text = str(raw or "items").strip().lower().replace(" ", "_")
    if text in ("full", "minimal", "items"):
        return text
    return "items"


def probe_full_inventory_counts(world: StubWorld) -> Dict[str, int]:
    _ensure_metroid_bread_importable()
    from worlds.metroid_bread.Items import item_table

    counts = {
        name: 12
        for name, data in item_table.items()
        if getattr(data, "id", None) is not None
    }
    counts["Energy Tank"] = int(world.options.energy_tanks)
    counts["Energy Part"] = int(world.options.energy_parts)
    return counts


def probe_uncleared_names(world: StubWorld) -> List[str]:
    """Pickup / event items out of logic with a full inventory.

    For events, one event_item may have several nodes (normal vs glitch
    alternate). Only report the item if *no* providing node is reachable.
    """
    from collections import defaultdict

    _ensure_metroid_bread_importable()
    from worlds.metroid_bread.Events import event_locations

    nodes = world.logic.get_reachable_nodes(
        world.logic.inventory_from_counts(probe_full_inventory_counts(world))
    )
    missing: List[str] = []
    for name in world.active_location_names():
        node = world.logic.pickup_nodes.get(name)
        if node is not None and node not in nodes:
            missing.append(name)
    by_item: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for ev in event_locations:
        by_item[ev.event_item].append((ev.game_region, ev.area, ev.node))
    for item, locs in by_item.items():
        if not any(loc in nodes for loc in locs):
            missing.append(f"event:{item}")
    return missing


def probe_has_uncleared_logic(world: StubWorld) -> bool:
    """True if any AP pickup/event stays out of logic with a full inventory."""
    return bool(probe_uncleared_names(world))


def accessibility_full_conflict(world: StubWorld) -> Dict[str, Any]:
    """
    Error when Accessibility Full cannot keep every check in logic.

    Highlights Accessibility plus the minimum trick raises that would clear
    the missing checks (when tricks alone can fix it).
    """
    from worlds.metroid_bread.start_sphere0_tricks import (
        find_min_tricks_for_full_accessibility,
        format_trick_alt,
    )

    missing = probe_uncleared_names(world)
    n = len(missing)
    entries, solvable = find_min_tricks_for_full_accessibility(
        world, has_uncleared=lambda: probe_has_uncleared_logic(world)
    )
    fields = ["accessibility"]
    fix = "Set Accessibility to Items (generation would downgrade Full anyway)."
    if entries:
        for e in entries:
            key = str(e.get("key") or "")
            if key and key not in fields:
                fields.append(key)
        alt = format_trick_alt(entries)
        fix = f"Enable {alt}, or set Accessibility to Items."
        msg = (
            f"{n} pickup(s)/event(s) stay out of logic with a full inventory "
            f"because required tricks are too low (need {alt}). "
            "Accessibility Full cannot be kept."
        )
    elif not solvable:
        msg = (
            f"{n} pickup(s)/event(s) stay out of logic even with every trick "
            "at Ludicrous. Accessibility Full cannot be kept."
        )
    else:
        msg = (
            f"{n} pickup(s)/event(s) stay out of logic with a full inventory "
            "under these tricks. Accessibility Full cannot be kept."
        )
    return {
        "id": "accessibility_full_blocked",
        "severity": "error",
        "title": "Accessibility Full needs higher tricks",
        "message": msg,
        "fix": fix,
        "fields": fields,
        "trick_alt": entries,
        "missing_count": n,
    }


def apply_door_lock_shuffle(
    world,
    *,
    doors_to_change: Any,
    change_doors_to: Any,
    start_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Apply Individual Doors *pre-fill* (gen-equivalent early graph).

    Classifies docks into fill-assist unlocks + reroute unlocks. Interesting
    lock types are assigned post-fill in generation; the probe only needs the
    opened graph for sphere-0 kit sizing.
    """
    _ensure_metroid_bread_importable()
    from worlds.metroid_bread import DoorRando, DoorRandoAssigner

    if int(getattr(world.options, "door_lock_rando").value) != 1:
        return {
            "applied": False,
            "unlocked": 0,
            "assist": 0,
            "reroute": 0,
            "protected": 0,
        }

    change_from = _as_option_set(doors_to_change, DoorRando.DEFAULT_DOORS_TO_CHANGE)
    change_to = _as_option_set(change_doors_to, DoorRando.DEFAULT_CHANGE_DOORS_TO)
    active = set(world.active_location_names()) if hasattr(world, "active_location_names") else None
    result = DoorRandoAssigner.pre_fill_roll(
        world.logic,
        world.random,
        doors_to_change=change_from,
        change_doors_to=change_to,
        start_counts=start_counts,
        active=active,
    )
    if not result.assignments:
        return {
            "applied": False,
            "unlocked": 0,
            "assist": 0,
            "reroute": 0,
            "protected": len(result.protected_keys),
        }

    DoorRando.apply_assignments(world.logic.parser, result.assignments)
    world.logic.rebuild_graph()
    return {
        "applied": True,
        "unlocked": len(result.assignments),
        "assist": len(result.fill_assist_keys),
        "reroute": len(result.reroute_keys),
        "protected": len(result.protected_keys),
    }


def apply_transport_shuffle(world, *, attempts: int = 40) -> Dict[str, Any]:
    """
    Roll a connected transport matching onto ``world.logic`` (gen-equivalent).

    Returns metadata: matching size / whether the graph was rewritten.
    No-op when transport_rando is off. Mutates the parser graph in place.
    """
    _ensure_metroid_bread_importable()
    from worlds.metroid_bread import TransportRando

    if int(getattr(world.options, "transport_rando").value) != 1:
        return {"applied": False, "pairs": 0, "matching": {}}

    matching, transports = TransportRando.roll_connected_matching(
        world.logic, world.random, mode="randomized", attempts=attempts
    )
    if not matching:
        return {"applied": False, "pairs": 0, "matching": {}}

    TransportRando.apply_matching(world.logic.parser, transports, matching)
    world.logic.rebuild_graph()
    return {
        "applied": True,
        "pairs": len(matching) // 2,
        "matching": dict(matching),
    }


def probe_one_start(world: StubWorld, info) -> Dict[str, Any]:
    _ensure_metroid_bread_importable()
    from worlds.metroid_bread import StartKit

    world.logic.set_starting_node(info.node_id)
    empty_checks = StartKit.start_checks(world, {})
    kit = StartKit.build_start_kit(world, max_kit=StartKit.MAX_START_KIT)
    checks_with_kit = StartKit.start_checks(world, StartKit.kit_counts(kit))
    return {
        "path": info.path,
        "option_key": info.option_key,
        "display_name": info.display_name,
        "is_default": info.is_default,
        "empty_checks": empty_checks,
        "min_kit_size": len(kit),
        "kit": list(kit),
        "checks_with_kit": checks_with_kit,
        "meets_min_checks": checks_with_kit >= StartKit.MIN_START_LOCATIONS,
    }


def evaluate_probe(req: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_metroid_bread_importable()
    from worlds.metroid_bread import StartKit
    from worlds.metroid_bread.starting_locations import (
        get_by_option_key,
        get_default,
        load_starting_locations,
    )
    from worlds.metroid_bread.yaml_option_conflicts import (
        analyze_option_conflicts,
        merge_conflicts_into_result,
    )

    values = build_option_values(req)
    access = parse_accessibility(req)
    conflict_values: Dict[str, Any] = dict(values)
    conflict_values["accessibility"] = access
    conflicts = analyze_option_conflicts(conflict_values)
    seed = _as_int(req.get("seed"), 0)
    budget = max(0, min(StartKit.MAX_START_KIT, values.get("starting_kit_items", 0)))
    start_key = str(req.get("starting_location") or "default").strip()
    doors_on = values.get("door_lock_rando", 0) == 1
    transports_on = values.get("transport_rando", 0) == 1
    # Both door pre-fill unlocks and transport shuffle are simulated below.
    doors_unvalidated = False

    world = StubWorld(values, seed=seed)
    all_starts = load_starting_locations()

    if start_key == "random_save_station":
        frontier_info = get_default()
    elif start_key in ("default", "", "artaria_intro_room_start_point"):
        frontier_info = get_default()
    else:
        frontier_info = get_by_option_key(start_key) or get_default()

    world.logic.set_starting_node(frontier_info.node_id)

    door_meta: Dict[str, Any] = {"applied": False, "unlocked": 0}
    transport_meta: Dict[str, Any] = {"applied": False, "pairs": 0}
    graph_notes: List[str] = []

    if doors_on:
        # Gen: protect frontier, force-unlock fill-assist, unlock ~85% reroute set.
        frontier_kit = StartKit.build_start_kit(world, max_kit=budget)
        door_meta = apply_door_lock_shuffle(
            world,
            doors_to_change=req.get("doors_to_change"),
            change_doors_to=req.get("change_doors_to"),
            start_counts=StartKit.kit_counts(frontier_kit),
        )
        if door_meta.get("applied"):
            graph_notes.append(
                f"Door lock pre-fill: assist={door_meta.get('assist', 0)} "
                f"reroute={door_meta.get('reroute', 0)} "
                f"(unlocked {door_meta['unlocked']} dock(s), seed={seed})."
            )
        else:
            graph_notes.append(
                "Door lock rando is on but no docks were unlocked "
                "(empty eligible set or all protected)."
            )

    if transports_on:
        transport_meta = apply_transport_shuffle(world)
        if transport_meta.get("applied"):
            graph_notes.append(
                f"Transport shuffle applied ({transport_meta['pairs']} pairs, seed={seed})."
            )
        else:
            graph_notes.append(
                "Transport rando is on but no connected shuffle was found; "
                "using vanilla elevators (Teleporters enabled)."
            )

    if access == "full" and probe_has_uncleared_logic(world):
        conflicts = list(conflicts) + [accessibility_full_conflict(world)]

    graph_note = (" " + " ".join(graph_notes)) if graph_notes else ""

    def trick_alt_for(info, alt_budget: int) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        from worlds.metroid_bread.start_sphere0_tricks import (
            find_min_trick_alt,
            format_trick_alt,
        )

        world.logic.set_starting_node(info.node_id)
        alt = find_min_trick_alt(world, alt_budget)
        return alt, format_trick_alt(alt)

    def severity_for(
        row: Dict[str, Any], info=None
    ) -> Tuple[str, str, str, str, str, Optional[List[Dict[str, Any]]]]:
        need = int(row["min_kit_size"])
        meets = bool(row["meets_min_checks"])
        kit = row.get("kit") or []
        path = row["path"]
        if not meets:
            fix = (
                "Pick Default (Artaria Intro) or another save that opens with Morph/Bombs."
            )
            fix_alt = ""
            trick_alt = None
            if info is not None:
                trick_alt, fix_alt = trick_alt_for(info, StartKit.MAX_START_KIT)
            return (
                "error",
                "Starting location can't open sphere 0",
                f"{path} still has only {row['checks_with_kit']} check(s) even with a "
                f"max Start Kit of {StartKit.MAX_START_KIT} (need {StartKit.MIN_START_LOCATIONS}).",
                fix,
                fix_alt,
                trick_alt,
            )
        if budget < need:
            items = ", ".join(kit) if kit else "(none)"
            fix = (
                f"Set Starting Items to at least {need}, or choose Default (Artaria Intro)."
            )
            fix_alt = ""
            trick_alt = None
            if info is not None:
                trick_alt, fix_alt = trick_alt_for(info, budget)
            return (
                "error",
                "Starting Items too low",
                f"{path} needs {need} Starting Item(s) ({items}); Starting Items is {budget}.",
                fix,
                fix_alt,
                trick_alt,
            )
        note = (
            f"{path} opens with {row['empty_checks']} sphere-0 check(s) on empty inventory."
            if need == 0
            else f"{path} needs kit [{', '.join(kit)}]; budget {budget} is enough."
        )
        return (
            "ok",
            "YAML looks good",
            f"Likely to generate successfully. {note}",
            "",
            "",
            None,
        )

    if start_key == "random_save_station":
        rows = [probe_one_start(world, info) for info in all_starts]
        hard = [r for r in rows if not r["meets_min_checks"]]
        under = [r for r in rows if r["meets_min_checks"] and budget < r["min_kit_size"]]
        ok_rows = [r for r in rows if r["meets_min_checks"] and budget >= r["min_kit_size"]]
        fix_alt = ""
        trick_alt = None
        if not ok_rows:
            if hard and len(hard) == len(rows):
                sev, title, msg, fix = (
                    "error",
                    "No random start can open sphere 0",
                    f"All {len(rows)} starts fail even with a max Start Kit under these tricks.",
                    "Use Default (Artaria Intro) or loosen trick settings.",
                )
            else:
                worst = max(under or hard, key=lambda r: r["min_kit_size"])
                need_min = (
                    max(r["min_kit_size"] for r in rows if r["meets_min_checks"])
                    if any(r["meets_min_checks"] for r in rows)
                    else StartKit.MAX_START_KIT
                )
                sev, title, msg, fix = (
                    "error",
                    "Starting Items too low for every viable start",
                    f"{len(under) + len(hard)}/{len(rows)} starts need more than "
                    f"Starting Items={budget} (e.g. {worst['path']} needs {worst['min_kit_size']}).",
                    f"Raise Starting Items to at least {need_min}, or choose Default.",
                )
                worst_info = next(
                    (i for i in all_starts if i.option_key == worst["option_key"]),
                    None,
                )
                if worst_info is not None:
                    trick_alt, fix_alt = trick_alt_for(worst_info, budget)
        elif under:
            examples = ", ".join(r["path"] for r in under[:3])
            need = max(r["min_kit_size"] for r in under)
            sev, title, msg, fix = (
                "warning",
                "Some random starts need more Starting Items",
                f"{len(under)} of {len(rows)} starts need more than Starting Items={budget} "
                f"(e.g. {examples}). Random may still pick a viable start.",
                f"Raise Starting Items to {need} to cover more of the pool, "
                "or keep Default / a specific open start.",
            )
            sample = under[0]
            sample_info = next(
                (i for i in all_starts if i.option_key == sample["option_key"]),
                None,
            )
            if sample_info is not None:
                trick_alt, fix_alt = trick_alt_for(sample_info, budget)
                if fix_alt:
                    fix_alt = f"e.g. for {sample['path']}: {fix_alt}"
        else:
            sev, title, msg, fix = (
                "ok",
                "YAML looks good",
                f"Likely to generate successfully. Random pool: {len(ok_rows)}/{len(rows)} "
                f"starts open with Starting Items={budget}.",
                "",
            )
        if graph_note and sev in ("ok", "warning", "error"):
            msg = msg + graph_note
        return merge_conflicts_into_result(
            {
                "ok": True,
                "severity": sev,
                "title": title,
                "message": msg,
                "fix": fix,
                "fix_alt": fix_alt,
                "trick_alt": trick_alt,
                "doors_unvalidated": doors_unvalidated,
                "door_shuffle": {
                    "enabled": doors_on,
                    "applied": bool(door_meta.get("applied")),
                    "unlocked": int(door_meta.get("unlocked") or 0),
                    "assist": int(door_meta.get("assist") or 0),
                    "reroute": int(door_meta.get("reroute") or 0),
                    "protected": int(door_meta.get("protected") or 0),
                },
                "transport_shuffle": {
                    "enabled": transports_on,
                    "applied": bool(transport_meta.get("applied")),
                    "pairs": int(transport_meta.get("pairs") or 0),
                },
                "starting_location": start_key,
                "starting_kit_items": budget,
                "starts": rows,
            },
            conflicts,
        )

    if start_key in ("default", "", "artaria_intro_room_start_point"):
        info = get_default()
    else:
        info = get_by_option_key(start_key)
        if info is None:
            return merge_conflicts_into_result(
                {
                    "ok": False,
                    "severity": "error",
                    "title": "Unknown starting location",
                    "message": f"No start matches option key {start_key!r}.",
                    "fix": "Pick Default or a listed save station.",
                    "fix_alt": "",
                    "doors_unvalidated": doors_unvalidated,
                    "starting_location": start_key,
                    "starting_kit_items": budget,
                },
                conflicts,
            )

    row = probe_one_start(world, info)
    sev, title, msg, fix, fix_alt, trick_alt = severity_for(row, info)
    if graph_note and sev in ("ok", "warning", "error"):
        msg = msg + graph_note
    if trick_alt:
        row = dict(row)
        row["trick_alt"] = trick_alt
    return merge_conflicts_into_result(
        {
            "ok": True,
            "severity": sev,
            "title": title,
            "message": msg,
            "fix": fix,
            "fix_alt": fix_alt,
            "trick_alt": trick_alt,
            "doors_unvalidated": doors_unvalidated,
            "door_shuffle": {
                "enabled": doors_on,
                "applied": bool(door_meta.get("applied")),
                "unlocked": int(door_meta.get("unlocked") or 0),
                "assist": int(door_meta.get("assist") or 0),
                "reroute": int(door_meta.get("reroute") or 0),
                "protected": int(door_meta.get("protected") or 0),
            },
            "transport_shuffle": {
                "enabled": transports_on,
                "applied": bool(transport_meta.get("applied")),
                "pairs": int(transport_meta.get("pairs") or 0),
            },
            "starting_location": start_key,
            "starting_kit_items": budget,
            "selected": row,
            "starts": [row],
        },
        conflicts,
    )


def main() -> int:
    raw = sys.stdin.read()
    try:
        req = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        json.dump(
            {
                "ok": False,
                "severity": "error",
                "title": "Invalid probe request",
                "message": str(exc),
                "fix": "",
            },
            sys.stdout,
            ensure_ascii=True,
        )
        print()
        return 1
    if not isinstance(req, dict):
        req = {}
    result = evaluate_probe(req)
    # ASCII-only JSON: Hub on Windows often uses a non-UTF8 console encoding;
    # ensure_ascii=False truncated mid-message on UnicodeEncodeError.
    json.dump(result, sys.stdout, ensure_ascii=True)
    print()
    return 0 if result.get("ok", True) or result.get("severity") else 1


if __name__ == "__main__":
    raise SystemExit(main())

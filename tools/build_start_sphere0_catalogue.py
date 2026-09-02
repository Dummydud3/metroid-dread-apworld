#!/usr/bin/env python3
"""
Build logic_database/start_sphere0_catalogue.json

For every RDV valid_starting_location, compute StartKit size / sphere-0 check
counts with door rando off and all tricks disabled.

Usage (from Archipelago repo root):
  py -3.12 worlds/metroid_bread/tools/build_start_sphere0_catalogue.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

WORLD_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = WORLD_DIR / "logic_database" / "start_sphere0_catalogue.json"

# Same set as tools/stress_victory_clearance.py — force every trick to 0.
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

# Match MetroidBreadWorld._BOSS_EMMI_LOCATION_SUBSTR (boss/EMMI filter).
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

# Option defaults used by StartKit / DreadLogic (non-trick). Progressive and
# Flash Shift defaults match Options.py so the kit candidate pool matches gen.
_OPTION_DEFAULTS: Dict[str, int] = {
    "door_lock_rando": 0,
    "transport_rando": 0,
    "nerf_power_bombs": 0,
    "game_goal": 0,  # Defeat Raven Beak — no 100% active-location filter
    "include_boss_pickups": 1,  # DefaultOnToggle
    "start_with_pulse_radar": 1,  # DefaultOnToggle
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
    # Ammo/energy — inventory_from_counts reads these; 0 missiles softlocks intro.
    "starting_missiles": 15,
    "starting_power_bombs": 0,
    "energy_per_tank": 100,
    "missile_tank_ammo": 2,
    "missile_plus_tank_ammo": 10,
    "power_bomb_tank_ammo": 1,
}


class _Opt:
    """Truthy when value is non-zero; exposes .value for DreadLogic / flash_shift."""

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


class _StubWorld:
    """Minimal world for StartKit.build_start_kit / start_checks."""

    player = 1

    def __init__(self, *, seed: int = 0) -> None:
        from worlds.metroid_bread.Locations import location_table
        from worlds.metroid_bread.dread_logic import DreadLogic
        from worlds.metroid_bread import StartKit

        values = dict(_OPTION_DEFAULTS)
        for key in TRICK_KEYS:
            values[key] = 0
        self.options = _Options(values)
        self.random = random.Random(seed)
        self._location_table = location_table
        self._StartKit = StartKit
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


def build_catalogue(*, seed: int = 0) -> Dict[str, Any]:
    # Avoid worlds/__init__.py loading every AP world (bsdiff4, etc.).
    import types

    worlds_dir = ROOT / "worlds"
    if "worlds" not in sys.modules or not getattr(
        sys.modules.get("worlds"), "_mb_probe_stub", False
    ):
        for key in [k for k in list(sys.modules) if k == "worlds" or k.startswith("worlds.")]:
            del sys.modules[key]
        worlds_mod = types.ModuleType("worlds")
        worlds_mod.__path__ = [str(worlds_dir)]
        worlds_mod.__file__ = str(worlds_dir / "__init__.py")
        worlds_mod.__package__ = "worlds"
        worlds_mod._mb_probe_stub = True  # type: ignore[attr-defined]
        sys.modules["worlds"] = worlds_mod
        mb = types.ModuleType("worlds.metroid_bread")
        mb.__path__ = [str(WORLD_DIR)]
        mb.__file__ = str(WORLD_DIR / "__init__.py")
        mb.__package__ = "worlds.metroid_bread"
        mb._mb_probe_stub = True  # type: ignore[attr-defined]
        sys.modules["worlds.metroid_bread"] = mb

    from worlds.metroid_bread import StartKit
    from worlds.metroid_bread.starting_locations import load_starting_locations
    from worlds.metroid_bread.start_sphere0_tricks import find_min_trick_alt

    world = _StubWorld(seed=seed)
    starts_out: List[Dict[str, Any]] = []

    for info in load_starting_locations():
        world.logic.set_starting_node(info.node_id)
        empty_checks = StartKit.start_checks(world, {})
        kit = StartKit.build_start_kit(world)
        checks_with_kit = StartKit.start_checks(world, StartKit.kit_counts(kit))
        meets = checks_with_kit >= StartKit.MIN_START_LOCATIONS
        trick_alt = None
        if meets and len(kit) > 0:
            # Tricks that open sphere 0 with Starting Items = 0 (instead of the kit).
            trick_alt = find_min_trick_alt(world, 0)
        elif not meets:
            trick_alt = find_min_trick_alt(world, StartKit.MAX_START_KIT)
        starts_out.append(
            {
                "path": info.path,
                "option_key": info.option_key,
                "display_name": info.display_name,
                "scenario": info.scenario,
                "actor": info.actor,
                "is_default": info.is_default,
                "empty_checks": empty_checks,
                "min_kit_size": len(kit),
                "kit": list(kit),
                "checks_with_kit": checks_with_kit,
                "meets_min_checks": meets,
                "trick_alt": trick_alt,
            }
        )

    return {
        "schema_version": 2,
        "profile": "doors_off_tricks_disabled",
        "assumptions": {
            "door_lock_rando": "off",
            "transport_rando": "off",
            "tricks": "all_disabled",
            "combat_tricks": "disabled",
            "include_boss_pickups": bool(_OPTION_DEFAULTS["include_boss_pickups"]),
            "game_goal": "defeat_raven_beak",
            "random_seed": seed,
            "progressive_defaults": {
                k: bool(v)
                for k, v in _OPTION_DEFAULTS.items()
                if k.startswith("progressive_")
            },
            "start_with_pulse_radar": bool(
                _OPTION_DEFAULTS["start_with_pulse_radar"]
            ),
            "vanilla_flash_shift_behaviour": bool(
                _OPTION_DEFAULTS["vanilla_flash_shift_behaviour"]
            ),
            "starting_missiles": _OPTION_DEFAULTS["starting_missiles"],
            "energy_per_tank": _OPTION_DEFAULTS["energy_per_tank"],
            "note": (
                "min_kit_size is the fewest StartKit progression items precollected "
                "so sphere 0 has >= min_start_checks reachable active pickups. "
                "Kit choice is greedy and seed-shuffled (see random_seed). "
                "trick_alt is the fewest trick raises (from all-disabled) that open "
                "sphere 0 with Starting Items=0 instead of the kit."
            ),
        },
        "min_start_checks": StartKit.MIN_START_LOCATIONS,
        "max_start_kit": StartKit.MAX_START_KIT,
        "starts": starts_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build start_sphere0_catalogue.json (doors off, tricks disabled)."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for StartKit candidate shuffle (default 0)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_PATH,
        help=f"Output JSON path (default: {OUT_PATH})",
    )
    args = parser.parse_args()

    data = build_catalogue(seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    n = len(data["starts"])
    ok = sum(1 for s in data["starts"] if s["meets_min_checks"])
    cramped = [s for s in data["starts"] if s["empty_checks"] < data["min_start_checks"]]
    print(f"Wrote {args.output}")
    print(f"Starts: {n}; meets_min_checks: {ok}/{n}; empty_checks < floor: {len(cramped)}")
    for s in data["starts"][:3]:
        print(
            f"  {s['path']}: empty={s['empty_checks']} kit={s['min_kit_size']} "
            f"{s['kit']} with_kit={s['checks_with_kit']}"
        )
    intro = next((s for s in data["starts"] if s["is_default"]), None)
    if intro:
        print(
            f"Default Intro: empty={intro['empty_checks']} "
            f"min_kit_size={intro['min_kit_size']} meets={intro['meets_min_checks']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

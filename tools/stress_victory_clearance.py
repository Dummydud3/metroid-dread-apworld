#!/usr/bin/env python3
"""
Stress-test Metroid Bread victory-implies-90% clearance across extreme YAMLs.

Usage (from Archipelago repo root):
  py -3.12 worlds/metroid_bread/tools/stress_victory_clearance.py
  py -3.12 worlds/metroid_bread/tools/stress_victory_clearance.py --count 40 --seed 100
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
import traceback
import warnings
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GAME = "Metroid Bread"
_AP: dict[str, Any] | None = None

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

STARTS = (
    "default",
    "random_save_station",
    "hanubia_navigation_station_save_station",
    "cataris_save_station_east_save_station",
    "dairon_navigation_station_south_save_station",
    "burenia_save_station_north_save_station",
    "ghavoran_save_station_east_save_station",
    "ferenia_save_station_southeast_save_station",
)


def bootstrap() -> dict[str, Any]:
    global _AP
    if _AP is not None:
        return _AP
    from worlds.AutoWorld import AutoWorldRegister, call_all
    from Fill import distribute_items_restrictive
    from test.general import gen_steps, setup_multiworld
    from worlds.metroid_bread import victory_clearance

    if GAME not in AutoWorldRegister.world_types:
        raise RuntimeError(f"{GAME!r} is not registered")
    _AP = {
        "call_all": call_all,
        "distribute_items_restrictive": distribute_items_restrictive,
        "gen_steps": gen_steps,
        "setup_multiworld": setup_multiworld,
        "world_type": AutoWorldRegister.world_types[GAME],
        "victory_clearance": victory_clearance,
    }
    return _AP


def extreme_configs(rng_seed: int) -> list[dict]:
    """Build a deterministic list of outrageous option combos."""
    import random

    rng = random.Random(rng_seed)
    configs: list[dict] = []

    # Explicit softballs / historical problem shapes.
    configs.extend(
        [
            {
                "label": "hanubia_dna0_minimal",
                "required_dna": 0,
                "starting_location": "hanubia_navigation_station_save_station",
                "accessibility": "minimal",
            },
            {
                "label": "hanubia_dna0_items",
                "required_dna": 0,
                "starting_location": "hanubia_navigation_station_save_station",
                "accessibility": "items",
                "transport_rando": "randomized",
            },
            {
                "label": "intro_dna0_doors",
                "required_dna": 0,
                "starting_location": "default",
                "door_lock_rando": "individual_doors",
                "accessibility": "minimal",
                "early_morph_ball": True,
            },
            {
                "label": "dna12_full",
                "required_dna": 12,
                "accessibility": "full",
                "dna_placement": "anywhere",
            },
            {
                "label": "dna1_transport_doors",
                "required_dna": 1,
                "transport_rando": "randomized",
                "door_lock_rando": "individual_doors",
                "accessibility": "items",
            },
        ]
    )

    # Randomized extremes.
    for i in range(45):
        opts: dict[str, Any] = {
            "label": f"extreme_{i}",
            "required_dna": rng.choice([0, 0, 1, 3, 6, 9, 12]),
            "starting_location": rng.choice(STARTS),
            "accessibility": rng.choice(["minimal", "items", "full"]),
            "transport_rando": rng.choice(["off", "randomized", "randomized"]),
            "door_lock_rando": rng.choice(
                ["vanilla", "vanilla", "individual_doors"]
            ),
            "early_morph_ball": rng.choice([False, True, True]),
            "include_boss_pickups": rng.choice([True, True, False]),
            "progressive_beams": rng.choice([False, True]),
            "progressive_charge": rng.choice([False, True]),
            "progressive_missiles": rng.choice([False, True]),
            "progressive_bombs": rng.choice([False, True]),
            "progressive_suit": rng.choice([False, True]),
            "progressive_spin": rng.choice([False, True]),
            "reverse_grapple_block": rng.choice([False, True]),
            "dna_placement": rng.choice(
                ["prefer_emmi", "prefer_bosses", "anywhere"]
            ),
        }
        if rng.random() < 0.35:
            for key in TRICK_KEYS:
                opts[key] = "expert"
            opts["reverse_grapple_block"] = True
            opts["label"] += "_alltricks"
        elif rng.random() < 0.25:
            for key in rng.sample(TRICK_KEYS, k=8):
                opts[key] = rng.choice(["beginner", "intermediate", "advanced", "expert", "ludicrous"])
        configs.append(opts)
    return configs


def run_one(opts: dict, seed: int, quiet: bool) -> tuple[bool, float, str, dict]:
    ap = bootstrap()
    label = opts.get("label", "?")
    option_body = {k: v for k, v in opts.items() if k != "label"}
    t0 = time.perf_counter()
    sink = io.StringIO()
    try:
        ctx = (
            contextlib.redirect_stdout(sink)
            if quiet
            else contextlib.nullcontext()
        )
        with ctx:
            mw = ap["setup_multiworld"](
                ap["world_type"],
                steps=ap["gen_steps"],
                seed=seed,
                options=option_body,
            )
            ap["distribute_items_restrictive"](mw)
            ap["call_all"](mw, "post_fill")
            world = mw.worlds[1]
            vc = ap["victory_clearance"]
            missing = vc.missing_checks_at_victory(world)
            rb_sphere = vc.raven_beak_sphere_index(world)
            clearable = len(vc.clearable_pickup_names(world))
            allowed = vc.allowed_missing_at_victory(clearable)
            if len(missing) > allowed:
                raise RuntimeError(
                    f"clearance violated after post_fill: "
                    f"{len(missing)} missing > {allowed} allowed; "
                    f"e.g. {missing[:8]}"
                )
            # Sphere sanity: RB must appear in a real sphere, not Unreachable.
            if rb_sphere < 0:
                raise RuntimeError("Raven Beak not found in reachable spheres")
        info = {
            "label": label,
            "seed": seed,
            "rb_sphere": rb_sphere,
            "eventual_checks": clearable,
            "accessibility": world.options.accessibility.current_key,
            "start": "/".join(world.logic.starting_node),
            "dna": int(world.options.required_dna.value),
        }
        return True, time.perf_counter() - t0, "", info
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc(limit=6)
        return False, time.perf_counter() - t0, f"{err}\n{tb}", {"label": label, "seed": seed}


def run_with_retries(
    opts: dict, base_seed: int, quiet: bool, retries: int
) -> tuple[bool, float, str, dict]:
    """Retry a few seeds; extreme door/DNA rolls can dead-end a single seed."""
    last_err = ""
    total_dt = 0.0
    for attempt in range(retries):
        seed = base_seed + attempt * 997
        ok, dt, err, info = run_one(opts, seed, quiet=quiet)
        total_dt += dt
        if ok:
            info["attempts"] = attempt + 1
            return True, total_dt, "", info
        last_err = err
    return False, total_dt, last_err, {"label": opts.get("label", "?"), "seed": base_seed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=50, help="Max configs to run")
    parser.add_argument("--seed", type=int, default=1000, help="Base seed")
    parser.add_argument("--config-seed", type=int, default=1, help="Config RNG seed")
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Max seed attempts per config (0 or 1 = single attempt; default 5)",
    )
    parser.add_argument("--quiet", action="store_true", default=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    quiet = not args.verbose

    warnings.filterwarnings("ignore")
    configs = extreme_configs(args.config_seed)[: args.count]
    # retries==0 means first-seed only (one attempt).
    max_attempts = 1 if args.retries <= 0 else args.retries
    print(
        f"Stressing {len(configs)} configs "
        f"(base seed {args.seed}, up to {max_attempts} seed attempt(s) each)..."
    )

    ok = fail = 0
    retried_ok = 0
    failures: list[str] = []
    t_all = time.perf_counter()
    for i, opts in enumerate(configs):
        seed = args.seed + i
        success, dt, err, info = run_with_retries(
            opts, seed, quiet=quiet, retries=max_attempts
        )
        if success:
            ok += 1
            attempts = info.get("attempts", 1)
            if attempts > 1:
                retried_ok += 1
            print(
                f"[{i+1}/{len(configs)}] PASS {info['label']} "
                f"seed={info['seed']} rb_sphere={info['rb_sphere']} "
                f"checks={info['eventual_checks']} "
                f"attempts={attempts} ({dt:.1f}s)"
            )
        else:
            fail += 1
            failures.append(f"{opts.get('label')} seed={seed}: {err.splitlines()[0]}")
            print(f"[{i+1}/{len(configs)}] FAIL {opts.get('label')} seed={seed} ({dt:.1f}s)")
            print(f"  {err.splitlines()[0]}")

    elapsed = time.perf_counter() - t_all
    print()
    print(
        f"Done in {elapsed:.1f}s: {ok} passed ({retried_ok} needed seed retry), "
        f"{fail} failed / {len(configs)}"
    )
    if failures:
        print("Failures:")
        for line in failures:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Sweep Metroid Dread on/off generation options (solo) and log pass/fail.

Tests the 11 binary options that change seed generation (excludes
start_with_pulse_radar and cosmetics). Uses in-process AP generation through
fill + accessibility — does not write .zip / spoiler output.

Usage (from Archipelago repo root):
  py -3.11 worlds/metroid_dread/tools/gen_combo_bot.py
  py -3.11 worlds/metroid_dread/tools/gen_combo_bot.py --limit 8 --seed 1
  py -3.11 worlds/metroid_dread/tools/gen_combo_bot.py --resume
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import logging
import sys
import time
import traceback
import warnings
from itertools import product
from pathlib import Path
from typing import Any


# Repo root (…/Archipelago-main)
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GAME = "Metroid Dread"

# Cached after bootstrap (Fill must NOT be imported before worlds finish loading).
_AP: dict[str, Any] | None = None
_QUIET = False

# Binary axes that change generation (pulse radar intentionally omitted).
TOGGLE_KEYS = (
    "include_boss_pickups",
    "early_morph_ball",
    "progressive_beams",
    "progressive_charge",
    "progressive_missiles",
    "progressive_bombs",
    "progressive_suit",
    "progressive_spin",
    "reverse_grapple_block",
)

# Two-state Choices treated as on/off.
CHOICE_KEYS = (
    ("door_lock_rando", ("vanilla", "individual_doors")),
    ("transport_rando", ("off", "randomized")),
)

DEFAULT_FIXED = {
    "start_with_pulse_radar": False,
    "required_dna": 0,
    "dna_placement": "prefer_emmi",
    "accessibility": "full",
    "death_link": False,
}


def all_combos() -> list[dict]:
    """Return every on/off generation combination as option dicts."""
    choice_names = [name for name, _ in CHOICE_KEYS]
    choice_values = [vals for _, vals in CHOICE_KEYS]
    combos: list[dict] = []
    for toggle_bits in product((False, True), repeat=len(TOGGLE_KEYS)):
        for choice_pick in product(*choice_values):
            opts = dict(DEFAULT_FIXED)
            for key, val in zip(TOGGLE_KEYS, toggle_bits):
                opts[key] = val
            for key, val in zip(choice_names, choice_pick):
                opts[key] = val
            combos.append(opts)
    return combos


def combo_id(opts: dict) -> str:
    parts = []
    for key in TOGGLE_KEYS:
        parts.append(f"{key}={'1' if opts[key] else '0'}")
    for key, _ in CHOICE_KEYS:
        parts.append(f"{key}={opts[key]}")
    return "|".join(parts)


def bootstrap_ap() -> dict[str, Any]:
    """
    Load worlds before Fill.

    Importing Fill first causes circular imports (alttp/oot/etc. import Fill while
    Fill is still initializing), which spams ERROR:root and can leave worlds unloaded.
    """
    global _AP
    if _AP is not None:
        return _AP

    # Worlds first — this triggers world package loading safely.
    from worlds.AutoWorld import AutoWorldRegister, call_all  # noqa: WPS433
    if GAME not in AutoWorldRegister.world_types:
        raise RuntimeError(f"{GAME!r} is not registered. Is worlds/metroid_dread present?")

    # Now Fill is safe to import.
    from Fill import distribute_items_restrictive  # noqa: WPS433
    from test.general import gen_steps, setup_multiworld  # noqa: WPS433

    _AP = {
        "AutoWorldRegister": AutoWorldRegister,
        "call_all": call_all,
        "distribute_items_restrictive": distribute_items_restrictive,
        "gen_steps": gen_steps,
        "setup_multiworld": setup_multiworld,
        "world_type": AutoWorldRegister.world_types[GAME],
    }
    return _AP


@contextlib.contextmanager
def _maybe_quiet():
    if not _QUIET:
        yield
        return
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        yield


def run_one(opts: dict, seed: int) -> tuple[bool, float, str]:
    """Generate + fill a solo Dread multiworld. Returns (ok, seconds, error)."""
    ap = bootstrap_ap()
    t0 = time.perf_counter()
    try:
        with _maybe_quiet():
            mw = ap["setup_multiworld"](
                ap["world_type"], steps=ap["gen_steps"], seed=seed, options=opts
            )
            ap["distribute_items_restrictive"](mw)
            ap["call_all"](mw, "post_fill")
            if not mw.fulfills_accessibility():
                raise RuntimeError("fulfills_accessibility() returned False")
        return True, time.perf_counter() - t0, ""
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc(limit=8)
        return False, time.perf_counter() - t0, f"{err}\n{tb}"


def load_done_indices(path: Path) -> set[int]:
    done: set[int] = set()
    if not path.is_file():
        return done
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                done.add(int(row["index"]))
            except (KeyError, ValueError):
                continue
    return done


def append_csv(path: Path, fieldnames: list[str], row: dict) -> None:
    new_file = not path.is_file()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=1, help="Fixed seed for every combo (default: 1)")
    parser.add_argument("--start", type=int, default=0, help="Start combo index (inclusive)")
    parser.add_argument("--limit", type=int, default=0, help="Max combos to run (0 = all remaining)")
    parser.add_argument("--resume", action="store_true", help="Skip indices already in success/fail CSVs")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "logs" / "dread_gen_combo",
        help="Directory for success/fail logs",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Exit after the first failure",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress Archipelago/world INFO logs (keep bot progress lines)",
    )
    args = parser.parse_args(argv)

    global _QUIET
    _QUIET = bool(args.quiet)
    if args.quiet:
        logging.disable(logging.CRITICAL)
        warnings.filterwarnings("ignore")

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    success_path = out_dir / "successes.csv"
    fail_path = out_dir / "failures.csv"
    detail_fail_path = out_dir / "failures_detail.txt"
    summary_path = out_dir / "summary.json"
    progress_path = out_dir / "progress.jsonl"

    combos = all_combos()
    total = len(combos)
    print(f"Total generation on/off combos: {total}")
    print(f"Axes: {list(TOGGLE_KEYS) + [k for k, _ in CHOICE_KEYS]}")
    print(f"Seed={args.seed}  out={out_dir}")

    done: set[int] = set()
    if args.resume:
        done |= load_done_indices(success_path)
        done |= load_done_indices(fail_path)
        print(f"Resume: {len(done)} already logged")

    # Warm imports / RDV load once before the loop timing.
    print("Warming Archipelago + Metroid Dread world…")
    print("(first import loads all worlds — wait for Warm gen line)")
    bootstrap_ap()
    warm_ok, warm_s, warm_err = run_one(dict(DEFAULT_FIXED, **{
        "include_boss_pickups": True,
        "early_morph_ball": False,
        "progressive_beams": True,
        "progressive_charge": True,
        "progressive_missiles": False,
        "progressive_bombs": True,
        "progressive_suit": True,
        "progressive_spin": True,
        "reverse_grapple_block": False,
        "door_lock_rando": "vanilla",
        "transport_rando": "off",
    }), args.seed)
    print(f"Warm gen: {'OK' if warm_ok else 'FAIL'} in {warm_s:.2f}s")
    if not warm_ok:
        print(warm_err)
        return 2

    fieldnames = [
        "index", "seed", "ok", "elapsed_s", "error_short",
        *TOGGLE_KEYS, *(k for k, _ in CHOICE_KEYS), "combo_id",
    ]

    ok_count = 0
    fail_count = 0
    ran = 0
    t_all = time.perf_counter()

    end = total if args.limit <= 0 else min(total, args.start + args.limit)
    for index in range(args.start, end):
        if index in done:
            continue
        opts = combos[index]
        ok, elapsed, err = run_one(opts, args.seed)
        ran += 1
        if ok:
            ok_count += 1
        else:
            fail_count += 1

        short_err = err.splitlines()[0] if err else ""
        row = {
            "index": index,
            "seed": args.seed,
            "ok": int(ok),
            "elapsed_s": f"{elapsed:.3f}",
            "error_short": short_err[:300],
            "combo_id": combo_id(opts),
            **{k: int(bool(opts[k])) for k in TOGGLE_KEYS},
            **{k: opts[k] for k, _ in CHOICE_KEYS},
        }
        append_csv(success_path if ok else fail_path, fieldnames, row)

        if not ok:
            with detail_fail_path.open("a", encoding="utf-8") as df:
                df.write(f"\n===== index={index} seed={args.seed} =====\n")
                df.write(combo_id(opts) + "\n")
                df.write(err + "\n")

        progress = {
            "index": index,
            "ok": ok,
            "elapsed_s": round(elapsed, 3),
            "ran": ran,
            "ok_count": ok_count,
            "fail_count": fail_count,
            "combo_id": combo_id(opts),
        }
        with progress_path.open("a", encoding="utf-8") as pf:
            pf.write(json.dumps(progress) + "\n")

        status = "OK" if ok else "FAIL"
        print(f"[{index + 1}/{total}] {status} {elapsed:.2f}s  {combo_id(opts)}")
        if not ok and args.stop_on_fail:
            print("Stopping on first failure (--stop-on-fail).")
            break

    summary = {
        "game": GAME,
        "players": 1,
        "seed": args.seed,
        "total_combos": total,
        "ran_this_session": ran,
        "ok_this_session": ok_count,
        "fail_this_session": fail_count,
        "elapsed_session_s": round(time.perf_counter() - t_all, 2),
        "toggle_keys": list(TOGGLE_KEYS),
        "choice_keys": {k: list(v) for k, v in CHOICE_KEYS},
        "fixed": DEFAULT_FIXED,
        "out_dir": str(out_dir),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

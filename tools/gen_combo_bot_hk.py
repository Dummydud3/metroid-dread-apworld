#!/usr/bin/env python3
"""
Sweep Metroid Dread on/off generation options in a 2-player multiworld
(Metroid Dread + Hollow Knight) and log pass/fail.

Same 11 Dread axes as gen_combo_bot.py. Hollow Knight options stay fixed
at safe defaults. Solo-only cosmetics / pulse radar are not swept.

Usage (from Archipelago repo root):
  py -3.11 worlds/metroid_dread/tools/gen_combo_bot_hk.py --quiet
  py -3.11 worlds/metroid_dread/tools/gen_combo_bot_hk.py --quiet --resume
  py -3.11 worlds/metroid_dread/tools/gen_combo_bot_hk.py --limit 4 --seed 1
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
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parents[3]  # …/Archipelago-main
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse solo-bot combo definitions / helpers.
from gen_combo_bot import (  # noqa: E402
    CHOICE_KEYS,
    DEFAULT_FIXED,
    TOGGLE_KEYS,
    all_combos,
    append_csv,
    combo_id,
    load_done_indices,
)

DREAD_GAME = "Metroid Dread"
HK_GAME = "Hollow Knight"

_AP: dict[str, Any] | None = None
_QUIET = False

# Fixed Hollow Knight options (rest use world defaults).
HK_FIXED = {
    "accessibility": "items",
    "DeathLink": False,
    "StartLocation": "king's_pass",
    "Goal": "hollowknight",
    "WhitePalace": "exclude",
}


def bootstrap_ap() -> dict[str, Any]:
    """Load worlds before Fill (avoids circular-import world-load failures)."""
    global _AP
    if _AP is not None:
        return _AP

    from worlds.AutoWorld import AutoWorldRegister, call_all  # noqa: WPS433

    for game in (DREAD_GAME, HK_GAME):
        if game not in AutoWorldRegister.world_types:
            raise RuntimeError(f"{game!r} is not registered")

    from Fill import distribute_items_restrictive  # noqa: WPS433
    from test.general import gen_steps, setup_multiworld  # noqa: WPS433

    types = AutoWorldRegister.world_types
    _AP = {
        "call_all": call_all,
        "distribute_items_restrictive": distribute_items_restrictive,
        "gen_steps": gen_steps,
        "setup_multiworld": setup_multiworld,
        "dread_type": types[DREAD_GAME],
        "hk_type": types[HK_GAME],
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


def run_one(dread_opts: dict, seed: int) -> tuple[bool, float, str]:
    """Generate + fill Dread+HK multiworld. Returns (ok, seconds, error)."""
    ap = bootstrap_ap()
    t0 = time.perf_counter()
    try:
        with _maybe_quiet():
            mw = ap["setup_multiworld"](
                [ap["dread_type"], ap["hk_type"]],
                steps=ap["gen_steps"],
                seed=seed,
                options=[dread_opts, dict(HK_FIXED)],
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=1, help="Fixed seed for every combo (default: 1)")
    parser.add_argument("--start", type=int, default=0, help="Start combo index (inclusive)")
    parser.add_argument("--limit", type=int, default=0, help="Max combos to run (0 = all remaining)")
    parser.add_argument("--resume", action="store_true", help="Skip indices already in success/fail CSVs")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "logs" / "dread_hk_gen_combo",
        help="Directory for success/fail logs",
    )
    parser.add_argument("--stop-on-fail", action="store_true", help="Exit after the first failure")
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
    print(f"Total Dread generation on/off combos: {total}")
    print(f"Players: 1={DREAD_GAME}, 2={HK_GAME}")
    print(f"Axes: {list(TOGGLE_KEYS) + [k for k, _ in CHOICE_KEYS]}")
    print(f"Seed={args.seed}  out={out_dir}")

    done: set[int] = set()
    if args.resume:
        done |= load_done_indices(success_path)
        done |= load_done_indices(fail_path)
        print(f"Resume: {len(done)} already logged")

    print("Warming Archipelago + Dread + Hollow Knight…")
    print("(first import loads all worlds — wait for Warm gen line)")
    bootstrap_ap()
    warm_opts = dict(DEFAULT_FIXED, **{
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
    })
    warm_ok, warm_s, warm_err = run_one(warm_opts, args.seed)
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

        with progress_path.open("a", encoding="utf-8") as pf:
            pf.write(json.dumps({
                "index": index,
                "ok": ok,
                "elapsed_s": round(elapsed, 3),
                "ran": ran,
                "ok_count": ok_count,
                "fail_count": fail_count,
                "combo_id": combo_id(opts),
            }) + "\n")

        status = "OK" if ok else "FAIL"
        print(f"[{index + 1}/{total}] {status} {elapsed:.2f}s  {combo_id(opts)}")
        if not ok and args.stop_on_fail:
            print("Stopping on first failure (--stop-on-fail).")
            break

    summary = {
        "games": [DREAD_GAME, HK_GAME],
        "players": 2,
        "seed": args.seed,
        "total_combos": total,
        "ran_this_session": ran,
        "ok_this_session": ok_count,
        "fail_this_session": fail_count,
        "elapsed_session_s": round(time.perf_counter() - t_all, 2),
        "toggle_keys": list(TOGGLE_KEYS),
        "choice_keys": {k: list(v) for k, v in CHOICE_KEYS},
        "dread_fixed": DEFAULT_FIXED,
        "hk_fixed": HK_FIXED,
        "out_dir": str(out_dir),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

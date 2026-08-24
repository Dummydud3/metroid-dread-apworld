#!/usr/bin/env python3
"""
Archipelago Metroid Bread — Direct Patcher (bypasses Randovania Export UI)

## How Randovania does it
1. Load .rdvgame → LayoutDescription (presets + game_modifications)
2. DreadPatchDataFactory.create_game_specific_data()
   builds a patcher.json-shaped dict (pickups, starting_*, enable_remote_lua, …)
3. DreadGameExporter._do_export_game()
   → open_dread_rando.patch_with_status_update(base_rom, ryujinx_mod, patch_data)

## How we do it
1. Parse Archipelago spoiler (our placements + foreign item names)
2. Build the same patcher.json via ap_to_patcher.create_patcher_json()
   (always enable_remote_lua=true for TCP :6969)
3. Call open_dread_rando the same way Randovania does
4. Copy patcher.json + map_icon_keys.json + randomizer_powerup.lua + reachable
   minimap data into the mod
5. finalize_mod() brands credits.txt (Metroid Bread + Archipelago Implementation /
   Dummydude before Major Item Locations), strips leftover HK autosave bootstrap,
   installs ApWarp hotkeys, hardcodes ODR death-counter DNA-slot HUD coords
   (Ryujinx-safe), then ships reachable-map data into RomFS
6. Save-file dim reveal is OFF by default (reveal_minimap_save: false).
   Bright paint uses VisitBoundsSafe in-game; the offline tool remains under tools/.
7. map_icon_keys.json maps pickup_index / location_id / actor → MAP_ICON_ItemCustom{n}
   (ODR assignment order) for Phase 2 collected labels.

No Randovania GUI / game-session export required.

ApWarp hotkeys (location-independent warps)
-------------------------------------------
  finalize_mod() installs dread_scripts/ap_warp.lua (TOC + system.pkg) and patches
  system/scripts/scenario.lc to DoFile + ApWarp.Install(). Tracks last save station
  vs last scripted checkpoint. Close pause/options while holding ZL → last checkpoint;
  hold ZR → last save. Fallback: ZL+DPAD_LEFT / ZR+DPAD_RIGHT.

  Any prior -- AP_HK_AUTOSAVE / ProgressKeeper bootstrap is stripped on every patch
  (that path was wiping inventory on load).

Loading tips on Continue / New Game
-----------------------------------
  finalize_mod() installs dread_scripts/ap_loading_tips.lua (TOC + system.pkg) and
  patches system/scripts/init.lc to DoFile + ApLoadingTips.Install(). With OdrTip
  subsdk9, Install wraps LoadGame / OnLoadScenarioRequest / StartPrologue /
  LoadProfile to call Game.SetForcedTooltip only (no ShowLoadingScreen thrash).
  SetLoadingMode trampoline re-applies LOADING+0x68.

  Experiment (default ON): ap_to_patcher + finalize_mod also rewrite BTXT for the
  AP context-4 carousel (TIP_000–TIP_004) via ODR text_patches / live romfs
  when OdrTip forces context class 4. Titles become "AP POOL4 0"…"AP POOL4 4".
  Disable with METROID_BREAD_CAROUSEL_TIP_PATCHES=0 then re-patch (or re-run finalize).

Reachable minimap (AP logic → bright map)
-----------------------------------------
  finalize_mod() installs bounds-only reachable_map_cells.lua the ODR way:
    → romfs/system/scripts/ap_reachable_map_cells.{lua,lc}
    → TOC + packs/system/system.pkg (+ replacements.json)
  Loose romfs copy alone is NOT enough — Game.DoFile resolves via TOC/.lc
  like death_counter.lua. Bootstrap DoFile loads bounds; client pushes
  RL.ApplyReachableMap. Real full-room paint uses exlaunch
  OdrMap.VisitBoundsSafe (legacy VisitBounds stays crash-guarded; see
  docs/odrmap_exlaunch_binder.md). enable_remote_lua stays true.
  Dim force-save / RevealDimLayout are disabled; bright = VisitBoundsSafe
  + optional fillmaps + physical walk OR.

  Acceptance (manual):
  1. Start + AP-reachable bright via VisitBoundsSafe (current scenario)
  2. Item receive opens areas → brighten without walking
  3. Reload → recompute from current inventory
  4. Walk into unreachable → brightens (physical OR; no revert)
  5. HUD matches pause map (same visit bits)
  6. /map_smoke and /map_smoke_bounds for bright smoke tests
  7. /map_icon_smoke [actor] for ForceEntityIconVisible (map icon pop-out)
  8. /map_unlock_region [scenario] probes AreaBox world-map unlock (OdrMap.UnlockWorldRegion)
  9. Collect item → map inspector shows "{Item} (Collected)"; die/reload restores labels

Usage
-----
  py -3.11 dread_direct_patch.py --spoiler path\\to\\*_Spoiler.txt --player DreadPlayer
  py -3.11 dread_direct_patch.py --seed-folder output\\AP_... --player DreadPlayer

Config (optional): dread_direct_patch_config.json next to this script.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import dread_paths

dread_paths.ensure_import_paths()

# WORLD_DIR: client/patcher scripts + data. AP_ROOT: Archipelago / portable root.
ROOT = dread_paths.WORLD_DIR
AP_ROOT = dread_paths.AP_ROOT
DEFAULT_CONFIG = ROOT / "dread_direct_patch_config.json"
DEFAULT_TEMPLATE = ROOT / "sample_patcher_WORKING.json"
DEFAULT_RYUJINX_MOD = Path(
    os.path.expandvars(r"%APPDATA%\Ryujinx\mods\contents\010093801237c000")
)
DEFAULT_BASE_ROM = Path(r"C:\Users\dummy\Downloads\md rando")
# This is the exlaunch project's Makefile `OUT` directory (see OUT in
# open-dread-rando-exlaunch/Makefile) -- i.e. every `./exlaunch.sh build`
# (misc/scripts/post-build.sh) writes the freshly built subsdk9 + main.npdm
# directly here. Because that build output folder IS this patcher's
# custom_exlaunch_deploy source, a new exlaunch build/deploy is picked up on
# the very next direct-patch run with no separate "install into the patcher"
# copy step. Keep this in sync with dread_direct_patch_config.json's
# "custom_exlaunch_deploy" key; verify with
# open-dread-rando-exlaunch/tools/_verify_patcher_sync.sh.
DEFAULT_CUSTOM_EXLAUNCH_DEPLOY = Path(
    r"C:\Users\dummy\Downloads\open-dread-rando-exlaunch"
    r"\src\open_dread_rando_exlaunch\deploy"
)
REVEAL_MINIMAP_SAVE_TOOL = dread_paths.tools_file("dread_reveal_minimap_save.py")


class PatchError(Exception):
    pass


def log(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def load_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "base_rom_path": str(DEFAULT_BASE_ROM),
        "output_path": str(DEFAULT_RYUJINX_MOD),
        "player_name": "DreadPlayer",
        "clean_output": False,
        "freesink": False,
        # Prefer world-relative deploy (apworld / Hub runtime). Absolute local
        # exlaunch OUT remains a last-resort candidate in resolve_custom_exlaunch_deploy.
        "custom_exlaunch_deploy": str(dread_paths.BUNDLED_EXLAUNCH_DEPLOY).replace("\\", "/"),
        # Offline samus.bmssv dim reveal — OFF (bright path is VisitBoundsSafe in-game).
        "reveal_minimap_save": False,
    }
    cfg.update(dread_paths.load_patch_config(ROOT))
    return cfg


def config_path(cfg: Dict[str, Any], key: str, fallback: Path) -> Path:
    """Config path that may be absolute, %VAR%-based, or relative to this folder."""
    return dread_paths.resolve_path(cfg.get(key), ROOT) or fallback


def _load_reveal_minimap_save_module():
    """Import tools/dread_reveal_minimap_save.py without requiring a package."""
    path = REVEAL_MINIMAP_SAVE_TOOL
    if not path.is_file():
        raise FileNotFoundError(f"missing save reveal tool: {path}")
    name = "dread_reveal_minimap_save"
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "reveal_minimap_auto", None):
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    # dataclasses need the module registered before exec_module
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def maybe_reveal_minimap_save(*, enabled: bool = False) -> None:
    """
    Optionally reveal minimap fog in the newest Ryujinx profile save.

    Default OFF — reachable bright paint uses VisitBoundsSafe in-game.
    Non-fatal when enabled: missing save, locked file, Ryujinx running, or
    tool errors only log [WARN] and never fail the patch.
    """
    if not enabled:
        log("[INFO] reveal_minimap_save disabled — skipping save fog reveal")
        return

    try:
        mod = _load_reveal_minimap_save_module()
        result = mod.reveal_minimap_auto(
            state="dim",
            keep_visited=True,
            fill_gaps=True,
            # Engine-max rows on scenarios already in the save only.
            # create_missing/section cloning is unsafe (crashes load).
            full_rows=mod.DEFAULT_FULL_ROWS,  # 0:299
            scenarios=None,
            create_missing=False,
            also_journal=True,
            skip_if_ryujinx_running=True,
        )
    except Exception as e:
        log(f"[WARN] skipped save minimap reveal: {e}")
        return

    if result.skipped or not result.ok:
        log(f"[WARN] skipped save minimap reveal: {result.message}")
        return

    for line in result.reports:
        log(f"  {line}")
    log(f"[OK] revealed minimap in save {result.message}")


def resolve_custom_exlaunch_deploy(cfg: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """Prefer config path, else the bundled deploy, else the local OdrMap build."""
    candidates: list[Path] = []
    if cfg and cfg.get("custom_exlaunch_deploy"):
        configured = dread_paths.resolve_path(cfg["custom_exlaunch_deploy"], ROOT)
        if configured is not None:
            candidates.append(configured)
    bundled = dread_paths.bundled_exlaunch_deploy(ROOT)
    if bundled is not None:
        candidates.append(bundled)
    candidates.append(DEFAULT_CUSTOM_EXLAUNCH_DEPLOY)
    seen: set[Path] = set()
    for p in candidates:
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key in seen:
            continue
        seen.add(key)
        if (p / "subsdk9").is_file():
            return p
    return None


def install_custom_exlaunch(exefs: Path, deploy: Optional[Path]) -> None:
    """
    Re-install custom OdrMap exlaunch over stock ODR exefs after patching.

    open-dread-rando always writes its stock subsdk9; without this step the
    custom VisitBounds / OdrMap binders are lost. Missing deploy is non-fatal
    (stock remote lua still works).

    Uses shutil.copy2 so the destination Explorer/mtime matches the *source*
    binary's build time (not "now"). A week-old date after a successful patch
    usually means the bundled/custom source itself is that old — check the
    [OK] log line (source path + size), not the file date alone.
    Stock open-dread-rando subsdk9 is ~191054 bytes; custom OdrMap is larger.
    """
    if deploy is None:
        log(
            "[WARN] custom OdrMap exlaunch deploy not found — keeping stock ODR "
            "subsdk9 (~191054 bytes). Hub/apworld needs worlds/.../exlaunch/deploy/"
            "subsdk9, or set custom_exlaunch_deploy in dread_direct_patch_config.json"
        )
        return

    src_sub = deploy / "subsdk9"
    if not src_sub.is_file():
        log(f"[WARN] custom exlaunch missing subsdk9 at {deploy} — keeping stock")
        return

    exefs.mkdir(parents=True, exist_ok=True)
    dst_sub = exefs / "subsdk9"
    src_stat = src_sub.stat()
    src_mtime = datetime.fromtimestamp(src_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    shutil.copy2(src_sub, dst_sub)
    size = dst_sub.stat().st_size
    log(
        f"[OK] installed custom OdrMap subsdk9 ({size} bytes) from {src_sub} "
        f"(source mtime {src_mtime}; Explorer date follows source via copy2)"
    )
    if size <= 200_000:
        log(
            "[WARN] installed subsdk9 looks stock-sized "
            f"({size} bytes; custom OdrMap is typically >210KB) — map binders may be missing"
        )

    src_npdm = deploy / "main.npdm"
    if src_npdm.is_file():
        shutil.copy2(src_npdm, exefs / "main.npdm")
        log(f"[OK] installed custom main.npdm from {deploy}")
    else:
        log(f"[INFO] no main.npdm in {deploy} — left ODR/existing npdm as-is")


def save_config(cfg: Dict[str, Any]) -> None:
    with open(DEFAULT_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    log(f"[OK] Wrote config: {DEFAULT_CONFIG}")


def find_spoiler(seed_folder: Path) -> Path:
    matches = sorted(
        seed_folder.rglob("*_Spoiler.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise PatchError(f"No *_Spoiler.txt under {seed_folder}")
    log(f"[INFO] Using newest spoiler: {matches[0]}")
    return matches[0]


def find_python_with_odr() -> list[str]:
    """Prefer an interpreter that has open-dread-rando installed."""
    candidates = []
    if sys.platform == "win32":
        for minor in (11, 12, 13, 10):
            candidates.append(["py", f"-3.{minor}"])
        candidates.append(["py", "-3"])
    candidates.append([sys.executable])
    candidates.append(["python"])

    for cmd in candidates:
        try:
            r = subprocess.run(
                cmd + ["-c", "import open_dread_rando; print('ok')"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0 and "ok" in (r.stdout or ""):
                return cmd
        except (OSError, subprocess.TimeoutExpired):
            continue

    raise PatchError(
        "open-dread-rando is not installed for any Python on PATH.\n"
        "Install with:  py -3.11 -m pip install open-dread-rando\n"
        "Then re-run this patcher with that same Python."
    )


def build_patcher_json(
    spoiler: Path,
    player: str,
    template: Path,
    *,
    layout_uuid: Optional[str] = None,
) -> dict:
    # Ensure imports resolve (world package + Archipelago root)
    dread_paths.ensure_import_paths()

    from ap_to_patcher import create_patcher_json

    if not template.is_file():
        raise PatchError(f"Missing template patcher JSON:\n  {template}")

    with open(template, encoding="utf-8") as f:
        template_data = json.load(f)

    return create_patcher_json(
        spoiler, player, template_data, layout_uuid=layout_uuid
    )


def ensure_remote_lua(
    patcher_data: dict,
    *,
    seed_id: Optional[str] = None,
    spoiler_path: Optional[Path] = None,
) -> None:
    """Enable remote Lua and set the Metroid Bread AP title screen string."""
    patcher_data["enable_remote_lua"] = True
    patcher_data["mod_compatibility"] = patcher_data.get("mod_compatibility") or "ryujinx"
    patcher_data["mod_category"] = patcher_data.get("mod_category") or "romfs"
    from ap_to_patcher import apply_company_title_screen

    title = apply_company_title_screen(
        patcher_data, seed_id=seed_id, spoiler_path=spoiler_path
    )
    log(f"[OK] Title screen: {title.replace(chr(10), ' / ')}")


def apply_freesink(patcher_data: dict, enabled: bool) -> None:
    """
    Randovania freesink → cosmetic_patches.config.SubAreaManager.bKillPlayerOutsideScenario.
    When freesink is ON, out-of-bounds kills are disabled (bKillPlayerOutsideScenario=false).
    """
    cosmetic = patcher_data.setdefault("cosmetic_patches", {})
    if not isinstance(cosmetic, dict):
        cosmetic = {}
        patcher_data["cosmetic_patches"] = cosmetic
    config = cosmetic.setdefault("config", {})
    if not isinstance(config, dict):
        config = {}
        cosmetic["config"] = config
    sub = config.setdefault("SubAreaManager", {})
    if not isinstance(sub, dict):
        sub = {}
        config["SubAreaManager"] = sub
    sub["bKillPlayerOutsideScenario"] = not bool(enabled)
    log(
        f"[OK] Freesink={'ON' if enabled else 'OFF'} "
        f"(bKillPlayerOutsideScenario={sub['bKillPlayerOutsideScenario']})"
    )


def _format_odr_validation_error(err: str, *, head: int = 1800, tail: int = 500) -> str:
    """Keep the jsonschema *message* visible when the dump is enormous.

    Root ``additionalProperties`` failures embed the entire schema + instance
    (hundreds of KB). Truncating with ``err[-2000:]`` only showed door_patches
    tails and hid the real reason (e.g. unexpected ``has_flash_upgrades``).
    """
    err = (err or "").strip()
    if not err:
        return "(no error output)"
    if len(err) <= head + tail + 40:
        return err
    return f"{err[:head]}\n\n...[truncated {len(err) - head - tail} chars]...\n\n{err[-tail:]}"


def validate_patcher_json(patcher_data: dict) -> None:
    """Fail fast with a clear error if open-dread-rando would reject the JSON.

    Validates against ``files/schema.json`` only — do **not** import
    ``open_dread_rando.dread_patcher`` here. That module pulls cosmetic →
    misc_patches; a broken/partial pip install then fails with
    ``ModuleNotFoundError: misc_patches`` even though the JSON is fine.
    """
    schema = None
    try:
        import open_dread_rando

        schema_path = (
            Path(open_dread_rando.__file__).resolve().parent / "files" / "schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except ModuleNotFoundError as exc:
        name = str(exc)
        if "open_dread_rando" in name or "misc_patches" in name:
            raise PatchError(_broken_odr_install_message(exc)) from exc
        log(f"[WARN] open_dread_rando not importable ({exc}); schema check deferred")
        return
    except Exception as exc:
        log(f"[WARN] could not load ODR schema.json ({exc}); schema check deferred")
        return

    try:
        from open_dread_rando.validator_with_default import (
            DefaultValidatingDraft7Validator,
        )

        DefaultValidatingDraft7Validator(schema).validate(patcher_data)
        log("[OK] patcher.json passes open-dread-rando schema")
    except ModuleNotFoundError as exc:
        raise PatchError(_broken_odr_install_message(exc)) from exc
    except Exception as e:
        raise PatchError(
            "patcher.json failed open-dread-rando validation:\n"
            f"{_format_odr_validation_error(str(e))}"
        ) from e


def _broken_odr_install_message(exc: BaseException) -> str:
    return (
        "Broken or incomplete open-dread-rando install "
        f"({exc}).\n"
        "Hub Connect now installs ODR into a short local venv on Windows "
        f"(%LOCALAPPDATA%\\MetroidBread\\venv) to avoid MAX_PATH failures.\n"
        "Retry Connect, or manually:\n"
        '  "%LOCALAPPDATA%\\MetroidBread\\venv\\Scripts\\python.exe" -m pip install '
        '--force-reinstall "open-dread-rando>=2.19"\n'
        "Do not pip install into Microsoft Store Python (path too long)."
    )


def verify_elevator_brflds(romfs: Path, patcher_json: Path) -> None:
    """Fail the patch if written brfld transporter targets ≠ patcher.json.

    A prior shipyard wagontrain crash was chased while the live mod's brflds
    came from a *different* seed than patcher.json (re-patch overwrite). This
    check makes that desync a hard error instead of a silent in-game null deref.
    """
    with open(patcher_json, encoding="utf-8") as f:
        data = json.load(f)
    elevators = data.get("elevators") or []
    if not elevators:
        log("[OK] elevator verify skipped (no elevators in patcher.json)")
        return

    try:
        from mercury_engine_data_structures.formats.brfld import Brfld
        from mercury_engine_data_structures.game_check import Game
    except ImportError as exc:
        raise PatchError(
            f"cannot verify elevators — mercury_engine_data_structures missing: {exc}"
        ) from exc

    brfld_root = romfs / "maps" / "levels" / "c10_samus"
    mismatches: list[str] = []
    for entry in elevators:
        tele = entry.get("teleporter") or {}
        dest = entry.get("destination") or {}
        scenario = tele.get("scenario")
        actor = tele.get("actor")
        want_scen = dest.get("scenario")
        want_spawn = dest.get("actor")
        if not scenario or not actor:
            mismatches.append(f"bad teleporter entry: {entry!r}")
            continue
        path = brfld_root / scenario / f"{scenario}.brfld"
        if not path.is_file():
            mismatches.append(f"missing brfld {path}")
            continue
        brfld = Brfld.parse(path.read_bytes(), target_game=Game.DREAD)
        try:
            usable = brfld.actors_for_sublayer("default")[actor].pComponents.USABLE
        except Exception as exc:
            mismatches.append(f"missing actor {scenario}/{actor}: {exc}")
            continue
        got_scen = usable.get("sScenarioName")
        got_spawn = usable.get("sTargetSpawnPoint")
        if got_scen != want_scen or got_spawn != want_spawn:
            mismatches.append(
                f"{scenario}/{actor}: want {want_scen}/{want_spawn} "
                f"got {got_scen}/{got_spawn}"
            )
        # Defensive: never ship null/empty spawn strings.
        if not got_scen or not got_spawn:
            mismatches.append(
                f"{scenario}/{actor}: empty sScenarioName/sTargetSpawnPoint "
                f"({got_scen!r}/{got_spawn!r})"
            )

    if mismatches:
        detail = "\n  ".join(mismatches[:20])
        more = f"\n  ... and {len(mismatches) - 20} more" if len(mismatches) > 20 else ""
        raise PatchError(
            f"elevator brfld verify failed ({len(mismatches)} mismatch(es)) — "
            f"mod would crash on transport use:\n  {detail}{more}\n"
            "Do not mix patcher.json from one seed with romfs from another. "
            "Re-run a clean patch (delete the mod output folder first)."
        )
    log(f"[OK] elevator brfld verify: {len(elevators)} transporters match patcher.json")


def run_open_dread_rando(
    python_cmd: list[str],
    patcher_json: Path,
    base_rom: Path,
    output: Path,
) -> None:
    if not base_rom.is_dir():
        raise PatchError(
            f"Base ROM folder not found:\n  {base_rom}\n"
            "Set base_rom_path in dread_direct_patch_config.json\n"
            "(extracted Dread romfs: either <dump>/romfs/system/files.toc or <dump>/system/files.toc)."
        )
    toc_a = base_rom / "romfs" / "system" / "files.toc"
    toc_b = base_rom / "system" / "files.toc"
    if not toc_a.is_file() and not toc_b.is_file():
        raise PatchError(
            f"Base ROM looks incomplete (no system/files.toc):\n  {base_rom}\n"
            "Point base_rom_path at the extracted RomFS folder (contains gui/, packs/, system/, …)."
        )

    output.mkdir(parents=True, exist_ok=True)

    cmd = python_cmd + [
        "-m",
        "open_dread_rando",
        "--input-json",
        str(patcher_json),
        "--input-path",
        str(base_rom),
        "--output-path",
        str(output),
    ]
    log("\n>>> open-dread-rando")
    log("    " + " ".join(cmd))
    log("-" * 60)

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        raise PatchError(f"open-dread-rando failed with exit code {result.returncode}")


def _register_system_script_asset(romfs: Path, stem: str, data: bytes) -> None:
    """
    Register a system/scripts/<stem>.{lua,lc} so Game.DoFile('….lua') works.

    ODR stores custom system scripts as .lc inside packs/system/system.pkg and TOC.
    A loose romfs copy alone is invisible to the engine / depackager.
    """
    from mercury_engine_data_structures.formats.pkg import Pkg
    from mercury_engine_data_structures.formats.toc import Toc
    from mercury_engine_data_structures.game_check import Game

    scripts_dir = romfs / "system" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    asset_lua = f"system/scripts/{stem}.lua"
    asset_lc = f"system/scripts/{stem}.lc"
    (scripts_dir / f"{stem}.lua").write_bytes(data)
    (scripts_dir / f"{stem}.lc").write_bytes(data)
    log(f"[OK] wrote loose {asset_lua} + {asset_lc} ({len(data)} bytes)")

    toc_path = romfs / "system" / "files.toc"
    pkg_path = romfs / "packs" / "system" / "system.pkg"
    if not toc_path.is_file() or not pkg_path.is_file():
        raise PatchError(
            f"missing TOC/pkg under {romfs} — cannot register DoFile asset "
            f"(toc={toc_path.is_file()} pkg={pkg_path.is_file()}). "
            "Loose romfs copy alone is not enough; ODR must have written "
            "system/files.toc and packs/system/system.pkg first."
        )

    toc = Toc.parse(toc_path.read_bytes(), target_game=Game.DREAD)
    toc.add_file(asset_lc, len(data))
    toc.add_file(Toc.system_files_name(), len(toc.build()))
    toc_path.write_bytes(toc.build())
    log(f"[OK] TOC registered {asset_lc} ({len(data)} bytes)")

    with pkg_path.open("rb") as f:
        pkg = Pkg.parse_stream(f, target_game=Game.DREAD)
    if pkg.get_asset(asset_lc) is not None:
        pkg.replace_asset(asset_lc, data)
        log(f"[OK] system.pkg replaced {asset_lc}")
    else:
        pkg.add_asset(asset_lc, data)
        log(f"[OK] system.pkg added {asset_lc}")
    with pkg_path.open("wb") as f:
        pkg.build_stream(f)

    repl_path = romfs / "replacements.json"
    if repl_path.is_file():
        try:
            repl = json.loads(repl_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            repl = {"replacements": []}
        items = repl.setdefault("replacements", [])
        if asset_lc not in items:
            items.append(asset_lc)
            repl_path.write_text(json.dumps(repl, indent=4) + "\n", encoding="utf-8")
            log(f"[OK] replacements.json += {asset_lc}")
        else:
            log(f"[OK] replacements.json already lists {asset_lc}")
    else:
        log("[WARN] replacements.json missing — pack/TOC registration should still work")


def install_reachable_map_script(romfs: Path, src_lua: Path) -> None:
    """Register bounds Lua so Game.DoFile('system/scripts/ap_reachable_map_cells.lua') works."""
    if not src_lua.is_file():
        log(
            f"[WARN] missing {src_lua} — run tools/build_reachable_map_cells.py "
            "(reachable minimap bounds will not load in-game)"
        )
        return

    data = src_lua.read_bytes()
    if len(data) > 200_000:
        raise PatchError(
            f"{src_lua.name} is {len(data)} bytes — expected bounds-only ~22KB. "
            "Full MapAreaCells tables break Game.DoFile; rebuild with "
            "tools/build_reachable_map_cells.py (no --include-cells)."
        )

    _register_system_script_asset(romfs, "ap_reachable_map_cells", data)

    stale_json = romfs / "system" / "scripts" / "ap_reachable_map_cells.json"
    if stale_json.is_file() and stale_json.stat().st_size > 200_000:
        stale_json.unlink()
        log(f"[OK] removed oversized debug JSON {stale_json.name}")


def install_map_unlock_region_script(romfs: Path) -> None:
    """Register AreaBox unlock smoke for /map_unlock_region (DoFile, not bootstrap)."""
    src = dread_paths.dread_scripts_dir() / "ap_map_unlock_region.lua"
    if not src.is_file():
        log(f"[WARN] missing {src} — /map_unlock_region DoFile will fail")
        return
    _register_system_script_asset(romfs, "ap_map_unlock_region", src.read_bytes())


def install_ap_map_icon_atlas(romfs: Path) -> None:
    """Overwrite ODR's minimap icons.bctex with the AP-stamped atlas.

    ODR already replaces textures/system/minimap/icons/icons.bctex via
    add_custom_files; we drop our stamped copy on the same loose-romfs path
    (and replacements.json entry) so:
      - foreign / unknown reveals use the Archipelago cluster cell
      - in-logic uncollected checks can use the green '?' cell at runtime
    """
    src = ROOT / "assets" / "icons.bctex"
    if not src.is_file():
        log(
            f"[WARN] missing {src} — run dread_scripts/build_ap_map_icon_atlas.py "
            "(foreign map icons stay on the ItemSphere cell; in-logic ? unavailable)"
        )
        return
    rel = Path("textures") / "system" / "minimap" / "icons" / "icons.bctex"
    dst = romfs / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log(f"[OK] AP map-icon atlas -> {rel.as_posix()} ({src.stat().st_size} bytes)")

    repl_path = romfs / "replacements.json"
    asset = rel.as_posix()
    if repl_path.is_file():
        try:
            with open(repl_path, encoding="utf-8") as f:
                repl = json.load(f)
        except (OSError, json.JSONDecodeError):
            repl = {"replacements": []}
        items = repl.setdefault("replacements", [])
        if asset not in items:
            items.append(asset)
            with open(repl_path, "w", encoding="utf-8") as f:
                json.dump(repl, f, indent=2)
            log(f"[OK] replacements.json += {asset}")
    else:
        log("[WARN] replacements.json missing — loose icons.bctex should still load")


HK_AUTOSAVE_MARKER = "-- AP_HK_AUTOSAVE"
AP_WARP_MARKER = "-- AP_WARP"
AP_WARP_BOOTSTRAP = """
-- AP_WARP
-- Must load AFTER ODR defines Scenario.CheckDebugInputs / CheckWarpToStart.
-- Location-independent warps: ZL+close menu / ZL+DPAD_LEFT = last checkpoint;
-- ZR+close menu / ZR+DPAD_RIGHT = last save.
Game.DoFile("system/scripts/ap_warp.lua")
if ApWarp and ApWarp.Install then
    ApWarp.Install()
end
""".lstrip()

AP_LOADING_TIPS_MARKER = "-- AP_LOADING_TIPS"
AP_LOADING_TIPS_BOOTSTRAP = """
-- AP_LOADING_TIPS
-- Early init hook: wrap ShowLoadingScreen so Continue / New Game get ForcedTooltip.
pcall(function()
  Game.DoFile("system/scripts/ap_loading_tips.lua")
  if ApLoadingTips and ApLoadingTips.Install then
    ApLoadingTips.Install()
  end
end)
""".lstrip()

_HK_AUTOSAVE_BLOCK_RE = re.compile(
    r"\n*-- AP_HK_AUTOSAVE\n"
    r"(?:.*\n)*?"
    r"if HkAutosave and HkAutosave\.Install then\n"
    r"\s*HkAutosave\.Install\(\)\n"
    r"end\n?",
    re.MULTILINE,
)

_AP_WARP_BLOCK_RE = re.compile(
    r"\n*-- AP_WARP\n"
    r"(?:.*\n)*?"
    r"if ApWarp and ApWarp\.Install then\n"
    r"\s*ApWarp\.Install\(\)\n"
    r"end\n?",
    re.MULTILINE,
)

# ODR ≥2.19 death-only HUD: move DeathCounter into the DNA row of ExtraInfoPanel.
# Stock ODR reads DNA_Icon/DNA_Label via _Y_GetterFunction / _CenterY_GetterFunction;
# on Ryujinx those getters often return junk/0 and park the label off-slot (below the
# short background). Hardcode the coords from ODR's randohudcomposition.bmscp.
_ODR_DEATH_COUNTER_REPOSITION_RE = re.compile(
    r"(?P<indent>[ \t]*)if not showDnaInHud then\n"
    r"[ \t]*-- Need to move the death counter icon and label up to where the DNA would normally be shown\n"
    r"[ \t]*local dnaIconY = Scenario\.ExtraInfoPanel:FindChild\(\"DNA_Icon\"\):_Y_GetterFunction\(\)\n"
    r"[ \t]*local dnaLabelY = Scenario\.ExtraInfoPanel:FindChild\(\"DNA_Label\"\):_CenterY_GetterFunction\(\)\n"
    r"\n?"
    r"[ \t]*GUI\.SetProperties\(Scenario\.ExtraInfoPanel:FindChild\(\"DeathCounter_Icon\"\), \{ Y = dnaIconY \}\)\n"
    r"[ \t]*GUI\.SetProperties\(Scenario\.ExtraInfoPanel:FindChild\(\"DeathCounter_Label\"\), \{ CenterY = dnaLabelY \}\)\n"
    r"(?P=indent)end",
    re.MULTILINE,
)

# DNA_Icon.Y / DNA_Label.CenterY from open_dread_rando files/romfs/gui/scripts/randohudcomposition.bmscp
_ODR_DNA_ICON_Y = 0.014536125585436821
_ODR_DNA_LABEL_CENTERY = 0.014536126516759396

_AP_DEATH_COUNTER_HUD_MARKER = "-- AP: hardcode ODR DNA-slot coords"


def _read_scenario_lc(romfs: Path) -> tuple[bytes, object]:
    """Return (scenario.lc bytes, parsed Pkg). Raises PatchError if missing."""
    from mercury_engine_data_structures.formats.pkg import Pkg
    from mercury_engine_data_structures.game_check import Game

    asset_lc = "system/scripts/scenario.lc"
    toc_path = romfs / "system" / "files.toc"
    pkg_path = romfs / "packs" / "system" / "system.pkg"
    loose_lc = romfs / "system" / "scripts" / "scenario.lc"
    loose_lua = romfs / "system" / "scripts" / "scenario.lua"

    if not toc_path.is_file() or not pkg_path.is_file():
        raise PatchError(
            f"missing TOC/pkg under {romfs} — cannot patch {asset_lc}"
        )

    with pkg_path.open("rb") as f:
        pkg = Pkg.parse_stream(f, target_game=Game.DREAD)

    existing = pkg.get_asset(asset_lc)
    if existing is None and loose_lc.is_file():
        existing = loose_lc.read_bytes()
    elif existing is None and loose_lua.is_file():
        existing = loose_lua.read_bytes()
    if existing is None:
        raise PatchError(f"{asset_lc} not found in system.pkg after ODR")
    return existing, pkg


def _write_scenario_lc(romfs: Path, data: bytes, pkg) -> None:
    """Write scenario.lc to loose romfs + system.pkg + TOC."""
    from mercury_engine_data_structures.formats.toc import Toc
    from mercury_engine_data_structures.game_check import Game

    asset_lc = "system/scripts/scenario.lc"
    toc_path = romfs / "system" / "files.toc"
    pkg_path = romfs / "packs" / "system" / "system.pkg"
    scripts_dir = romfs / "system" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "scenario.lc").write_bytes(data)
    (scripts_dir / "scenario.lua").write_bytes(data)

    if pkg.get_asset(asset_lc) is not None:
        pkg.replace_asset(asset_lc, data)
    else:
        pkg.add_asset(asset_lc, data)
    with pkg_path.open("wb") as f:
        pkg.build_stream(f)

    toc = Toc.parse(toc_path.read_bytes(), target_game=Game.DREAD)
    toc.add_file(asset_lc, len(data))
    toc.add_file(Toc.system_files_name(), len(toc.build()))
    toc_path.write_bytes(toc.build())


def strip_hk_autosave_from_scenario(romfs: Path) -> None:
    """
    Remove ProgressKeeper / HkAutosave bootstrap from scenario.lc.

    That path reinjected ProgressStore on load and could wipe inventory.
    Safe no-op when TOC/pkg or the marker is absent.
    """
    if not (romfs / "packs" / "system" / "system.pkg").is_file():
        log("[WARN] strip HK autosave skipped — no system.pkg yet")
        return
    try:
        existing, pkg = _read_scenario_lc(romfs)
    except PatchError as exc:
        log(f"[WARN] strip HK autosave skipped: {exc}")
        return

    text = existing.decode("utf-8", errors="replace")
    if HK_AUTOSAVE_MARKER not in text and "HkAutosave.Install" not in text:
        log("[OK] scenario.lc has no HK autosave bootstrap")
        return

    stripped = _HK_AUTOSAVE_BLOCK_RE.sub("\n", text)
    if stripped == text:
        # Fallback: crude cut from marker through Install() end
        idx = text.find(HK_AUTOSAVE_MARKER)
        if idx < 0:
            idx = text.find("Game.DoFile(\"system/scripts/progress_keeper.lua\")")
        end = text.find("HkAutosave.Install()", idx if idx >= 0 else 0)
        if idx >= 0 and end >= 0:
            end_line = text.find("\n", end)
            if end_line < 0:
                end_line = len(text)
            else:
                # include following `end`
                rest = text[end_line + 1 :]
                if rest.lstrip().startswith("end"):
                    end_line = end_line + 1 + rest.find("end") + 3
            stripped = text[:idx].rstrip() + "\n" + text[end_line:].lstrip()
        else:
            log("[WARN] HK autosave marker found but block could not be stripped")
            return

    data = stripped.encode("utf-8")
    _write_scenario_lc(romfs, data, pkg)
    log(f"[OK] stripped HK autosave bootstrap from scenario.lc ({len(data)} bytes)")


def _ap_death_counter_reposition_block(indent: str) -> str:
    """Lua that parks death-counter icon/label on ODR's DNA row (death-only HUD)."""
    return (
        f"{indent}if not showDnaInHud then\n"
        f"{indent}    {_AP_DEATH_COUNTER_HUD_MARKER} (bmscp). Avoid _Y_GetterFunction on Ryujinx.\n"
        f"{indent}    GUI.SetProperties(Scenario.ExtraInfoPanel:FindChild(\"DeathCounter_Icon\"), "
        f"{{ Y = {_ODR_DNA_ICON_Y} }})\n"
        f"{indent}    GUI.SetProperties(Scenario.ExtraInfoPanel:FindChild(\"DeathCounter_Label\"), "
        f"{{ CenterY = {_ODR_DNA_LABEL_CENTERY} }})\n"
        f"{indent}end"
    )


def fix_death_counter_hud_position(romfs: Path) -> None:
    """
    Make ODR ≥2.19 death-only HUD match DNA-slot placement without runtime getters.

    ExtraInfoPanel sits at (X=0.025, Y≈0.2019) on iconshudcomposition — same band as
    legacy GUILib death_counter (Y=0.1975). DeathCounter_* defaults are the dual-row
    lower slot; when DNA HUD is off, ODR moves them to DNA_Icon/DNA_Label coords.
    """
    try:
        existing, pkg = _read_scenario_lc(romfs)
    except PatchError as exc:
        log(f"[WARN] death-counter HUD fix skipped: {exc}")
        return

    text = existing.decode("utf-8", errors="replace")
    if _AP_DEATH_COUNTER_HUD_MARKER in text:
        log("[OK] death-counter HUD already uses hardcoded ODR DNA-slot coords")
        return

    match = _ODR_DEATH_COUNTER_REPOSITION_RE.search(text)
    if not match:
        # ODR ≤2.18 builds the counter via GUILib at X=0.025,Y=0.1975 — nothing to fix.
        if "DeathCounter_Icon" in text or "_Y_GetterFunction" in text:
            log(
                "[WARN] death-counter HUD getter block not found — left scenario.lc unchanged"
            )
        else:
            log("[OK] no ODR≥2.19 death-counter reposition block (legacy GUILib layout)")
        return

    replacement = _ap_death_counter_reposition_block(match.group("indent"))
    new_text = text[: match.start()] + replacement + text[match.end() :]
    data = new_text.encode("utf-8")
    _write_scenario_lc(romfs, data, pkg)
    log(
        "[OK] death-counter HUD: hardcoded ODR DNA-slot coords "
        f"(Y={_ODR_DNA_ICON_Y}, CenterY={_ODR_DNA_LABEL_CENTERY})"
    )


def install_ap_warp_scripts(romfs: Path) -> None:
    """Install ApWarp Lua + wire DoFile/Install into ODR custom_scenario (scenario.lc)."""
    src = dread_paths.dread_scripts_dir() / "ap_warp.lua"
    if not src.is_file():
        raise PatchError(f"missing ApWarp script: {src}")
    _register_system_script_asset(romfs, "ap_warp", src.read_bytes())
    _patch_scenario_for_ap_warp(romfs)


def _patch_scenario_for_ap_warp(romfs: Path) -> None:
    """
    Install ApWarp bootstrap at the END of scenario.lc.

    Mid-file install (e.g. after death_counter) runs before ODR defines
    CheckDebugInputs / CheckWarpToStart, so hooks never attach. Always strip any
    prior -- AP_WARP block and re-append at EOF.
    """
    existing, pkg = _read_scenario_lc(romfs)
    text = existing.decode("utf-8", errors="replace")
    if AP_WARP_MARKER in text:
        relocated = _AP_WARP_BLOCK_RE.sub("\n", text)
        if relocated == text:
            log("[WARN] ApWarp marker found but block could not be relocated")
            return
        text = relocated
        log("[OK] removed prior ApWarp bootstrap (will re-append at EOF)")

    text = text.rstrip() + "\n\n" + AP_WARP_BOOTSTRAP
    data = text.encode("utf-8")
    _write_scenario_lc(romfs, data, pkg)
    log(f"[OK] patched scenario.lc with ApWarp.Install at EOF ({len(data)} bytes)")


def _read_init_lc(romfs: Path) -> tuple[bytes, object]:
    """Return (init.lc bytes, parsed Pkg). Raises PatchError if missing."""
    from mercury_engine_data_structures.formats.pkg import Pkg
    from mercury_engine_data_structures.game_check import Game

    asset_lc = "system/scripts/init.lc"
    toc_path = romfs / "system" / "files.toc"
    pkg_path = romfs / "packs" / "system" / "system.pkg"
    loose_lc = romfs / "system" / "scripts" / "init.lc"
    loose_lua = romfs / "system" / "scripts" / "init.lua"

    if not toc_path.is_file() or not pkg_path.is_file():
        raise PatchError(
            f"missing TOC/pkg under {romfs} — cannot patch {asset_lc}"
        )

    with pkg_path.open("rb") as f:
        pkg = Pkg.parse_stream(f, target_game=Game.DREAD)

    existing = pkg.get_asset(asset_lc)
    if existing is None and loose_lc.is_file():
        existing = loose_lc.read_bytes()
    elif existing is None and loose_lua.is_file():
        existing = loose_lua.read_bytes()
    if existing is None:
        raise PatchError(f"{asset_lc} not found in system.pkg after ODR")
    return existing, pkg


def _write_init_lc(romfs: Path, data: bytes, pkg) -> None:
    """Write init.lc to loose romfs + system.pkg + TOC."""
    from mercury_engine_data_structures.formats.toc import Toc
    from mercury_engine_data_structures.game_check import Game

    asset_lc = "system/scripts/init.lc"
    toc_path = romfs / "system" / "files.toc"
    pkg_path = romfs / "packs" / "system" / "system.pkg"
    scripts_dir = romfs / "system" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "init.lc").write_bytes(data)
    (scripts_dir / "init.lua").write_bytes(data)

    if pkg.get_asset(asset_lc) is not None:
        pkg.replace_asset(asset_lc, data)
    else:
        pkg.add_asset(asset_lc, data)
    with pkg_path.open("wb") as f:
        pkg.build_stream(f)

    toc = Toc.parse(toc_path.read_bytes(), target_game=Game.DREAD)
    toc.add_file(asset_lc, len(data))
    toc.add_file(Toc.system_files_name(), len(toc.build()))
    toc_path.write_bytes(toc.build())


def install_ap_loading_tips_scripts(romfs: Path) -> None:
    """Install ForcedTooltip tip injector + wire DoFile/Install into init.lc (+ scenario backup)."""
    src = dread_paths.dread_scripts_dir() / "ap_loading_tips.lua"
    if not src.is_file():
        raise PatchError(f"missing ApLoadingTips script: {src}")
    _register_system_script_asset(romfs, "ap_loading_tips", src.read_bytes())
    _patch_init_for_ap_loading_tips(romfs)
    _patch_scenario_for_ap_loading_tips(romfs)


def _patch_init_for_ap_loading_tips(romfs: Path) -> None:
    """
    Append ApLoadingTips bootstrap at EOF of init.lc (idempotent).

    Must run early (init), not scenario.lc alone — Continue/New Game show the loading
    screen before Scenario bootstrap would run. scenario.lc also gets a backup Install.
    """
    existing, pkg = _read_init_lc(romfs)
    text = existing.decode("utf-8", errors="replace")
    if AP_LOADING_TIPS_MARKER in text:
        # Truncate from marker (more reliable than nested-pcall regex).
        idx = text.find(AP_LOADING_TIPS_MARKER)
        text = text[:idx].rstrip() + "\n"
        log("[OK] removed prior ApLoadingTips bootstrap from init.lc (will re-append)")

    text = text.rstrip() + "\n\n" + AP_LOADING_TIPS_BOOTSTRAP
    data = text.encode("utf-8")
    _write_init_lc(romfs, data, pkg)
    log(f"[OK] patched init.lc with ApLoadingTips.Install at EOF ({len(data)} bytes)")


def _patch_scenario_for_ap_loading_tips(romfs: Path) -> None:
    """Backup Install at EOF of scenario.lc (idempotent; safe if already installed)."""
    existing, pkg = _read_scenario_lc(romfs)
    text = existing.decode("utf-8", errors="replace")
    marker = "-- AP_LOADING_TIPS_SCENARIO"
    bootstrap = (
        f"{marker}\n"
        "pcall(function()\n"
        '  if not ApLoadingTips then\n'
        '    Game.DoFile("system/scripts/ap_loading_tips.lua")\n'
        "  end\n"
        "  if ApLoadingTips and ApLoadingTips.Install then\n"
        "    ApLoadingTips.Install()\n"
        "  end\n"
        "end)\n"
    )
    if marker in text:
        idx = text.find(marker)
        text = text[:idx].rstrip() + "\n"
        log("[OK] removed prior ApLoadingTips scenario bootstrap (will re-append)")
    text = text.rstrip() + "\n\n" + bootstrap
    data = text.encode("utf-8")
    _write_scenario_lc(romfs, data, pkg)
    log(f"[OK] patched scenario.lc with ApLoadingTips.Install backup ({len(data)} bytes)")


def apply_ap_credits_branding(romfs: Path) -> None:
    """
    Post-process ODR credits.txt:
      - Title: Metroid Bread → Metroid Bread
      - Insert "Archipelago Implementation" / Dummydude just before Major Item Locations
    Keeps the full Randomizer Credits block intact.

    Inserted strings are scrubbed with ap_to_patcher.sanitize_credits_text (printable
    ASCII only) so branding cannot introduce illegal glyphs into BTXT. CREDIT_R_*
    rows are re-scrubbed on rewrite (skips whitespace-only spacers).
    """
    credits_path = romfs / "system" / "localization" / "credits.txt"
    if not credits_path.is_file():
        log(f"[WARN] credits.txt not found at {credits_path} — skipping AP credits branding")
        return

    try:
        from mercury_engine_data_structures.formats.txt import Txt
        from mercury_engine_data_structures.game_check import Game
    except ImportError as exc:
        log(f"[WARN] cannot edit credits.txt (mercury missing): {exc}")
        return

    try:
        from ap_to_patcher import sanitize_credits_text
    except ImportError:
        def sanitize_credits_text(value, **_kwargs):  # type: ignore[misc]
            return str(value or "")

    title_key = "CREDIT_0_000_TITLE"
    ap_subtitle_key = "CREDIT_AP_000_SUBTITLE"
    ap_name_key = "CREDIT_AP_001"
    bread_title = sanitize_credits_text("Metroid Bread", max_lines=1)
    ap_subtitle = sanitize_credits_text("Archipelago Implementation", max_lines=1)
    ap_name = sanitize_credits_text("Dummydude", max_lines=1)
    major_title = "Major Item Locations"

    txt = Txt.parse(credits_path.read_bytes(), target_game=Game.DREAD)
    ordered = list(txt.strings.items())

    # 1) Rename game title
    changed_title = False
    for i, (key, value) in enumerate(ordered):
        if key == title_key or (i == 0 and value == "Metroid Dread"):
            if value != bread_title:
                ordered[i] = (key if key == title_key else title_key, bread_title)
                changed_title = True
            break

    # 2) Insert AP credit block before Major Item Locations (idempotent)
    already = any(k == ap_subtitle_key or v == ap_subtitle for k, v in ordered)
    inserted = False
    if not already:
        insert_at = None
        for i, (key, value) in enumerate(ordered):
            if value == major_title and key.endswith("_TITLE"):
                insert_at = i
                break
        # Fallback when spoiler_log was empty (ODR skips Major Item Locations):
        # insert after Randomizer Credits block, before remaining CREDIT_0_* rows.
        if insert_at is None:
            for i, (key, _value) in enumerate(ordered):
                if key.startswith("CREDIT_0_") and i > 0:
                    insert_at = i
                    break
        # Last resort: after title (index 0), before whatever follows.
        if insert_at is None and ordered:
            insert_at = 1 if len(ordered) > 1 else len(ordered)
        if insert_at is None:
            log("[WARN] No credits insert point found — AP block not inserted")
        else:
            ordered[insert_at:insert_at] = [
                (ap_subtitle_key, ap_subtitle),
                (ap_name_key, ap_name),
            ]
            inserted = True

    # Scrub any CREDIT_R_* values that still carry illegal glyphs (old patcher
    # JSON / future ODR paths). Preserve whitespace-only spacer rows.
    scrubbed = 0
    for i, (key, value) in enumerate(ordered):
        if not key.startswith("CREDIT_R_"):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        clean = sanitize_credits_text(value)
        if clean != value:
            ordered[i] = (key, clean)
            scrubbed += 1

    if not changed_title and not inserted and already and not scrubbed:
        # Still rewrite if title was wrong somehow but AP block exists
        if any(k == title_key and v == bread_title for k, v in ordered):
            log("[OK] credits.txt already has AP branding")
            return

    txt.strings = {k: v for k, v in ordered}
    credits_path.write_bytes(txt.build())
    bits = []
    if changed_title:
        bits.append(f"title→{bread_title}")
    if inserted:
        bits.append(f"+{ap_subtitle}/{ap_name}")
    if already and not inserted:
        bits.append("AP block kept")
    if scrubbed:
        bits.append(f"scrubbed {scrubbed} CREDIT_R rows")
    log(f"[OK] credits.txt branded ({', '.join(bits) or 'rewritten'}) -> {credits_path}")


def finalize_mod(
    output: Path,
    patcher_json: Path,
    *,
    custom_exlaunch_deploy: Optional[Path] = None,
    map_icon_keys_json: Optional[Path] = None,
) -> None:
    """Copy client-facing extras into the Ryujinx mod tree (Randovania layout)."""
    mod_root = output / "DreadRandovania"
    # open-dread-rando may write romfs at output/ or output/DreadRandovania/
    candidates = [
        output / "romfs",
        mod_root / "romfs",
        output,
    ]

    # Prefer a folder that already has romfs or exefs from the patcher
    romfs_parent = output
    for c in (output, mod_root):
        if (c / "romfs").is_dir() or (c / "exefs").is_dir():
            romfs_parent = c
            break

    # Always keep a copy of patcher.json next to the mod for debugging / UUID
    dst_json = romfs_parent / "patcher.json"
    shutil.copy2(patcher_json, dst_json)
    log(f"[OK] patcher.json -> {dst_json}")

    # Phase 2: pickup/location → MAP_ICON_ItemCustom{n} for runtime OdrText labels.
    keys_src = map_icon_keys_json
    if keys_src is None or not keys_src.is_file():
        sibling = patcher_json.with_name(
            patcher_json.name.replace("_patcher.json", "_map_icon_keys.json")
        )
        if sibling.is_file():
            keys_src = sibling
        else:
            # Derive from patcher pickups order (same as ODR custom_icon assignment).
            try:
                from dread_map_icon_labels import (
                    build_map_icon_keys_for_patcher,
                    write_map_icon_keys,
                )

                with open(patcher_json, encoding="utf-8") as f:
                    pdata = json.load(f)
                derived = patcher_json.parent / "map_icon_keys.json"
                write_map_icon_keys(derived, build_map_icon_keys_for_patcher(pdata))
                keys_src = derived
                log(f"[OK] derived map_icon_keys.json ({pdata and len(pdata.get('pickups') or [])} pickups)")
            except Exception as exc:
                log(f"[WARN] could not build map_icon_keys.json: {exc}")
                keys_src = None
    if keys_src is not None and keys_src.is_file():
        dst_keys = romfs_parent / "map_icon_keys.json"
        shutil.copy2(keys_src, dst_keys)
        log(f"[OK] map_icon_keys.json -> {dst_keys}")

    lua_dst = (
        romfs_parent
        / "romfs"
        / "actors"
        / "items"
        / "randomizer_powerup"
        / "scripts"
        / "randomizer_powerup.lua"
    )
    lua_dst.parent.mkdir(parents=True, exist_ok=True)
    overrides = dread_paths.dread_scripts_dir() / "ap_powerup_overrides.lua"
    odr_lc = lua_dst.with_suffix(".lc")
    # Prefer ODR-generated script (progressive/boss classes) + AP overrides appended.
    # DoFile('...randomizer_powerup.lua') shadows .lc when the .lua exists.
    base_bytes: Optional[bytes] = None
    if odr_lc.is_file():
        base_bytes = odr_lc.read_bytes()
        log(f"[OK] Using ODR-generated {odr_lc.name} as powerup base")
    elif lua_dst.is_file():
        base_bytes = lua_dst.read_bytes()
        log(f"[OK] Using existing {lua_dst.name} as powerup base")
    fallback = dread_paths.dread_scripts_dir() / "randomizer_powerup.lua"
    if base_bytes is None and fallback.is_file():
        base_bytes = fallback.read_bytes()
        log("[WARN] No ODR powerup script found — using AP fallback randomizer_powerup.lua")
    if base_bytes is not None:
        text = base_bytes.decode("utf-8", errors="replace")
        if overrides.is_file():
            text = text.rstrip() + "\n\n" + overrides.read_text(encoding="utf-8")
            log(f"[OK] Appended AP overrides from {overrides.name}")
        # Bake Require-Main + All Bosses gate flags from pickup layout / extras.
        requires_main = False
        all_bosses_gate = False
        try:
            with open(patcher_json, encoding="utf-8") as f:
                pdata = json.load(f)
            from flash_shift import infer_requires_main_from_pickups, plan_from_extras

            meta = pdata.get("_ap_flash_shift") if isinstance(pdata, dict) else None
            extras_path = patcher_json.with_name(
                patcher_json.name.replace("_patcher.json", "_extras.json")
            )
            extras = {}
            if extras_path.is_file():
                with open(extras_path, encoding="utf-8") as ef:
                    extras = json.load(ef) or {}
            if not isinstance(extras, dict):
                extras = {}
            if isinstance(meta, dict) and "requires_main" in meta:
                requires_main = bool(meta.get("requires_main"))
            else:
                plan = plan_from_extras(extras)
                if extras:
                    requires_main = bool(plan.get("require_main")) and not bool(
                        plan.get("vanilla")
                    )
                else:
                    requires_main = infer_requires_main_from_pickups(
                        (pdata or {}).get("pickups") or []
                    )
            try:
                all_bosses_gate = int(extras.get("game_goal", 0) or 0) == 2
            except Exception:
                all_bosses_gate = False
        except Exception as exc:
            log(f"[WARN] Flash Shift / All Bosses flag detect failed: {exc}")
        flag = "true" if requires_main else "false"
        bosses_flag = "true" if all_bosses_gate else "false"
        text = (
            f"AP_FLASH_SHIFT_REQUIRES_MAIN = {flag}\n"
            f"AP_ALL_BOSSES_GATE = {bosses_flag}\n"
            + text
        )
        log(f"[OK] AP_FLASH_SHIFT_REQUIRES_MAIN = {flag}")
        log(f"[OK] AP_ALL_BOSSES_GATE = {bosses_flag}")
        lua_dst.write_text(text, encoding="utf-8", newline="\n")
        log(f"[OK] randomizer_powerup.lua -> {lua_dst}")
    else:
        log("[WARN] No randomizer_powerup script available to install")

    romfs = romfs_parent / "romfs"

    # Title + AP implementer credit (keeps ODR Randomizer Credits intact).
    apply_ap_credits_branding(romfs)

    # AP context-4 tip carousel BTXT (TIP_000–TIP_004). Belt-and-suspenders with
    # ap_to_patcher text_patches; also lets a finalize-only pass refresh a live mod.
    try:
        from dread_carousel_tip_patches import (
            apply_carousel_tip_text_patches_to_romfs,
            carousel_tip_text_patches_enabled,
        )

        if carousel_tip_text_patches_enabled():
            tip_writes = apply_carousel_tip_text_patches_to_romfs(romfs)
            if tip_writes:
                log(
                    f"[OK] Carousel tip text_patches applied to romfs "
                    f"({tip_writes} key writes; TIP_000–TIP_004 AP POOL4)"
                )
            else:
                log(
                    "[WARN] Carousel tip text_patches enabled but no TIP_* keys "
                    "updated under romfs localization (missing mercury or keys?)"
                )
        else:
            log("[INFO] Carousel tip text_patches skipped (disabled)")
    except Exception as exc:
        log(f"[WARN] Carousel tip text_patches failed: {exc}")

    # Remove leftover ProgressKeeper bootstrap (was wiping items on load).
    strip_hk_autosave_from_scenario(romfs)

    # Location-independent warp hotkeys (last checkpoint / last save).
    install_ap_warp_scripts(romfs)

    # ForcedTooltip on Continue / New Game loading screens (init.lc, early).
    install_ap_loading_tips_scripts(romfs)

    # Death-only ExtraInfoPanel: park counter on ODR DNA-slot coords (no Ryujinx getters).
    fix_death_counter_hud_position(romfs)

    # Reachable minimap offline data (bounds for OdrMap.VisitBounds).
    # Must be TOC + system.pkg (.lc), not loose-only — see install_reachable_map_script.
    # Order: after ODR romfs write, before custom exefs overlay.
    map_src_lua = ROOT / "data" / "reachable_map_cells.lua"
    install_reachable_map_script(romfs, map_src_lua)
    install_map_unlock_region_script(romfs)

    # Archipelago logo + green in-logic ? cells in the minimap atlas
    # (ODR ships progressive/DNA cells; we overwrite that same romfs path
    # with our stamped icons.bctex).
    install_ap_map_icon_atlas(romfs)

    # Optional debug JSON (not used by Game.DoFile). Skip huge full-cells exports.
    map_src_json = map_src_lua.with_suffix(".json")
    if map_src_json.is_file() and map_src_json.stat().st_size <= 200_000:
        dst_map_json = romfs / "system" / "scripts" / "ap_reachable_map_cells.json"
        dst_map_json.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(map_src_json, dst_map_json)
        log(f"[OK] optional debug JSON -> {dst_map_json.name}")

    # Quick remote-lua sanity
    try:
        with open(dst_json, encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("enable_remote_lua"):
            log("[WARN] enable_remote_lua is false — AP client will not connect")
        else:
            log("[OK] enable_remote_lua=true (TCP 6969 expected after boot)")
    except OSError:
        pass

    exefs = romfs_parent / "exefs"
    if exefs.is_dir():
        subsdk = list(exefs.glob("subsdk*"))
        log(f"[OK] exefs present ({len(subsdk)} subsdk* file(s))")
    else:
        log("[WARN] exefs/ not found under output — remote connector may be missing")
        exefs.mkdir(parents=True, exist_ok=True)

    # ODR writes stock remote-lua exlaunch; overlay custom OdrMap binders when available.
    # Must run AFTER ODR exefs install so VisitBounds is not overwritten by stock.
    # See worlds/metroid_bread/docs/odrmap_exlaunch_binder.md.
    install_custom_exlaunch(exefs, custom_exlaunch_deploy)
    log(
        "[OK] finalize_mod complete: ApWarp + ApLoadingTips + TOC/pkg map script + "
        "AP map-icon atlas + custom OdrMap exefs (enable_remote_lua kept on)"
    )


def patch_from_spoiler(
    spoiler: Path,
    player: str,
    base_rom: Path,
    output: Path,
    *,
    template: Path = DEFAULT_TEMPLATE,
    clean_output: bool = False,
    freesink: bool = False,
    custom_exlaunch_deploy: Optional[Path] = None,
    reveal_minimap_save: bool = False,
    layout_uuid: Optional[str] = None,
) -> Path:
    log("=" * 60)
    log("Archipelago Dread Direct Patcher")
    log("(spoiler -> patcher.json -> open-dread-rando -> Ryujinx mod)")
    log("=" * 60)
    log(f"Spoiler : {spoiler}")
    log(f"Player  : {player}")
    log(f"Base ROM: {base_rom}")
    log(f"Output  : {output}")
    log(f"Freesink: {freesink}")

    if clean_output and output.exists():
        log(f"Cleaning output: {output}")
        shutil.rmtree(output, ignore_errors=True)

    try:
        from ap_to_patcher import resolve_dread_player

        player = resolve_dread_player(spoiler, player)
    except ValueError as e:
        raise PatchError(str(e)) from e

    try:
        patcher_data = build_patcher_json(
            spoiler, player, template, layout_uuid=layout_uuid
        )
    except ValueError as e:
        raise PatchError(str(e)) from e
    # Re-apply with the spoiler path so seed id is never the RDV template leftover.
    ensure_remote_lua(patcher_data, spoiler_path=spoiler)
    apply_freesink(patcher_data, freesink)

    py = find_python_with_odr()
    log(f"Using Python with open-dread-rando: {' '.join(py)}")

    # Match patcher.json to the validating ODR schema (show_dna_in_hud /
    # has_flash_upgrades / has_speed_upgrades are ODR ≥2.19-only; older schemas
    # reject them with additionalProperties: false).
    from ap_to_patcher import apply_upgrade_menu_flags, sanitize_patcher_for_odr

    apply_upgrade_menu_flags(patcher_data, py_cmd=py)
    stripped = sanitize_patcher_for_odr(patcher_data, py_cmd=py)
    if stripped:
        log(
            "[INFO] Stripped patcher keys unsupported by patch ODR: "
            + ", ".join(stripped)
        )

    out_json = spoiler.parent / f"AP_{player}_patcher.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(patcher_data, f, indent=2)
    log(
        f"[OK] Wrote {out_json} ({len(patcher_data.get('pickups', []))} pickups) "
        f"layout_uuid={patcher_data.get('layout_uuid')}"
    )

    from dread_map_icon_labels import (
        build_map_icon_keys_for_patcher,
        write_map_icon_keys,
    )

    from ap_to_patcher import last_map_icon_sprites

    keys_data = build_map_icon_keys_for_patcher(
        patcher_data, sprite_by_pickup_index=last_map_icon_sprites()
    )
    out_keys = spoiler.parent / f"AP_{player}_map_icon_keys.json"
    write_map_icon_keys(out_keys, keys_data)
    log(
        f"[OK] Wrote {out_keys} "
        f"({keys_data.get('custom_icon_count', 0)} MAP_ICON_ItemCustom* keys)"
    )

    # Validate against schema.json only (avoid importing dread_patcher → misc_patches).
    val = subprocess.run(
        py
        + [
            "-c",
            (
                "import json,sys;"
                "from pathlib import Path;"
                "import open_dread_rando;"
                "from open_dread_rando.validator_with_default import "
                "DefaultValidatingDraft7Validator;"
                "schema=json.load(open("
                "Path(open_dread_rando.__file__).resolve().parent/'files'/'schema.json',"
                "encoding='utf-8'));"
                "DefaultValidatingDraft7Validator(schema).validate("
                "json.load(open(sys.argv[1],encoding='utf-8')));"
                "print('SCHEMA_OK')"
            ),
            str(out_json),
        ],
        capture_output=True,
        text=True,
    )
    if val.returncode != 0 or "SCHEMA_OK" not in (val.stdout or ""):
        err = (val.stderr or val.stdout or "").strip()
        if "misc_patches" in err or "ModuleNotFoundError" in err:
            raise PatchError(_broken_odr_install_message(err or "import failed"))
        raise PatchError(
            "patcher.json failed open-dread-rando validation:\n"
            f"{_format_odr_validation_error(err)}"
        )
    log("[OK] patcher.json passes open-dread-rando schema")

    run_open_dread_rando(py, out_json, base_rom, output)
    # Prefer the ODR/Ryujinx mod layout; fall back to bare output/romfs.
    romfs_candidates = [
        output / "DreadRandovania" / "romfs",
        output / "romfs",
        output,
    ]
    romfs_for_verify = next(
        (p for p in romfs_candidates if (p / "maps" / "levels" / "c10_samus").is_dir()),
        None,
    )
    if romfs_for_verify is None:
        raise PatchError(
            "open-dread-rando finished but no maps/levels/c10_samus tree was found "
            f"under {output} — cannot verify elevator patches"
        )
    verify_elevator_brflds(romfs_for_verify, out_json)
    finalize_mod(
        output,
        out_json,
        custom_exlaunch_deploy=custom_exlaunch_deploy,
        map_icon_keys_json=out_keys,
    )
    # Optional offline dim reveal (default OFF; never fails the patch).
    maybe_reveal_minimap_save(enabled=reveal_minimap_save)

    log("\n" + "=" * 60)
    log("DONE - enable the mod in Ryujinx, start a NEW save, then:")
    log("  Launch_Dread_Client -> /connect ... -> /connect_dread")
    log("Quit Randovania Game Connection first if :6969 is busy.")
    log("=" * 60)
    return out_json


def main(argv: Optional[list[str]] = None) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Patch Metroid Bread for Archipelago without Randovania Export")
    parser.add_argument("--spoiler", type=Path, help="Path to AP *_Spoiler.txt")
    parser.add_argument("--seed-folder", type=Path, help="AP output folder containing a spoiler")
    parser.add_argument("--player", default=cfg.get("player_name", "DreadPlayer"))
    parser.add_argument(
        "--base-rom",
        type=Path,
        default=config_path(cfg, "base_rom_path", DEFAULT_BASE_ROM),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=config_path(cfg, "output_path", DEFAULT_RYUJINX_MOD),
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--clean", action="store_true", default=bool(cfg.get("clean_output")))
    parser.add_argument(
        "--freesink",
        action=argparse.BooleanOptionalAction,
        default=bool(cfg.get("freesink", False)),
        help="Allow free out-of-bounds movement (disables kill-outside-scenario)",
    )
    parser.add_argument(
        "--custom-exlaunch-deploy",
        type=Path,
        default=None,
        help="Folder with custom OdrMap subsdk9 (+ optional main.npdm) to overlay after ODR",
    )
    parser.add_argument(
        "--reveal-minimap-save",
        action=argparse.BooleanOptionalAction,
        default=bool(cfg.get("reveal_minimap_save", False)),
        help="After patch, dim-reveal fog in newest Ryujinx samus.bmssv (default: off)",
    )
    parser.add_argument(
        "--layout-uuid",
        default=None,
        help="Force layout_uuid (recover an existing save). Default: preserve prior "
        "AP_<player>_patcher.json or derive a stable uuid5 from seed+player.",
    )
    parser.add_argument("--write-config", action="store_true", help="Write dread_direct_patch_config.json from args")
    args = parser.parse_args(argv)

    deploy = args.custom_exlaunch_deploy
    if deploy is None:
        deploy = resolve_custom_exlaunch_deploy(cfg)
    elif not (deploy / "subsdk9").is_file():
        log(f"[WARN] --custom-exlaunch-deploy has no subsdk9: {deploy}")
        deploy = None

    if args.write_config:
        save_config(
            {
                "base_rom_path": str(args.base_rom),
                "output_path": str(args.output),
                "player_name": args.player,
                "clean_output": bool(args.clean),
                "freesink": bool(args.freesink),
                "custom_exlaunch_deploy": str(
                    args.custom_exlaunch_deploy
                    or cfg.get("custom_exlaunch_deploy")
                    or dread_paths.BUNDLED_EXLAUNCH_DEPLOY
                ).replace("\\", "/"),
                "reveal_minimap_save": bool(args.reveal_minimap_save),
            }
        )
        return 0

    spoiler = args.spoiler
    if spoiler is None:
        if args.seed_folder is None:
            parser.error("Provide --spoiler or --seed-folder")
        spoiler = find_spoiler(args.seed_folder)

    if not spoiler.is_file():
        raise PatchError(f"Spoiler not found: {spoiler}")

    if deploy is not None:
        log(f"[INFO] custom OdrMap exlaunch deploy: {deploy}")
    else:
        log("[WARN] no custom OdrMap exlaunch deploy — stock ODR subsdk9 will remain")

    patch_from_spoiler(
        spoiler,
        args.player,
        args.base_rom,
        args.output,
        template=args.template,
        clean_output=args.clean,
        freesink=bool(args.freesink),
        custom_exlaunch_deploy=deploy,
        reveal_minimap_save=bool(args.reveal_minimap_save),
        layout_uuid=args.layout_uuid,
    )
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
            sys.stderr.reconfigure(errors="replace")
        except Exception:
            pass
    try:
        raise SystemExit(main())
    except PatchError as e:
        log("\nFAILED")
        log(str(e))
        raise SystemExit(1)

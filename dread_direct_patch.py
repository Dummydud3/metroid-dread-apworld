#!/usr/bin/env python3
"""Archipelago Metroid Bread — Direct Patcher (bypasses Randovania Export UI)"""

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
DREAD_TITLE_ID = "010093801237c000"
DEFAULT_RYUJINX_MOD = Path(
    os.path.expandvars(rf"%APPDATA%\Ryujinx\mods\contents\{DREAD_TITLE_ID}")
)
# Atmosphere output root is the CFW folder (usually <SD>/atmosphere). ODR nests
DEFAULT_ATMOSPHERE_ROOT = Path("")
DEFAULT_BASE_ROM = Path(r"C:\Users\dummy\Downloads\md rando")
# This is the exlaunch project's Makefile `OUT` directory (see OUT in
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
        "ryujinx_output_path": str(DEFAULT_RYUJINX_MOD),
        "atmosphere_output_path": "",
        "mod_compatibility": "ryujinx",
        "player_name": "DreadPlayer",
        "clean_output": False,
        "freesink": False,
        # Prefer world-relative deploy (apworld / Hub runtime). Absolute local
        "custom_exlaunch_deploy": str(dread_paths.BUNDLED_EXLAUNCH_DEPLOY).replace("\\", "/"),
        # Offline samus.bmssv dim reveal — OFF (bright path is VisitBoundsSafe in-game).
        "reveal_minimap_save": False,
    }
    cfg.update(dread_paths.load_patch_config(ROOT))
    cfg["mod_compatibility"] = normalize_mod_compatibility(
        cfg.get("mod_compatibility")
    )
    # Keep dual-path memory in sync with the active output_path.
    compat = cfg["mod_compatibility"]
    out = str(cfg.get("output_path") or "").strip()
    if compat == "atmosphere":
        if out and not str(cfg.get("atmosphere_output_path") or "").strip():
            cfg["atmosphere_output_path"] = out
        if not str(cfg.get("ryujinx_output_path") or "").strip():
            cfg["ryujinx_output_path"] = str(DEFAULT_RYUJINX_MOD)
    else:
        if out and not str(cfg.get("ryujinx_output_path") or "").strip():
            cfg["ryujinx_output_path"] = out
        if not str(cfg.get("ryujinx_output_path") or "").strip():
            cfg["ryujinx_output_path"] = str(DEFAULT_RYUJINX_MOD)
    return cfg


def normalize_mod_compatibility(value: Optional[str]) -> str:
    raw = (value or "ryujinx").strip().lower()
    if raw in ("atmosphere", "atmos", "cfw", "switch", "hardware"):
        return "atmosphere"
    return "ryujinx"


def mod_layout_paths(output: Path, compatibility: str) -> Dict[str, Path]:
    """Resolve romfs / exefs / IPS dirs the same way open-dread-rando does."""
    compat = normalize_mod_compatibility(compatibility)
    if compat == "atmosphere":
        mod_root = output / "contents" / DREAD_TITLE_ID
        return {
            "compatibility": compat,
            "mod_root": mod_root,
            "romfs": mod_root / "romfs",
            "exefs": mod_root / "exefs",
            "exefs_patches": output / "exefs_patches" / "DreadRandovania",
        }
    mod_root = output / "DreadRandovania"
    return {
        "compatibility": compat,
        "mod_root": mod_root,
        "romfs": mod_root / "romfs",
        "exefs": mod_root / "exefs",
        "exefs_patches": mod_root / "exefs",
    }


def clean_mod_output(output: Path, compatibility: str) -> None:
    """Remove previous Metroid Bread / Randovania mod files only."""
    compat = normalize_mod_compatibility(compatibility)
    if compat == "atmosphere":
        targets = [
            output / "contents" / DREAD_TITLE_ID,
            output / "exefs_patches" / "DreadRandovania",
        ]
        for path in targets:
            if path.exists():
                log(f"[INFO] Cleaning Atmosphere mod path: {path}")
                shutil.rmtree(path, ignore_errors=True)
        return

    dread = output / "DreadRandovania"
    if dread.exists():
        log(f"[INFO] Cleaning Ryujinx mod path: {dread}")
        shutil.rmtree(dread, ignore_errors=True)
        return
    # Legacy flat layout under the title folder.
    for name in ("romfs", "exefs"):
        path = output / name
        if path.exists():
            log(f"[INFO] Cleaning legacy Ryujinx path: {path}")
            shutil.rmtree(path, ignore_errors=True)


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
    """Optionally reveal minimap fog in the newest Ryujinx profile save."""
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
    """Re-install custom OdrMap exlaunch over stock ODR exefs after patching."""
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
    mod_compatibility: Optional[str] = None,
) -> None:
    """Enable remote Lua and set the Metroid Bread AP title screen string."""
    patcher_data["enable_remote_lua"] = True
    # Always set layout target (Hub/CLI may override ap_to_patcher's default).
    compat = normalize_mod_compatibility(
        mod_compatibility
        if mod_compatibility is not None
        else patcher_data.get("mod_compatibility")
    )
    patcher_data["mod_compatibility"] = compat
    patcher_data["mod_category"] = patcher_data.get("mod_category") or "romfs"
    from ap_to_patcher import apply_company_title_screen

    title = apply_company_title_screen(
        patcher_data, seed_id=seed_id, spoiler_path=spoiler_path
    )
    log(f"[OK] Title screen: {title.replace(chr(10), ' / ')}")
    ap_seed = str(patcher_data.get("_ap_seed_id") or "").strip()
    if ap_seed:
        log(f"[OK] AP seed id for mismatch guard: {ap_seed}")
    log(f"[OK] mod_compatibility={compat}")


def apply_freesink(patcher_data: dict, enabled: bool) -> None:
    """Randovania freesink → cosmetic_patches.config.SubAreaManager.bKillPlayerOutsideScenario."""
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
    """Keep the jsonschema *message* visible when the dump is enormous."""
    err = (err or "").strip()
    if not err:
        return "(no error output)"
    if len(err) <= head + tail + 40:
        return err
    return f"{err[:head]}\n\n...[truncated {len(err) - head - tail} chars]...\n\n{err[-tail:]}"


def _summarize_jsonschema_error(exc: BaseException) -> str:
    """Prefer path + short message over dumping the whole pickups array."""
    message = getattr(exc, "message", None)
    path = getattr(exc, "absolute_path", None)
    validator = getattr(exc, "validator", None)
    if message is None:
        return _format_odr_validation_error(str(exc))
    path_list = list(path) if path is not None else []
    path_s = "$" + "".join(f"[{p!r}]" if isinstance(p, int) else f".{p}" for p in path_list)
    bits = [f"{path_s}: {message}"]
    if validator is not None:
        bits.append(f"(validator={validator!r} value={getattr(exc, 'validator_value', None)!r})")
    # oneOf / anyOf context often has the real reason.
    context = getattr(exc, "context", None) or ()
    for i, sub in enumerate(context[:6]):
        sub_path = list(getattr(sub, "absolute_path", []) or [])
        sub_s = "$" + "".join(
            f"[{p!r}]" if isinstance(p, int) else f".{p}" for p in sub_path
        )
        bits.append(f"  context[{i}] {sub_s}: {getattr(sub, 'message', sub)}")
    return "\n".join(bits)


def validate_patcher_json(patcher_data: dict) -> None:
    """Fail fast with a clear error if open-dread-rando would reject the JSON."""
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
            f"{_summarize_jsonschema_error(e)}"
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
    """Fail the patch if written brfld transporter targets ≠ patcher.json."""
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
    """Register a system/scripts/<stem>.{lua,lc} so Game.DoFile('….lua') works."""
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
    """Overwrite ODR's minimap icons.bctex with the AP-stamped atlas."""
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
-- ZR+close menu / ZR+DPAD_RIGHT = last Save/Network/Map station.
Game.DoFile("system/scripts/ap_warp.lua")
if ApWarp and ApWarp.Install then
    ApWarp.Install()
end
""".lstrip()

AP_ELUN_ARRIVAL_GATE_MARKER = "-- AP_ELUN_ARRIVAL_GATE"
AP_ELUN_ARRIVAL_GATE_BOOTSTRAP = """
-- AP_ELUN_ARRIVAL_GATE
-- Transport-rando / ApWarp: restore Elun arrival seal (ev_gatesealed_second) on load.
-- Install after ApWarp so OnLoadScenarioFinished / CheckDebugInputs chain correctly.
Game.DoFile("system/scripts/ap_elun_arrival_gate.lua")
if ApElunArrivalGate and ApElunArrivalGate.Install then
    ApElunArrivalGate.Install()
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

AP_SEED_ID_MARKER = "-- AP_SEED_ID"
# Placeholder {seed} is filled by install_ap_seed_id_bootstrap().
AP_SEED_ID_BOOTSTRAP_TEMPLATE = """
-- AP_SEED_ID
-- Baked Archipelago seed digits for Hub client mismatch checks (vs RoomInfo.seed_name).
Init.sApSeedId = "{seed}"
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

_AP_ELUN_ARRIVAL_GATE_BLOCK_RE = re.compile(
    r"\n*-- AP_ELUN_ARRIVAL_GATE\n"
    r"(?:.*\n)*?"
    r"if ApElunArrivalGate and ApElunArrivalGate\.Install then\n"
    r"\s*ApElunArrivalGate\.Install\(\)\n"
    r"end\n?",
    re.MULTILINE,
)

# ODR ≥2.19 death-only HUD: move DeathCounter into the DNA row of ExtraInfoPanel.
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
    """Remove ProgressKeeper / HkAutosave bootstrap from scenario.lc."""
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
    """Make ODR ≥2.19 death-only HUD match DNA-slot placement without runtime getters."""
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


def install_ap_elun_arrival_gate_scripts(romfs: Path) -> None:
    """Restore Elun arrival gate on load (transport rando + ApWarp softlock)."""
    src = dread_paths.dread_scripts_dir() / "ap_elun_arrival_gate.lua"
    if not src.is_file():
        raise PatchError(f"missing Elun arrival-gate script: {src}")
    _register_system_script_asset(romfs, "ap_elun_arrival_gate", src.read_bytes())
    _patch_scenario_for_ap_elun_arrival_gate(romfs)


def _patch_scenario_for_ap_elun_arrival_gate(romfs: Path) -> None:
    """Install ApElunArrivalGate bootstrap at EOF of scenario.lc (after ApWarp)."""
    existing, pkg = _read_scenario_lc(romfs)
    text = existing.decode("utf-8", errors="replace")
    if AP_ELUN_ARRIVAL_GATE_MARKER in text:
        relocated = _AP_ELUN_ARRIVAL_GATE_BLOCK_RE.sub("\n", text)
        if relocated == text:
            log("[WARN] ApElunArrivalGate marker found but block could not be relocated")
            return
        text = relocated
        log("[OK] removed prior ApElunArrivalGate bootstrap (will re-append at EOF)")

    text = text.rstrip() + "\n\n" + AP_ELUN_ARRIVAL_GATE_BOOTSTRAP
    data = text.encode("utf-8")
    _write_scenario_lc(romfs, data, pkg)
    log(f"[OK] patched scenario.lc with ApElunArrivalGate.Install at EOF ({len(data)} bytes)")


def _patch_scenario_for_ap_warp(romfs: Path) -> None:
    """Install ApWarp bootstrap at the END of scenario.lc."""
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
    """Install ForcedTooltip tip injector + tip pool + wire DoFile/Install into init.lc."""
    scripts = dread_paths.dread_scripts_dir()
    tips_src = scripts / "ap_loading_tips.lua"
    pool_src = scripts / "ap_tip_pool.lua"
    if not tips_src.is_file():
        raise PatchError(f"missing ApLoadingTips script: {tips_src}")
    _register_system_script_asset(romfs, "ap_loading_tips", tips_src.read_bytes())
    if pool_src.is_file():
        _register_system_script_asset(romfs, "ap_tip_pool", pool_src.read_bytes())
        log(f"[OK] installed ap_tip_pool.lua ({pool_src.stat().st_size} bytes)")
    else:
        log(f"[WARN] missing tip pool script: {pool_src}")
    _patch_init_for_ap_loading_tips(romfs)
    _patch_scenario_for_ap_loading_tips(romfs)


def _patch_init_for_ap_loading_tips(romfs: Path) -> None:
    """Append ApLoadingTips bootstrap at EOF of init.lc (idempotent)."""
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


def _escape_lua_string(value: str) -> str:
    """Escape a value for use inside a double-quoted Lua string literal."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def install_ap_seed_id_bootstrap(romfs: Path, ap_seed_id: str | None) -> None:
    """Bake Init.sApSeedId into init.lc so the Hub client can compare RoomInfo.seed_name"""
    seed = (ap_seed_id or "").strip()
    existing, pkg = _read_init_lc(romfs)
    text = existing.decode("utf-8", errors="replace")
    if AP_SEED_ID_MARKER in text:
        idx = text.find(AP_SEED_ID_MARKER)
        text = text[:idx].rstrip() + "\n"
        log("[OK] removed prior AP seed id bootstrap from init.lc")

    if not seed:
        data = text.encode("utf-8")
        _write_init_lc(romfs, data, pkg)
        log("[WARN] no AP seed id to bake — Init.sApSeedId not set")
        return

    bootstrap = AP_SEED_ID_BOOTSTRAP_TEMPLATE.format(seed=_escape_lua_string(seed))
    text = text.rstrip() + "\n\n" + bootstrap
    data = text.encode("utf-8")
    _write_init_lc(romfs, data, pkg)
    log(f"[OK] baked Init.sApSeedId={seed!r} into init.lc ({len(data)} bytes)")


_STATION_WARP_LOCALES = (
    "eu_dutch.txt",
    "eu_french.txt",
    "eu_german.txt",
    "eu_italian.txt",
    "eu_spanish.txt",
    "japanese.txt",
    "korean.txt",
    "russian.txt",
    "simplified_chinese.txt",
    "traditional_chinese.txt",
    "us_english.txt",
    "us_french.txt",
    "us_spanish.txt",
)
STATION_WARP_MSG_KEY = "GUI_AP_STATION_WARP"
STATION_WARP_MSG_TEXT = "Warp to this station?"
# U+1800 is the A-button logo used by GUI_GENERAL_LABEL_ACCEPT.
STATION_WARP_OK_KEY = "GUI_AP_STATION_OK"
STATION_WARP_OK_TEXT = "\u1800 OK"
_AP_STATION_WARP_MARKER = "-- AP_STATION_WARP"
_AP_STATION_WARP_END = "-- AP_STATION_WARP_END"
_AP_STATION_WARP_FLAG_MARKER = "-- AP_STATION_WARP_FLAG"
_AP_STATION_WARP_FLAG_END = "-- AP_STATION_WARP_FLAG_END"
_AP_STATION_WARP_BOOTSTRAP = """
-- AP_STATION_WARP
-- Pause-map warp. Loaded only when Init.bStationMapWarp is true.
if Init and Init.bStationMapWarp == true then
  Game.DoFile("system/scripts/ap_station_warp.lua")
  if ApStationWarp and ApStationWarp.Install then
    ApStationWarp.Install()
  end
end
-- AP_STATION_WARP_END
""".lstrip()


def _normalize_station_warp_mode(requirement: str, reach: str) -> tuple[str, str]:
    """Clamp baked modes to the strings ap_station_warp.lua reads."""
    req = str(requirement or "visited").strip().lower()
    rch = str(reach or "global").strip().lower()
    if req not in ("visible", "visited"):
        req = "visited"
    if rch not in ("local", "global"):
        rch = "global"
    return req, rch


def _station_warp_flag_bootstrap(requirement: str, reach: str) -> str:
    """Init flags the warp script reads. Written only when the warp is enabled."""
    req, rch = _normalize_station_warp_mode(requirement, reach)
    return (
        "-- AP_STATION_WARP_FLAG\n"
        "Init.bStationMapWarp = true\n"
        f'Init.sStationWarpRequirement = "{_escape_lua_string(req)}"\n'
        f'Init.sStationWarpReach = "{_escape_lua_string(rch)}"\n'
        "-- AP_STATION_WARP_FLAG_END\n"
    )


def _strip_inclusive_markers(text: str, start: str, end: str) -> str:
    """Drop every start..end block, including the marker lines."""
    while True:
        i = text.find(start)
        if i < 0:
            return text
        j = text.find(end, i + len(start))
        if j < 0:
            return text[:i].rstrip() + "\n"
        j2 = j + len(end)
        if j2 < len(text) and text[j2] == "\n":
            j2 += 1
        text = text[:i] + text[j2:]


def _write_station_warp_localization(romfs: Path) -> int:
    """Add the confirm-dialogue string. LaunchMessage looks this key up in the bank."""
    try:
        from mercury_engine_data_structures.formats.txt import Txt
        from mercury_engine_data_structures.game_check import Game
    except ImportError as exc:
        log(f"[WARN] station warp text skipped (mercury missing): {exc}")
        return 0

    loc_dir = romfs / "system" / "localization"
    if not loc_dir.is_dir():
        log(f"[WARN] station warp text skipped; missing {loc_dir}")
        return 0

    writes = 0
    for name in _STATION_WARP_LOCALES:
        path = loc_dir / name
        if not path.is_file():
            continue
        try:
            txt = Txt.parse(path.read_bytes(), target_game=Game.DREAD)
        except Exception as exc:
            log(f"[WARN] station warp text skipped {name}: {exc}")
            continue
        changed = False
        if txt.strings.get(STATION_WARP_MSG_KEY) != STATION_WARP_MSG_TEXT:
            txt.strings[STATION_WARP_MSG_KEY] = STATION_WARP_MSG_TEXT
            changed = True
        if txt.strings.get(STATION_WARP_OK_KEY) != STATION_WARP_OK_TEXT:
            txt.strings[STATION_WARP_OK_KEY] = STATION_WARP_OK_TEXT
            changed = True
        if not changed:
            continue
        path.write_bytes(txt.build())
        writes += 1
    log(f"[OK] station warp dialogue string written to {writes} localization file(s)")
    return writes


def install_station_map_warp(
    romfs: Path,
    enabled: bool,
    requirement: str = "visited",
    reach: str = "global",
) -> None:
    """Install pause-map station warp, or remove its bootstraps when the YAML option is off.

    When enabled, also bake Init.sStationWarpRequirement and Init.sStationWarpReach.
    The script is still registered only while the master toggle is on.
    """
    try:
        scenario_bytes, scenario_pkg = _read_scenario_lc(romfs)
    except PatchError as exc:
        log(f"[WARN] station map warp skipped: {exc}")
        return

    scenario_text = _strip_inclusive_markers(
        scenario_bytes.decode("utf-8", errors="replace"),
        _AP_STATION_WARP_MARKER,
        _AP_STATION_WARP_END,
    )
    if enabled:
        scenario_text = scenario_text.rstrip() + "\n\n" + _AP_STATION_WARP_BOOTSTRAP
    scenario_data = scenario_text.encode("utf-8")
    _write_scenario_lc(romfs, scenario_data, scenario_pkg)

    try:
        init_bytes, init_pkg = _read_init_lc(romfs)
    except PatchError as exc:
        log(f"[WARN] station map warp init flag skipped: {exc}")
        return
    init_text = _strip_inclusive_markers(
        init_bytes.decode("utf-8", errors="replace"),
        _AP_STATION_WARP_FLAG_MARKER,
        _AP_STATION_WARP_FLAG_END,
    )
    req, rch = _normalize_station_warp_mode(requirement, reach)
    if enabled:
        init_text = init_text.rstrip() + "\n\n" + _station_warp_flag_bootstrap(req, rch)
    init_data = init_text.encode("utf-8")
    # Write init before registering the lua asset. _write_init_lc rebuilds system.pkg
    # from the snapshot it was parsed from, which would drop a script added first.
    _write_init_lc(romfs, init_data, init_pkg)

    if enabled:
        src = dread_paths.dread_scripts_dir() / "ap_station_warp.lua"
        if not src.is_file():
            raise PatchError(f"missing station warp script: {src}")
        _register_system_script_asset(romfs, "ap_station_warp", src.read_bytes())
        _write_station_warp_localization(romfs)
        log(
            "[OK] pause-map station warp installed "
            f"(Init.bStationMapWarp, requirement={req}, reach={rch})"
        )
    else:
        log("[OK] pause-map station warp off — bootstraps removed, script not loaded")


_AP_MAP_LOGIC_MARKER = "-- AP_MAP_LOGIC"
_AP_MAP_LOGIC_END = "-- AP_MAP_LOGIC_END"
_AP_MAP_LOGIC_BOOTSTRAP = """
-- AP_MAP_LOGIC
pcall(function()
  Game.DoFile("system/scripts/ap_map_logic.lua")
  Game.DoFile("system/scripts/ap_map_logic_rows.lua")
end)
-- AP_MAP_LOGIC_END
""".lstrip()

# Seed fields the pause-map catalog reads besides logic_options.
_MAP_LOGIC_OPTION_KEYS = (
    "starting_missiles",
    "starting_power_bombs",
    "start_with_pulse_radar",
    "missile_tank_ammo",
    "missile_plus_tank_ammo",
    "power_bomb_tank_ammo",
    "energy_per_tank",
    "required_dna",
    "vanilla_flash_shift_behaviour",
    "flash_shift_upgrade_amount",
    "flash_shift_upgrade_count",
    "flash_shift_included_ammo",
    "flash_shift_upgrade_requires_main_item",
)


def map_logic_option_values(extras: dict) -> dict:
    """Trickset and starting-gear values for the pause-map catalog."""
    values: Dict[str, Any] = {}
    logic = extras.get("logic_options") if isinstance(extras, dict) else None
    if isinstance(logic, dict):
        values.update(logic)
    if isinstance(extras, dict):
        for key in _MAP_LOGIC_OPTION_KEYS:
            if key in extras and extras[key] is not None:
                values[key] = extras[key]
    if "start_with_pulse_radar" in values:
        values["start_with_pulse_radar"] = 1 if values["start_with_pulse_radar"] else 0
    return values


def render_map_logic_rows_lua(rows: list) -> bytes:
    """Lua that fills ApMapLogic.rows. The tick script loads before this file."""
    body = [
        "ApMapLogic = ApMapLogic or { rows = {}, snap = 800, _bound = false }",
        "ApMapLogic.rows = {",
    ]
    for row in rows:
        abilities = ", ".join(
            '"' + _escape_lua_string(str(item)) + '"'
            for item in (row.get("lines") or [])
        )
        body.append(
            '  {s="%s",x=%d,y=%d,area="%s",t={%s}},'
            % (
                _escape_lua_string(str(row["scenario"])),
                int(row["x"]),
                int(row["y"]),
                _escape_lua_string(str(row.get("area") or "")),
                abilities,
            )
        )
    body.append("}")
    body.append("")
    return "\n".join(body).encode("utf-8")


def build_map_logic_rows_lua(extras: dict) -> bytes:
    """Catalog every pickup once. Call this at patch time, not per check."""
    from worlds.metroid_bread.dread_logic import map_panel_rows

    rows = map_panel_rows(map_logic_option_values(extras))
    if not rows:
        raise PatchError("pause-map catalog produced no pickup rows")
    return render_map_logic_rows_lua(rows)


def install_map_logic_panel(romfs: Path, rows_lua: bytes | None) -> None:
    """Show minimum check abilities in the pause-map tip lines on the next boot."""
    if not rows_lua:
        log("[WARN] pause-map check lines skipped — no catalog")
        return
    src = dread_paths.dread_scripts_dir() / "ap_map_logic.lua"
    if not src.is_file():
        log(f"[WARN] pause-map check lines skipped — missing {src}")
        return
    try:
        scenario_bytes, scenario_pkg = _read_scenario_lc(romfs)
    except PatchError as exc:
        log(f"[WARN] pause-map check lines skipped: {exc}")
        return
    scenario_text = _strip_inclusive_markers(
        scenario_bytes.decode("utf-8", errors="replace"),
        _AP_MAP_LOGIC_MARKER,
        _AP_MAP_LOGIC_END,
    )
    scenario_text = scenario_text.rstrip() + "\n\n" + _AP_MAP_LOGIC_BOOTSTRAP
    # Write scenario before registering scripts. A later pkg rewrite from an
    # older snapshot would drop the bootstrap.
    _write_scenario_lc(romfs, scenario_text.encode("utf-8"), scenario_pkg)
    _register_system_script_asset(romfs, "ap_map_logic", src.read_bytes())
    _register_system_script_asset(romfs, "ap_map_logic_rows", rows_lua)
    log(f"[OK] pause-map check lines installed ({len(rows_lua)} byte catalog)")


_AP_MIN_LIFE_MARKER = "-- AP_MIN_LIFE"
_AP_MIN_LIFE_END = "-- AP_MIN_LIFE_END"
_AP_MIN_LIFE_BOOTSTRAP = """
-- AP_MIN_LIFE
-- Floor scenario entry and save snapshots at 1 HP. Loaded last so this
-- OnLoadScenarioFinished wrapper runs outside ApWarp / station warp.
Game.DoFile("system/scripts/ap_min_life.lua")
if ApMinLife and ApMinLife.Install then
    ApMinLife.Install()
end
-- AP_MIN_LIFE_END
""".lstrip("\n")


def install_ap_min_life_scripts(romfs: Path) -> None:
    """Keep checkpoint / save-slot energy at least 1 after a cinematic DeathLink."""
    src = dread_paths.dread_scripts_dir() / "ap_min_life.lua"
    if not src.is_file():
        log(f"[WARN] min-life skipped — missing {src}")
        return
    try:
        scenario_bytes, scenario_pkg = _read_scenario_lc(romfs)
    except PatchError as exc:
        log(f"[WARN] min-life skipped: {exc}")
        return
    text = _strip_inclusive_markers(
        scenario_bytes.decode("utf-8", errors="replace"),
        _AP_MIN_LIFE_MARKER,
        _AP_MIN_LIFE_END,
    )
    text = text.rstrip() + "\n\n" + _AP_MIN_LIFE_BOOTSTRAP
    # Scenario bootstrap first, then the DoFile asset, so a later pkg rewrite
    # re-reads the scenario that already calls the script.
    _write_scenario_lc(romfs, text.encode("utf-8"), scenario_pkg)
    _register_system_script_asset(romfs, "ap_min_life", src.read_bytes())
    log(f"[OK] min-life floors scenario entry and save slots ({src.stat().st_size} bytes)")


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
    """Post-process ODR credits.txt:"""
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
    mod_compatibility: str = "ryujinx",
    ap_seed_id: Optional[str] = None,
    station_map_warp: bool = False,
    station_warp_requirement: str = "visited",
    station_warp_reach: str = "global",
    map_logic_rows_lua: bytes | None = None,
) -> None:
    """Copy client-facing extras into the mod tree (Ryujinx or Atmosphere layout)."""
    layout = mod_layout_paths(output, mod_compatibility)
    compat = layout["compatibility"]
    mod_root = layout["mod_root"]
    # Prefer ODR's layout paths; fall back if the patcher wrote a legacy tree.
    romfs_parent = mod_root
    for c in (mod_root, output / "DreadRandovania", output / "contents" / DREAD_TITLE_ID, output):
        if (c / "romfs").is_dir() or (c / "exefs").is_dir():
            romfs_parent = c
            break
    log(
        f"[INFO] finalize_mod layout={compat} "
        f"mod_root={mod_root} romfs_parent={romfs_parent}"
    )

    # Always keep a copy of patcher.json next to the mod for debugging / UUID
    dst_json = romfs_parent / "patcher.json"
    shutil.copy2(patcher_json, dst_json)
    log(f"[OK] patcher.json -> {dst_json}")

    # Sidecar for Hub / tooling (same digits baked into Init.sApSeedId).
    seed_for_sidecar = (ap_seed_id or "").strip()
    if not seed_for_sidecar:
        try:
            with open(patcher_json, encoding="utf-8") as f:
                pdata_seed = json.load(f)
            if isinstance(pdata_seed, dict):
                seed_for_sidecar = str(pdata_seed.get("_ap_seed_id") or "").strip()
        except (OSError, json.JSONDecodeError, TypeError):
            seed_for_sidecar = ""
    if seed_for_sidecar:
        ap_seed_path = romfs_parent / "ap_seed.json"
        ap_seed_path.write_text(
            json.dumps({"ap_seed_id": seed_for_sidecar}, indent=2) + "\n",
            encoding="utf-8",
        )
        log(f"[OK] ap_seed.json -> {ap_seed_path} ({seed_for_sidecar!r})")
        ap_seed_id = seed_for_sidecar

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

    # Elun re-entry: ForceOpen ev_gatesealed_second (ApWarp / transport rando).
    install_ap_elun_arrival_gate_scripts(romfs)

    # ForcedTooltip on Continue / New Game loading screens (init.lc, early).
    install_ap_loading_tips_scripts(romfs)

    # Bake AP seed digits for Hub client seed-mismatch checks (RoomInfo vs RomFS).
    install_ap_seed_id_bootstrap(romfs, ap_seed_id)

    # Pause-map warp. Off: script is not loaded. On: bake requirement and reach too.
    install_station_map_warp(
        romfs,
        station_map_warp,
        requirement=station_warp_requirement,
        reach=station_warp_reach,
    )

    # Pause-map tip lines: minimum abilities for the hovered check.
    install_map_logic_panel(romfs, map_logic_rows_lua)

    # Death-only ExtraInfoPanel: park counter on ODR DNA-slot coords (no Ryujinx getters).
    fix_death_counter_hud_position(romfs)

    # DeathLink during a save / transport must not persist 0 HP. Last so the
    # scenario-enter wrapper sits outside the other OnLoad hooks.
    install_ap_min_life_scripts(romfs)

    # Reachable minimap offline data (bounds for OdrMap.VisitBounds).
    map_src_lua = ROOT / "data" / "reachable_map_cells.lua"
    install_reachable_map_script(romfs, map_src_lua)
    install_map_unlock_region_script(romfs)

    # Archipelago logo + green in-logic ? cells in the minimap atlas
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

    exefs = layout["exefs"]
    # If ODR wrote exefs under a different parent, prefer that tree's exefs
    discovered = romfs_parent / "exefs"
    if discovered.is_dir():
        exefs = discovered
    if exefs.is_dir():
        subsdk = list(exefs.glob("subsdk*"))
        log(f"[OK] exefs present at {exefs} ({len(subsdk)} subsdk* file(s))")
    else:
        log(f"[WARN] exefs/ not found — creating {exefs} for custom OdrMap overlay")
        exefs.mkdir(parents=True, exist_ok=True)

    # ODR writes stock remote-lua exlaunch; overlay custom OdrMap binders when available.
    log(f"[INFO] Installing custom OdrMap/OdrTip subsdk9 -> {exefs} ({compat})")
    install_custom_exlaunch(exefs, custom_exlaunch_deploy)
    log(
        "[OK] finalize_mod complete: ApWarp + ApLoadingTips + TOC/pkg map script + "
        f"AP map-icon atlas + custom OdrMap exefs ({compat}; enable_remote_lua kept on)"
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
    mod_compatibility: str = "ryujinx",
) -> Path:
    compat = normalize_mod_compatibility(mod_compatibility)
    layout = mod_layout_paths(output, compat)
    log("=" * 60)
    log("Archipelago Dread Direct Patcher")
    log(f"(spoiler -> patcher.json -> open-dread-rando -> {compat} mod)")
    log("=" * 60)
    log(f"Spoiler : {spoiler}")
    log(f"Player  : {player}")
    log(f"Base ROM: {base_rom}")
    log(f"Output  : {output}")
    log(f"Layout  : {compat} (romfs={layout['romfs']}, exefs={layout['exefs']})")
    log(f"Freesink: {freesink}")

    if clean_output:
        # Never rmtree the whole Atmosphere CFW root — only known mod subtrees.
        clean_mod_output(output, compat)

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
    ensure_remote_lua(
        patcher_data, spoiler_path=spoiler, mod_compatibility=compat
    )
    apply_freesink(patcher_data, freesink)

    py = find_python_with_odr()
    log(f"Using Python with open-dread-rando: {' '.join(py)}")

    # Match patcher.json to the validating ODR schema (show_dna_in_hud /
    from ap_to_patcher import apply_upgrade_menu_flags, sanitize_patcher_for_odr

    apply_upgrade_menu_flags(patcher_data, py_cmd=py)
    # Capture AP-private keys before schema sanitize / dump (ODR rejects them).
    ap_seed_id = str(patcher_data.pop("_ap_seed_id", "") or "").strip() or None
    station_map_warp = bool(patcher_data.pop("_ap_station_map_warp", False))
    station_warp_requirement = str(
        patcher_data.pop("_ap_station_warp_requirement", "visited") or "visited"
    )
    station_warp_reach = str(
        patcher_data.pop("_ap_station_warp_reach", "global") or "global"
    )
    map_logic_rows_lua = b""
    try:
        from ap_to_patcher import parse_dread_patch_extras

        log("[INFO] building pause-map check lines")
        map_logic_rows_lua = build_map_logic_rows_lua(
            parse_dread_patch_extras(spoiler, player)
        )
        log(f"[OK] pause-map catalog {len(map_logic_rows_lua)} bytes")
    except Exception as exc:
        log(f"[WARN] pause-map check lines not built: {exc}")
        map_logic_rows_lua = b""
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
                "import json,sys;\n"
                "from pathlib import Path;\n"
                "import open_dread_rando;\n"
                "from open_dread_rando.validator_with_default import "
                "DefaultValidatingDraft7Validator;\n"
                "schema=json.load(open("
                "Path(open_dread_rando.__file__).resolve().parent/'files'/'schema.json',"
                "encoding='utf-8'));\n"
                "data=json.load(open(sys.argv[1],encoding='utf-8'));\n"
                "print(f'AP_PICKUPS={len(data.get(\"pickups\") or [])}');\n"
                "try:\n"
                " DefaultValidatingDraft7Validator(schema).validate(data);\n"
                " print('SCHEMA_OK')\n"
                "except Exception as e:\n"
                " msg=getattr(e,'message',str(e));\n"
                " path='.'.join(str(p) for p in list(getattr(e,'absolute_path',[]) or [])) or '$';\n"
                " print(f'SCHEMA_FAIL path={path} validator={getattr(e,\"validator\",None)} msg={msg}', file=sys.stderr);\n"
                " raise\n"
            ),
            str(out_json),
        ],
        capture_output=True,
        text=True,
    )
    if val.stdout:
        for line in val.stdout.strip().splitlines():
            log(f"[INFO] {line}")
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
    # Prefer the active layout; also accept the other platform / legacy paths.
    romfs_candidates = [
        layout["romfs"],
        output / "contents" / DREAD_TITLE_ID / "romfs",
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
        mod_compatibility=compat,
        ap_seed_id=ap_seed_id,
        station_map_warp=station_map_warp,
        station_warp_requirement=station_warp_requirement,
        station_warp_reach=station_warp_reach,
        map_logic_rows_lua=map_logic_rows_lua,
    )
    # Optional offline dim reveal (default OFF; never fails the patch).
    maybe_reveal_minimap_save(enabled=reveal_minimap_save)

    log("\n" + "=" * 60)
    if compat == "atmosphere":
        log("DONE - Atmosphere layout ready under your CFW root:")
        log(f"  romfs/exefs : {layout['romfs'].parent}")
        log(f"  IPS patches : {layout['exefs_patches']}")
        log("  Confirm custom subsdk9 is in contents/<tid>/exefs/ (OdrMap/OdrTip).")
        log("Copy/sync to the Switch SD if needed, reboot, start a NEW save, then:")
        log("  Launch_Dread_Client -> set Switch IP -> /connect ... -> /connect_dread")
    else:
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
    parser.add_argument(
        "--mod-compatibility",
        choices=["ryujinx", "atmosphere"],
        default=normalize_mod_compatibility(cfg.get("mod_compatibility")),
        help="Output layout: Ryujinx DreadRandovania/ vs Atmosphere contents/<tid>/",
    )
    parser.add_argument("--write-config", action="store_true", help="Write dread_direct_patch_config.json from args")
    args = parser.parse_args(argv)

    deploy = args.custom_exlaunch_deploy
    if deploy is None:
        deploy = resolve_custom_exlaunch_deploy(cfg)
    elif not (deploy / "subsdk9").is_file():
        log(f"[WARN] --custom-exlaunch-deploy has no subsdk9: {deploy}")
        deploy = None

    compat = normalize_mod_compatibility(args.mod_compatibility)
    if args.write_config:
        out_s = str(args.output)
        ryujinx_out = str(cfg.get("ryujinx_output_path") or DEFAULT_RYUJINX_MOD)
        atmosphere_out = str(cfg.get("atmosphere_output_path") or "")
        if compat == "atmosphere":
            atmosphere_out = out_s
        else:
            ryujinx_out = out_s
        save_config(
            {
                "base_rom_path": str(args.base_rom),
                "output_path": out_s,
                "ryujinx_output_path": ryujinx_out,
                "atmosphere_output_path": atmosphere_out,
                "mod_compatibility": compat,
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
        mod_compatibility=compat,
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

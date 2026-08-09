#!/usr/bin/env python3
"""
Path helpers for the Metroid Dread client / direct patcher.

Canonical layout (after client↔world merge):
  worlds/metroid_dread/          ← WORLD_DIR (this package)
    MetroidDreadClient.py
    dread_direct_patch.py
    dread-client-app/
    ap_core/                     ← bundled import root for frozen installs
    dread_scripts/
    *.json data next to the scripts
  <Archipelago root>/            ← install root (source *or* frozen ProgramData)
    CommonClient.py (source) or lib/library.zip (frozen), tools/, …

dread_direct_patch_config.json may hold absolute paths, %APPDATA% values, or
paths relative to WORLD_DIR so the portable package stays movable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

AP_CORE_DIRNAME = "ap_core"


def _is_source_ap_root(candidate: Path) -> bool:
    """True when *candidate* is a filesystem Archipelago root with loose core modules."""
    try:
        return (candidate / "CommonClient.py").is_file() and (candidate / "Options.py").is_file()
    except OSError:
        return False


def _is_frozen_ap_install(candidate: Path) -> bool:
    """
    True for an official frozen Archipelago install (no loose CommonClient.py).

    Typical layout: ArchipelagoLauncher.exe + lib/library.zip (+ python3xx.dll).
    """
    try:
        if _is_source_ap_root(candidate):
            return False
        lib_zip = candidate / "lib" / "library.zip"
        if not lib_zip.is_file():
            return False
        # Prefer a clear launcher/exe signal so random folders with a zip don't match.
        markers = (
            "ArchipelagoLauncher.exe",
            "ArchipelagoGenerate.exe",
            "ArchipelagoServer.exe",
            "python313.dll",
            "python312.dll",
            "python311.dll",
            "manifest.json",
        )
        return any((candidate / name).is_file() for name in markers)
    except OSError:
        return False


def bundled_ap_core(world_dir: Optional[Path] = None) -> Optional[Path]:
    """Loose CommonClient import root shipped inside the world / runtime extract."""
    base = (world_dir or Path(__file__).resolve().parent).resolve()
    core = base / AP_CORE_DIRNAME
    if _is_source_ap_root(core):
        return core
    return None


def resolve_frozen_install_root(world_dir: Optional[Path] = None) -> Optional[Path]:
    """Nearest frozen Archipelago install folder, or None."""
    base = (world_dir or Path(__file__).resolve().parent).resolve()
    for key in ("DREAD_HUB_INSTALL_ROOT", "DREAD_HUB_FROZEN_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if _is_frozen_ap_install(candidate):
            return candidate.resolve()
    for parent in (base, *base.parents):
        if _is_frozen_ap_install(parent):
            return parent.resolve()
    try:
        from Utils import local_path

        local = Path(local_path())
        if _is_frozen_ap_install(local):
            return local.resolve()
    except Exception:
        pass
    return None


def resolve_ap_roots(world_dir: Optional[Path] = None) -> Tuple[Path, Path]:
    """
    Resolve (import_root, install_root).

    *import_root* — directory on PYTHONPATH with CommonClient.py + Options.py
      (real source tree, or world ``ap_core/`` for frozen-only users).
    *install_root* — Archipelago install for Players/, output/, host.yaml, logs
      (same as import_root for source; frozen ProgramData when using ap_core).
    """
    base = (world_dir or Path(__file__).resolve().parent).resolve()

    for key in ("DREAD_HUB_AP_ROOT", "ARCHIPELAGO_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if _is_source_ap_root(candidate):
            root = candidate.resolve()
            # Env may point at bundled ap_core — keep frozen ProgramData as install.
            if root.name.lower() == AP_CORE_DIRNAME:
                frozen = resolve_frozen_install_root(base)
                return root, (frozen or root)
            return root, root

    for parent in (base, *base.parents):
        if _is_source_ap_root(parent) and parent.name.lower() != AP_CORE_DIRNAME:
            return parent.resolve(), parent.resolve()

    # Infer from saved Hub / patcher config paths (often point at a source checkout).
    for cfg_name in ("dread_client_ui_config.json", "dread_direct_patch_config.json"):
        cfg_path = base / cfg_name
        if not cfg_path.is_file():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(cfg, dict):
            continue
        for key in ("games_folder", "yaml_path", "base_rom_path", "output_path"):
            raw = cfg.get(key)
            if not raw:
                continue
            cur = Path(os.path.expandvars(str(raw))).expanduser()
            for parent in (cur, *cur.parents):
                if _is_source_ap_root(parent) and parent.name.lower() != AP_CORE_DIRNAME:
                    return parent.resolve(), parent.resolve()

    # Frozen ProgramData (+ runtime extract): use bundled ap_core for imports.
    # Prefer this over Utils.local_path() — during tests / mixed installs Utils may
    # still point at an unrelated source checkout on sys.path.
    frozen = resolve_frozen_install_root(base)
    core = bundled_ap_core(base)
    if core is not None and frozen is not None:
        return core, frozen
    if core is not None:
        return core, core

    try:
        from Utils import local_path

        local = Path(local_path())
        if _is_source_ap_root(local) and local.name.lower() != AP_CORE_DIRNAME:
            return local.resolve(), local.resolve()
    except Exception:
        pass

    # Legacy layout: worlds/metroid_dread → repo root (wrong for runtime extracts).
    try:
        legacy = base.parents[1].resolve()
    except IndexError:
        legacy = base
    return legacy, legacy


def resolve_ap_root(world_dir: Optional[Path] = None) -> Path:
    """
    Resolve the Archipelago root used for PYTHONPATH / CommonClient imports.

    Runtime extracts live at custom_worlds/_metroid_dread_runtime — parents[1] is the
    install folder (often frozen-only). Prefer env, then a real source tree, then the
    bundled ``ap_core/`` next to the world package.
    """
    import_root, _install = resolve_ap_roots(world_dir)
    return import_root


WORLD_DIR = Path(__file__).resolve().parent
AP_ROOT, INSTALL_ROOT = resolve_ap_roots(WORLD_DIR)

# Back-compat alias: older code used ROOT for the folder holding client scripts.
ROOT = WORLD_DIR

CONFIG_NAME = "dread_direct_patch_config.json"
UI_CONFIG_NAME = "dread_client_ui_config.json"

# Folder the packaging script writes the custom subsdk9 into, relative to AP_ROOT
# (portable package) or optionally under WORLD_DIR.
BUNDLED_EXLAUNCH_DEPLOY = Path("exlaunch") / "deploy"


def bind_utils_install_root(install_root: Optional[Path] = None) -> None:
    """
    Point Utils.local_path / user_path at the Archipelago install (ProgramData),
    not at bundled ap_core (which only exists for imports).
    """
    root = (install_root or INSTALL_ROOT).resolve()
    try:
        import Utils
    except Exception:
        return
    try:
        Utils.local_path.cached_path = str(root)  # type: ignore[attr-defined]
    except Exception:
        pass
    for name in ("user_path", "home_path", "output_path"):
        fn = getattr(Utils, name, None)
        if fn is not None and hasattr(fn, "cached_path"):
            try:
                delattr(fn, "cached_path")
            except Exception:
                pass


def _attach_world_package_spec(pkg: Any, name: str = "worlds.metroid_dread") -> None:
    """
    Give a synthetic package a real ModuleSpec.

    Without ``__spec__``, ``pkgutil.get_data`` / ``importlib.util.find_spec`` raise
    ``ValueError: worlds.metroid_dread.__spec__ is None`` (seen when the direct
    patcher resolves starting locations from logic_database under ap_core).
    """
    import importlib.machinery
    import importlib.util

    init_py = WORLD_DIR / "__init__.py"
    loader = importlib.machinery.SourceFileLoader(name, str(init_py))
    spec = importlib.util.spec_from_file_location(
        name,
        str(init_py),
        loader=loader,
        submodule_search_locations=[str(WORLD_DIR)],
    )
    if spec is None:
        return
    pkg.__spec__ = spec
    pkg.__loader__ = loader


def ensure_runtime_world_namespace() -> None:
    """
    Expose WORLD_DIR as ``worlds.metroid_dread`` when the AP import root is ap_core.

    Frozen installs use a stub ``worlds`` package (no game loaders). Patcher / client
    helpers still do ``from worlds.metroid_dread...`` and need this namespace.
    """
    import types

    name = "worlds.metroid_dread"
    existing = sys.modules.get(name)
    if existing is not None:
        # Repair incomplete synthetic packages left by older Hub builds.
        if getattr(existing, "__spec__", None) is None and getattr(
            existing, "__path__", None
        ):
            _attach_world_package_spec(existing, name)
        return
    try:
        import importlib

        importlib.import_module(name)
        return
    except Exception:
        pass
    # Ensure parent package exists (ap_core stub or real AP).
    try:
        import worlds  # noqa: F401
    except Exception:
        return
    pkg = types.ModuleType(name)
    pkg.__file__ = str(WORLD_DIR / "__init__.py")
    pkg.__package__ = name
    pkg.__path__ = [str(WORLD_DIR)]  # type: ignore[attr-defined]
    _attach_world_package_spec(pkg, name)
    sys.modules[name] = pkg


def ensure_import_paths() -> None:
    """
    Put AP import root and WORLD_DIR on sys.path so client modules + AP core import.

    Re-resolves roots (env may be set after first import). Import root is inserted
    last so it sits first on sys.path. The world package ships its own Options.py;
    that must never shadow Archipelago's Options.
    """
    global AP_ROOT, INSTALL_ROOT
    AP_ROOT, INSTALL_ROOT = resolve_ap_roots(WORLD_DIR)
    # World first, then AP import root at 0 so AP wins for Options / CommonClient / worlds.
    for path in (WORLD_DIR, AP_ROOT):
        text = str(path)
        if text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)
    bind_utils_install_root(INSTALL_ROOT)
    ensure_runtime_world_namespace()


def resolve_path(value: Any, root: Optional[Path] = None) -> Optional[Path]:
    """Expand %VARS%/~ and anchor relative values at `root` (default: WORLD_DIR)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = os.path.expandvars(text)
    expanded = Path(text).expanduser()
    if expanded.is_absolute():
        return expanded
    return (root or WORLD_DIR) / expanded


def config_file(root: Optional[Path] = None) -> Path:
    return (root or WORLD_DIR) / CONFIG_NAME


def load_patch_config(root: Optional[Path] = None) -> Dict[str, Any]:
    """Read dread_direct_patch_config.json; missing/broken config is empty."""
    path = config_file(root)
    if not path.is_file():
        # Fall back to install root (pre-merge layout / older portable packages).
        legacy = INSTALL_ROOT / CONFIG_NAME
        if root is None and legacy.is_file():
            path = legacy
        else:
            return {}
    try:
        # utf-8-sig: editors and PowerShell happily leave a BOM on this file.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def config_paths(root: Optional[Path] = None) -> Dict[str, Optional[Path]]:
    """Resolved mod output / games folder used to locate map_icon_keys.json."""
    cfg = load_patch_config(root)
    base = root or WORLD_DIR
    return {
        "mod_root": resolve_path(cfg.get("output_path"), base),
        "games_folder": resolve_path(cfg.get("games_folder"), base),
    }


def bundled_exlaunch_deploy(root: Optional[Path] = None) -> Optional[Path]:
    """Custom subsdk9 shipped inside the portable package, if present."""
    bases = []
    if root is not None:
        bases.append(root)
    bases.extend((WORLD_DIR, INSTALL_ROOT, AP_ROOT))
    seen: set[Path] = set()
    for base in bases:
        try:
            resolved = base.resolve()
        except OSError:
            resolved = base
        if resolved in seen:
            continue
        seen.add(resolved)
        deploy = resolved / BUNDLED_EXLAUNCH_DEPLOY
        if (deploy / "subsdk9").is_file():
            return deploy
    return None


def dread_scripts_dir() -> Path:
    """Lua overrides / warp scripts (colocated under the world package)."""
    local = WORLD_DIR / "dread_scripts"
    if local.is_dir():
        return local
    legacy = INSTALL_ROOT / "dread_scripts"
    return legacy if legacy.is_dir() else local


def world_data_file(*parts: str) -> Path:
    return WORLD_DIR.joinpath(*parts)


def tools_file(*parts: str) -> Path:
    """Prefer install-root tools/, then world-local tools/."""
    for base in (INSTALL_ROOT, AP_ROOT):
        ap_tool = base.joinpath("tools", *parts)
        if ap_tool.is_file():
            return ap_tool
    return WORLD_DIR.joinpath("tools", *parts)

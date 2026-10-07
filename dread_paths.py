#!/usr/bin/env python3
"""Path helpers for the Metroid Bread client / direct patcher."""

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
    """True for an official frozen Archipelago install (no loose CommonClient.py)."""
    try:
        if _is_source_ap_root(candidate):
            return False
        lib_zip = candidate / "lib" / "library.zip"
        if not lib_zip.is_file():
            return False
        # Look for an AP launcher, not just any folder containing a zip.
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


def resolve_hub_install_root(world_dir: Optional[Path] = None) -> Optional[Path]:
    """Hub install root from env (source *or* frozen), then frozen climb, then source climb."""
    base = (world_dir or Path(__file__).resolve().parent).resolve()
    for key in ("DREAD_HUB_INSTALL_ROOT", "DREAD_HUB_FROZEN_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        try:
            if candidate.is_dir():
                return candidate.resolve()
        except OSError:
            continue
    frozen = resolve_frozen_install_root(base)
    if frozen is not None:
        return frozen
    for parent in (base, *base.parents):
        if _is_source_ap_root(parent) and parent.name.lower() != AP_CORE_DIRNAME:
            return parent.resolve()
    return None


def _infer_source_ap_from_configs(base: Path) -> Optional[Path]:
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
        for key in ("game_folder", "yaml_path", "base_rom_path", "output_path"):
            raw = cfg.get(key)
            if not raw:
                continue
            cur = Path(os.path.expandvars(str(raw))).expanduser()
            for parent in (cur, *cur.parents):
                if _is_source_ap_root(parent) and parent.name.lower() != AP_CORE_DIRNAME:
                    return parent.resolve()
    return None


def resolve_ap_roots(world_dir: Optional[Path] = None) -> Tuple[Path, Path]:
    """Resolve (import_root, install_root)."""
    base = (world_dir or Path(__file__).resolve().parent).resolve()
    core = bundled_ap_core(base)

    for key in ("DREAD_HUB_AP_ROOT", "ARCHIPELAGO_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if _is_source_ap_root(candidate):
            root = candidate.resolve()
            # Keep the install path even if the import path points to ap_core.
            if root.name.lower() == AP_CORE_DIRNAME:
                install = resolve_hub_install_root(base) or root
                return root, install
            # Prefer the matching bundled ap_core for imports.
            if core is not None:
                return core, root
            return root, root

    # Use bundled ap_core when it is available.
    if core is not None:
        install = resolve_hub_install_root(base)
        if install is None:
            for parent in (base, *base.parents):
                if _is_source_ap_root(parent) and parent.name.lower() != AP_CORE_DIRNAME:
                    install = parent.resolve()
                    break
        if install is None:
            install = _infer_source_ap_from_configs(base)
        return core, (install or core)

    for parent in (base, *base.parents):
        if _is_source_ap_root(parent) and parent.name.lower() != AP_CORE_DIRNAME:
            return parent.resolve(), parent.resolve()

    inferred = _infer_source_ap_from_configs(base)
    if inferred is not None:
        return inferred, inferred

    frozen = resolve_frozen_install_root(base)
    if frozen is not None:
        return frozen, frozen

    try:
        from Utils import local_path

        local = Path(local_path())
        if _is_source_ap_root(local) and local.name.lower() != AP_CORE_DIRNAME:
            return local.resolve(), local.resolve()
    except Exception:
        pass

    # Older installs keep the AP root above worlds/metroid_bread.
    try:
        legacy = base.parents[1].resolve()
    except IndexError:
        legacy = base
    return legacy, legacy



def resolve_ap_root(world_dir: Optional[Path] = None) -> Path:
    """Resolve the Archipelago root used for PYTHONPATH / CommonClient imports."""
    import_root, _install = resolve_ap_roots(world_dir)
    return import_root


WORLD_DIR = Path(__file__).resolve().parent
AP_ROOT, INSTALL_ROOT = resolve_ap_roots(WORLD_DIR)

# Keep ROOT for callers that still use the old name.
ROOT = WORLD_DIR

CONFIG_NAME = "dread_direct_patch_config.json"
UI_CONFIG_NAME = "dread_client_ui_config.json"

# Find the folder where the packager writes subsdk9.
BUNDLED_EXLAUNCH_DEPLOY = Path("exlaunch") / "deploy"


def bind_utils_install_root(install_root: Optional[Path] = None) -> None:
    """Point Utils.local_path / user_path at the Archipelago install (ProgramData),"""
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


def _attach_world_package_spec(pkg: Any, name: str = "worlds.metroid_bread") -> None:
    """Give a synthetic package a real ModuleSpec."""
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
    """Expose WORLD_DIR as ``worlds.metroid_bread`` when the AP import root is ap_core."""
    import types

    name = "worlds.metroid_bread"
    existing = sys.modules.get(name)
    if existing is not None:
        # Repair packages left incomplete by older Hub builds.
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
    # Create the parent package if it is missing.
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
    """Put AP import root and WORLD_DIR on sys.path so client modules + AP core import."""
    global AP_ROOT, INSTALL_ROOT
    AP_ROOT, INSTALL_ROOT = resolve_ap_roots(WORLD_DIR)
    # Put the AP import path first so its core modules win.
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
        # Try the install root for older package layouts.
        legacy = INSTALL_ROOT / CONFIG_NAME
        if root is None and legacy.is_file():
            path = legacy
        else:
            return {}
    try:
        # Accept the UTF-8 file marker left by some editors.
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

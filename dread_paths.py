#!/usr/bin/env python3
"""
Path helpers for the Metroid Dread client / direct patcher.

Canonical layout (after client↔world merge):
  worlds/metroid_dread/          ← WORLD_DIR (this package)
    MetroidDreadClient.py
    dread_direct_patch.py
    dread-client-app/
    dread_scripts/
    *.json data next to the scripts
  <Archipelago root>/            ← AP_ROOT (parents[1] of WORLD_DIR)
    CommonClient.py, tools/, …

dread_direct_patch_config.json may hold absolute paths, %APPDATA% values, or
paths relative to WORLD_DIR so the portable package stays movable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

WORLD_DIR = Path(__file__).resolve().parent
# worlds/metroid_dread → Archipelago (or portable package) root
AP_ROOT = WORLD_DIR.parents[1]

# Back-compat alias: older code used ROOT for the folder holding client scripts.
ROOT = WORLD_DIR

CONFIG_NAME = "dread_direct_patch_config.json"
UI_CONFIG_NAME = "dread_client_ui_config.json"

# Folder the packaging script writes the custom subsdk9 into, relative to AP_ROOT
# (portable package) or optionally under WORLD_DIR.
BUNDLED_EXLAUNCH_DEPLOY = Path("exlaunch") / "deploy"


def ensure_import_paths() -> None:
    """
    Put AP_ROOT and WORLD_DIR on sys.path so client modules + AP core import.

    AP_ROOT is inserted last (so it sits first on sys.path). The world package
    ships its own Options.py; that must never shadow Archipelago's Options.
    """
    for path in (WORLD_DIR, AP_ROOT):
        text = str(path)
        if text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)


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
        # Fall back to AP root (pre-merge layout / older portable packages).
        legacy = AP_ROOT / CONFIG_NAME
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
    bases.extend((WORLD_DIR, AP_ROOT))
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
    legacy = AP_ROOT / "dread_scripts"
    return legacy if legacy.is_dir() else local


def world_data_file(*parts: str) -> Path:
    return WORLD_DIR.joinpath(*parts)


def tools_file(*parts: str) -> Path:
    """Prefer AP-root tools/, then world-local tools/."""
    ap_tool = AP_ROOT.joinpath("tools", *parts)
    if ap_tool.is_file():
        return ap_tool
    return WORLD_DIR.joinpath("tools", *parts)

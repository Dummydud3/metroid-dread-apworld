"""
Rebuild an installed mod's map_icon_keys.json from its patcher.json.

Repairs sidecars written before KEYS_VERSION 3, which numbered every custom_icon
pickup — including the major-item spheres open-dread-rando never gives a custom
icon — so every later location's MAP_ICON_ItemCustom{n} was shifted and map labels
showed another check's logic state and item name.

Also upgrades pre-v4 sidecars, which carry no `sprite` per entry and so leave every
revealed icon stuck on the `unknown` graphic.

No re-patch is needed: the runtime label path writes the full display string with
OdrText.SetLocalized and the icon graphic is a runtime OdrMap.SetIconSprite write,
so a corrected sidecar is enough.

Usage:
    python dread_scripts/rebuild_map_icon_keys.py [mod_root]

mod_root defaults to output_path from dread_direct_patch_config.json.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dread_map_icon_labels import (  # noqa: E402
    KEYS_VERSION,
    build_map_icon_keys_for_patcher,
    write_map_icon_keys,
)


def _default_mod_root() -> Path | None:
    cfg = ROOT / "dread_direct_patch_config.json"
    if not cfg.is_file():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    out = data.get("output_path")
    return Path(out) if out else None


def main() -> int:
    if len(sys.argv) > 1:
        mod_root = Path(sys.argv[1])
    else:
        mod_root = _default_mod_root()
        if mod_root is None:
            print(__doc__)
            return 2

    bases = [mod_root, mod_root / "DreadRandovania"]
    patcher = next((b / "patcher.json" for b in bases if (b / "patcher.json").is_file()), None)
    if patcher is None:
        print(f"[FAIL] no patcher.json under {mod_root}")
        return 1

    data = json.loads(patcher.read_text(encoding="utf-8"))
    keys = build_map_icon_keys_for_patcher(data)
    dest = patcher.with_name("map_icon_keys.json")

    if dest.is_file():
        try:
            old = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}
        backup = dest.with_name(f"map_icon_keys.v{old.get('version', 0)}.{int(time.time())}.bak.json")
        shutil.copy2(dest, backup)
        print(f"[OK] backed up old sidecar (version {old.get('version')}) -> {backup.name}")
        moved = sum(
            1
            for loc, key in (keys.get("by_location_id") or {}).items()
            if (old.get("by_location_id") or {}).get(loc) not in (None, key)
        )
        print(f"[OK] {moved} locations remapped to a different MAP_ICON_ItemCustom key")

    write_map_icon_keys(dest, keys)
    revealing = sum(
        1
        for e in keys.get("entries") or []
        if tuple(e.get("sprite") or ()) != tuple(keys.get("unknown_sprite") or ())
    )
    print(
        f"[OK] wrote {dest} (version {KEYS_VERSION}, "
        f"{keys.get('custom_icon_count')} icons, "
        f"{len(keys.get('skipped') or [])} pickups keep their vanilla icon)"
    )
    print(f"[OK] {revealing} icons have a reveal sprite (collect / AP hint swaps the graphic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

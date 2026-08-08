#!/usr/bin/env python3
"""Copy Archipelago core modules + Metroid Dread datapackage into ap_core/."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

WORLD_DIR = Path(__file__).resolve().parents[1]
AP_CORE = WORLD_DIR / "ap_core"
AP_ROOT = WORLD_DIR.parents[1]

CORE_FILES = (
    "CommonClient.py",
    "Utils.py",
    "NetUtils.py",
    "Options.py",
    "settings.py",
    "ModuleUpdate.py",
    "MultiServer.py",
    "BaseClasses.py",
    "kvui.py",
    "requirements.txt",
)


def main() -> int:
    os.environ.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")
    if str(AP_ROOT) not in sys.path:
        sys.path.insert(0, str(AP_ROOT))

    AP_CORE.mkdir(parents=True, exist_ok=True)
    (AP_CORE / "worlds").mkdir(parents=True, exist_ok=True)

    for name in CORE_FILES:
        src = AP_ROOT / name
        if not src.is_file():
            print(f"MISSING {src}", file=sys.stderr)
            return 1
        shutil.copy2(src, AP_CORE / name)
        print(f"copied {name}")

    from worlds.AutoWorld import data_package_checksum
    from worlds.metroid_dread import MetroidDreadWorld

    pkg = MetroidDreadWorld.get_data_package_data()
    out = {
        "item_name_groups": {
            k: sorted(v) for k, v in sorted(pkg.get("item_name_groups", {}).items())
        },
        "item_name_to_id": dict(sorted(pkg["item_name_to_id"].items())),
        "location_name_groups": {
            k: sorted(v) for k, v in sorted(pkg.get("location_name_groups", {}).items())
        },
        "location_name_to_id": dict(sorted(pkg["location_name_to_id"].items())),
    }
    ordered = {
        "item_name_groups": out["item_name_groups"],
        "item_name_to_id": out["item_name_to_id"],
        "location_name_groups": out["location_name_groups"],
        "location_name_to_id": out["location_name_to_id"],
    }
    out["checksum"] = data_package_checksum(ordered)
    dp_path = AP_CORE / "worlds" / "metroid_dread_datapackage.json"
    dp_path.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(
        f"wrote {dp_path.name} items={len(out['item_name_to_id'])} "
        f"locs={len(out['location_name_to_id'])} checksum={out['checksum']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

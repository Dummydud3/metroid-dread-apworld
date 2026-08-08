"""
Generate dread_map_icon_actors.json: per-scenario minimap "items" actors.

open-dread-rando's MapIconEditor only consumes an ItemCustom{n} number when the
pickup's map actor exists in that scenario's vanilla .bmmap `items` category
(see open_dread_rando/pickups/pickup.py::patch_minimap_icon). Major-item spheres
(ItemSphere_*, IT_VARIA_GEN_001, ...) have no minimap item entry, so they are
skipped and every later pickup shifts down by one. dread_map_icon_labels needs
this table to reproduce the real numbering without the base ROM.

Usage (needs open-dread-rando's interpreter and an extracted Dread RomFS):
    py -3.11 dread_scripts/gen_map_icon_actors.py "C:/path/to/extracted/romfs"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mercury_engine_data_structures.file_tree_editor import FileTreeEditor
from mercury_engine_data_structures.formats import Bmmap
from mercury_engine_data_structures.game_check import Game
from mercury_engine_data_structures.romfs import ExtractedRomFs

SCENARIOS = [
    "s010_cave",
    "s020_magma",
    "s030_baselab",
    "s040_aqua",
    "s050_forest",
    "s060_quarantine",
    "s070_basesanc",
    "s080_shipyard",
    "s090_skybase",
]

OUT = Path(__file__).resolve().parent.parent / "dread_map_icon_actors.json"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = Path(sys.argv[1])
    if not base.is_dir():
        print(f"Not a directory: {base}")
        return 2

    editor = FileTreeEditor(ExtractedRomFs(base), target_game=Game.DREAD)
    items: dict[str, list[str]] = {}
    labels: dict[str, list[str]] = {}
    for scenario in SCENARIOS:
        path = f"maps/levels/c10_samus/{scenario}/{scenario}.bmmap"
        if not editor.does_asset_exists(path):
            continue
        bmmap = editor.get_parsed_asset(path, type_hint=Bmmap)
        items[scenario] = sorted(bmmap.items.keys())
        labels[scenario] = sorted(bmmap.ability_labels.keys())

    OUT.write_text(
        json.dumps(
            {
                "version": 1,
                "comment": (
                    "Vanilla Metroid Dread minimap categories. `items` drives ODR's "
                    "ItemCustom{n} numbering: a pickup whose map actor is absent from "
                    "its scenario's `items` list gets no custom icon."
                ),
                "items": items,
                "ability_labels": labels,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    total = sum(len(v) for v in items.values())
    print(f"[OK] {OUT} ({len(items)} scenarios, {total} map item actors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

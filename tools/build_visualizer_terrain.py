#!/usr/bin/env python3
"""Extract Dread BMMAP terrain into dread-client-app/visualizer/terrain.json.

Usage (from the Archipelago repo root):
  py -3.12 worlds/metroid_bread/tools/build_visualizer_terrain.py
  py -3.12 worlds/metroid_bread/tools/build_visualizer_terrain.py --romfs "C:\\Users\\dummy\\Downloads\\md rando"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORLD_DIR = Path(__file__).resolve().parents[1]
if str(WORLD_DIR) not in sys.path:
    sys.path.insert(0, str(WORLD_DIR))

from visualizer_terrain import write_visualizer_terrain


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Hub visualizer terrain from BMMAP")
    parser.add_argument("--romfs", type=Path, default=None, help="Extracted Dread RomFS folder")
    parser.add_argument("--out", type=Path, default=None, help="Output terrain.json")
    args = parser.parse_args()
    out = write_visualizer_terrain(path=args.out, romfs=args.romfs)
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Client-side helpers for AP reachability → in-game minimap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "data" / "reachable_map_cells.json"
DATA_LUA = ROOT / "data" / "reachable_map_cells.lua"

RegionArea = Tuple[str, str]

_CACHE: Optional[dict] = None


def load_map_data() -> dict:
    global _CACHE
    if _CACHE is None:
        if not DATA_JSON.is_file():
            _CACHE = {"region_to_scenario": {}, "scenarios": {}}
        else:
            _CACHE = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    return _CACHE


def region_to_scenario() -> Dict[str, str]:
    return dict(load_map_data().get("region_to_scenario") or {})


def format_apply_reachable_lua(areas: Iterable[RegionArea]) -> str:
    """
    Build RL.ApplyReachableMap(...) call grouping areas by scenario.

    areas: iterable of (region, area_name)
    """
    r2s = region_to_scenario()
    by_scenario: Dict[str, List[str]] = {}
    for region, area in areas:
        scenario = r2s.get(region)
        if not scenario:
            continue
        by_scenario.setdefault(scenario, []).append(area)

    # Compact Lua: {scenario={area1,area2,...}, ...}
    parts: List[str] = []
    for scenario in sorted(by_scenario):
        names = sorted(set(by_scenario[scenario]))
        quoted = ",".join('"' + n.replace("\\", "\\\\").replace('"', '\\"') + '"' for n in names)
        parts.append(f'["{scenario}"]={{{quoted}}}')
    table = "{" + ",".join(parts) + "}"
    return f"RL.ApplyReachableMap({table})"


def areas_signature(areas: Set[RegionArea]) -> Tuple[RegionArea, ...]:
    return tuple(sorted(areas))

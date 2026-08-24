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


def scenario_to_region() -> Dict[str, str]:
    """Inverse of region_to_scenario (one region per scenario id)."""
    return {scenario: region for region, scenario in region_to_scenario().items()}


def area_at_position(
    scenario: str,
    x: float,
    y: float,
) -> Optional[str]:
    """
    Resolve world (x, y) to a logic-database area name for *scenario*.

    Uses AABB bounds from reachable_map_cells.json (same names as
    ``DreadLogic.reachable_areas`` / minimap paint). When AABBs overlap,
    prefers the smallest containing box.
    """
    scen = (scenario or "").strip()
    if not scen:
        return None
    scenarios = load_map_data().get("scenarios") or {}
    areas = (scenarios.get(scen) or {}).get("areas") or {}
    best_name: Optional[str] = None
    best_area = float("inf")
    for name, meta in areas.items():
        bounds = (meta or {}).get("bounds")
        if not bounds or len(bounds) < 4:
            continue
        x1, y1, x2, y2 = (
            float(bounds[0]),
            float(bounds[1]),
            float(bounds[2]),
            float(bounds[3]),
        )
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        if x < x1 or x > x2 or y < y1 or y > y2:
            continue
        area = (x2 - x1) * (y2 - y1)
        if area < best_area:
            best_area = area
            best_name = str(name)
    return best_name


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

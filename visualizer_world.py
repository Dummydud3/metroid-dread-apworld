"""Dread world-space layout and minimap-cell raster for the Hub visualizer.

Uses the same coordinates as the game / logic database:

- World XY from ``logic_database`` node ``coordinates`` and area polygons
- Minimap cells of 100 world units, origin at each scenario's BMMAP ``grid.min``
- Packed index ``row * cols + col`` (same formula as ``build_reachable_map_cells.py``)

No PopTracker pixel fit — the visualizer SVG is this coordinate system with Y flipped for the screen.

Cave silhouette, heat/water/EMMI, doors, and magnets live in ``terrain.json``
(see ``visualizer_terrain.py``), extracted from each scenario BMMAP.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import AbstractSet, Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parent
LOGIC_DB = ROOT / "logic_database"
MAP_CELLS = ROOT / "data" / "reachable_map_cells.json"
LAYOUT_PATH = ROOT / "dread-client-app" / "visualizer" / "world_layout.json"

CELL_SIZE = 100.0
REGION_ORDER = (
    "Artaria",
    "Cataris",
    "Dairon",
    "Burenia",
    "Ghavoran",
    "Ferenia",
    "Elun",
    "Hanubia",
    "Itorash",
)

NodeId = Tuple[str, str, str]


def _round(value: float) -> float:
    return round(float(value), 1)


def world_to_cell(
    x: float,
    y: float,
    grid_min: Sequence[float],
    cell_size: float = CELL_SIZE,
) -> Tuple[int, int]:
    """Dread minimap cell (col, row) for a world XY point."""
    col = int(math.floor((float(x) - float(grid_min[0])) / cell_size))
    row = int(math.floor((float(y) - float(grid_min[1])) / cell_size))
    return col, row


def cell_origin(
    col: int,
    row: int,
    grid_min: Sequence[float],
    cell_size: float = CELL_SIZE,
) -> Tuple[float, float]:
    """World XY of the cell's min corner (Y-up)."""
    return (
        float(grid_min[0]) + col * cell_size,
        float(grid_min[1]) + row * cell_size,
    )


def grid_cols(grid: dict) -> int:
    gmin = grid.get("min") or [0.0, 0.0]
    gmax = grid.get("max") or [0.0, 0.0]
    size = float(grid.get("cell_size") or CELL_SIZE)
    return max(1, int(math.ceil((float(gmax[0]) - float(gmin[0])) / size)))


def pack_cell(col: int, row: int, cols: int) -> int:
    return int(row) * int(cols) + int(col)


def unpack_cell(index: int, cols: int) -> Tuple[int, int]:
    return int(index) % int(cols), int(index) // int(cols)


def point_in_poly(x: float, y: float, poly: Sequence[Sequence[float]]) -> bool:
    """Even-odd point in polygon (same test as fillmap / BMSCC tools)."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def cells_for_polygon(
    poly: Sequence[Sequence[float]],
    grid: dict,
) -> List[int]:
    """Pack every minimap cell whose center sits inside *poly*."""
    if len(poly) < 3:
        return []
    gmin = grid.get("min") or [0.0, 0.0]
    gmax = grid.get("max") or [0.0, 0.0]
    size = float(grid.get("cell_size") or CELL_SIZE)
    cols = grid_cols(grid)
    rows = max(1, int(math.ceil((float(gmax[1]) - float(gmin[1])) / size)))
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    c0 = max(0, int(math.floor((min(xs) - float(gmin[0])) / size)))
    c1 = min(cols - 1, int(math.floor((max(xs) - float(gmin[0]) - 1e-6) / size)))
    r0 = max(0, int(math.floor((min(ys) - float(gmin[1])) / size)))
    r1 = min(rows - 1, int(math.floor((max(ys) - float(gmin[1]) - 1e-6) / size)))
    half = size * 0.5
    out: List[int] = []
    for row in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            cx = float(gmin[0]) + col * size + half
            cy = float(gmin[1]) + row * size + half
            if point_in_poly(cx, cy, poly):
                out.append(pack_cell(col, row, cols))
    return out


def load_map_grids() -> Dict[str, dict]:
    if not MAP_CELLS.is_file():
        return {}
    data = json.loads(MAP_CELLS.read_text(encoding="utf-8"))
    out: Dict[str, dict] = {}
    for scenario, raw in (data.get("scenarios") or {}).items():
        grid = (raw or {}).get("grid")
        if isinstance(grid, dict) and grid.get("min") and grid.get("max"):
            out[str(scenario)] = {
                "min": [float(grid["min"][0]), float(grid["min"][1])],
                "max": [float(grid["max"][0]), float(grid["max"][1])],
                "cell_size": float(grid.get("cell_size") or CELL_SIZE),
            }
    return out


def _polygon_from_area(extra: dict) -> List[List[float]]:
    raw = extra.get("polygon") or []
    points: List[List[float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            points.append([_round(item[0]), _round(item[1])])
    if points:
        return points
    tb = extra.get("total_boundings") or {}
    if not tb:
        return []
    x1, y1, x2, y2 = (
        float(tb["x1"]),
        float(tb["y1"]),
        float(tb["x2"]),
        float(tb["y2"]),
    )
    return [
        [_round(x1), _round(y1)],
        [_round(x2), _round(y1)],
        [_round(x2), _round(y2)],
        [_round(x1), _round(y2)],
    ]


def build_world_layout() -> dict:
    """Static Dread-space geometry for the Hub visualizer."""
    grids = load_map_grids()
    region_to_scenario: Dict[str, str] = {}
    regions: Dict[str, dict] = {}

    for path in sorted(LOGIC_DB.glob("*.json")):
        if path.name == "header.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        region = str(data.get("name") or path.stem)
        extra = data.get("extra") or {}
        scenario = str(extra.get("scenario_id") or "")
        if not scenario:
            continue
        region_to_scenario[region] = scenario
        grid = grids.get(scenario) or {}
        areas_out: List[dict] = []
        pickups_out: List[dict] = []
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")

        for area_name, area in (data.get("areas") or {}).items():
            area_extra = area.get("extra") or {}
            poly = _polygon_from_area(area_extra)
            tb = area_extra.get("total_boundings") or {}
            bounds = None
            if tb:
                bounds = [
                    _round(tb["x1"]),
                    _round(tb["y1"]),
                    _round(tb["x2"]),
                    _round(tb["y2"]),
                ]
                min_x = min(min_x, bounds[0], bounds[2])
                min_y = min(min_y, bounds[1], bounds[3])
                max_x = max(max_x, bounds[0], bounds[2])
                max_y = max(max_y, bounds[1], bounds[3])
            elif poly:
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                bounds = [_round(min(xs)), _round(min(ys)), _round(max(xs)), _round(max(ys))]
                min_x = min(min_x, bounds[0])
                min_y = min(min_y, bounds[1])
                max_x = max(max_x, bounds[2])
                max_y = max(max_y, bounds[3])
            if poly or bounds:
                areas_out.append(
                    {
                        "name": str(area_name),
                        "polygon": poly,
                        "bounds": bounds,
                        "asset_id": area_extra.get("asset_id") or "",
                    }
                )
            for node_name, node in (area.get("nodes") or {}).items():
                if node.get("node_type") != "pickup":
                    continue
                coords = node.get("coordinates") or {}
                if "x" not in coords or "y" not in coords:
                    continue
                x = _round(coords["x"])
                y = _round(coords["y"])
                pickups_out.append(
                    {
                        "name": f"{region} - {area_name} - {node_name}",
                        "area": str(area_name),
                        "x": x,
                        "y": y,
                    }
                )
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

        if min_x == float("inf"):
            continue
        pad = 400.0
        regions[region] = {
            "scenario": scenario,
            "grid": grid,
            "bounds": [
                _round(min_x - pad),
                _round(min_y - pad),
                _round(max_x + pad),
                _round(max_y + pad),
            ],
            "areas": areas_out,
            "pickups": pickups_out,
        }

    return {
        "cell_size": CELL_SIZE,
        "coordinate_space": "dread_world_xy",
        "y_up": True,
        "region_order": [name for name in REGION_ORDER if name in regions],
        "region_to_scenario": region_to_scenario,
        "regions": regions,
    }


def write_world_layout(path: Optional[Path] = None) -> Path:
    dest = path or LAYOUT_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    layout = build_world_layout()
    dest.write_text(json.dumps(layout, separators=(",", ":")), encoding="utf-8")
    return dest


def _node_xy(parser, node_id: NodeId) -> Optional[Tuple[float, float]]:
    region, area, name = node_id
    try:
        node = parser.regions[region]["areas"][area]["nodes"][name]
    except KeyError:
        return None
    coords = node.get("coordinates") or {}
    if "x" not in coords or "y" not in coords:
        return None
    return float(coords["x"]), float(coords["y"])


def polygon_area(poly: Sequence[Sequence[float]]) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x1, y1 = float(poly[i][0]), float(poly[i][1])
        x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def smallest_loop_containing(
    x: float,
    y: float,
    loops: Sequence[Sequence[Sequence[float]]],
) -> Optional[int]:
    """Index of the tightest outline that contains (x, y)."""
    best: Optional[int] = None
    best_area = float("inf")
    for i, loop in enumerate(loops):
        if len(loop) < 3 or not point_in_poly(x, y, loop):
            continue
        area = polygon_area(loop)
        if area < best_area:
            best = i
            best_area = area
    return best


def loop_fraction_inside(
    loop: Sequence[Sequence[float]],
    camera: Optional[Sequence[Sequence[float]]],
) -> float:
    """How much of *loop* sits inside *camera* (vertices + centroid)."""
    if not camera or len(camera) < 3:
        return 1.0
    pts = [p for p in loop if len(p) >= 2]
    if not pts:
        return 0.0
    hits = 0
    for px, py, *_rest in pts:
        if point_in_poly(float(px), float(py), camera):
            hits += 1
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    if point_in_poly(sum(xs) / len(xs), sum(ys) / len(ys), camera):
        hits += 1
    return hits / (len(pts) + 1)


# Doorway / Z-overlay slivers are a few 100-unit cells. Walkable room
# floors are larger. Nodes sitting in a sliver should light the floor.
FLOOR_MIN_AREA = 120_000.0


def pick_loop_for_spot(
    x: float,
    y: float,
    loops: Sequence[Sequence[Sequence[float]]],
    camera: Optional[Sequence[Sequence[float]]] = None,
) -> Optional[int]:
    """Pick the terrain island for a logic node.

    Prefer a walkable floor that contains the point and belongs to the room
    camera. Doorway nodes often sit on a tiny Z-overlay just outside the
    navmesh — snap to that camera's largest floor instead of the sliver.
    """
    x = float(x)
    y = float(y)
    has_cam = bool(camera) and len(camera) >= 3
    contained: List[Tuple[int, float, float]] = []
    for i, loop in enumerate(loops):
        if len(loop) < 3 or not point_in_poly(x, y, loop):
            continue
        frac = loop_fraction_inside(loop, camera) if has_cam else 1.0
        contained.append((i, polygon_area(loop), frac))
    floors_in_room = [
        row for row in contained if row[2] >= 0.35 and row[1] >= FLOOR_MIN_AREA
    ]
    if floors_in_room:
        return min(floors_in_room, key=lambda row: row[1])[0]
    if has_cam:
        best_floor: Optional[int] = None
        best_floor_area = -1.0
        best_near: Optional[int] = None
        best_d = float("inf")
        for i, loop in enumerate(loops):
            if len(loop) < 3 or loop_fraction_inside(loop, camera) < 0.5:
                continue
            area = polygon_area(loop)
            if area >= FLOOR_MIN_AREA and area > best_floor_area:
                best_floor = i
                best_floor_area = area
            xs = [float(p[0]) for p in loop]
            ys = [float(p[1]) for p in loop]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            dist = (cx - x) ** 2 + (cy - y) ** 2
            if dist < best_d:
                best_near = i
                best_d = dist
        if best_floor is not None:
            return best_floor
        if best_near is not None:
            return best_near
    if contained:
        return min(contained, key=lambda row: row[1])[0]
    return None


def reachable_node_spots(
    logic,
    counts: Dict[str, int],
    *,
    exclude_auto_events: Optional[AbstractSet[str]] = None,
) -> Dict[str, List[dict]]:
    """Scenario → reachable logic nodes with world XY and area name."""
    from .DoorRando import REGION_TO_SCENARIO

    inv = logic.inventory_from_counts(counts)
    nodes = logic.get_reachable_nodes(inv, exclude_auto_events=exclude_auto_events)
    by_scenario: Dict[str, Set[Tuple[int, int, str]]] = {}
    for node_id in nodes:
        scenario = REGION_TO_SCENARIO.get(node_id[0])
        if not scenario:
            continue
        xy = _node_xy(logic.parser, node_id)
        if not xy:
            continue
        by_scenario.setdefault(scenario, set()).add(
            (int(round(xy[0])), int(round(xy[1])), str(node_id[1]))
        )
    return {
        scenario: [{"x": x, "y": y, "area": area} for x, y, area in sorted(pts)]
        for scenario, pts in by_scenario.items()
    }


def reachable_area_names(
    logic,
    counts: Dict[str, int],
    *,
    exclude_auto_events: Optional[AbstractSet[str]] = None,
) -> Dict[str, List[str]]:
    """Scenario → logic area names that have at least one reachable node."""
    from .DoorRando import REGION_TO_SCENARIO

    areas = logic.reachable_areas(counts, exclude_auto_events=exclude_auto_events)
    by_scenario: Dict[str, Set[str]] = {}
    for region, area in areas:
        scenario = REGION_TO_SCENARIO.get(region)
        if not scenario:
            continue
        by_scenario.setdefault(scenario, set()).add(area)
    return {scenario: sorted(names) for scenario, names in by_scenario.items()}


def _area_polygon(parser, region: str, area: str) -> List[List[float]]:
    try:
        extra = parser.regions[region]["areas"][area].get("extra") or {}
    except KeyError:
        return []
    return _polygon_from_area(extra)


def reachable_cell_indices(
    logic,
    counts: Dict[str, int],
    *,
    exclude_auto_events: Optional[AbstractSet[str]] = None,
    grids: Optional[Dict[str, dict]] = None,
) -> Dict[str, List[int]]:
    """Packed minimap cells inside camera polygons of reachable areas."""
    from .DoorRando import REGION_TO_SCENARIO

    grids = grids if grids is not None else load_map_grids()
    areas = logic.reachable_areas(counts, exclude_auto_events=exclude_auto_events)
    packed: Dict[str, Set[int]] = {}
    for region, area in areas:
        scenario = REGION_TO_SCENARIO.get(region)
        grid = grids.get(scenario or "")
        if not scenario or not grid:
            continue
        poly = _area_polygon(logic.parser, region, area)
        if not poly:
            continue
        packed.setdefault(scenario, set()).update(cells_for_polygon(poly, grid))
    return {scenario: sorted(indices) for scenario, indices in packed.items()}


if __name__ == "__main__":
    out = write_world_layout()
    layout = json.loads(out.read_text(encoding="utf-8"))
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    for name in layout.get("region_order") or []:
        region = layout["regions"][name]
        print(
            f"  {name}: {len(region.get('areas') or [])} areas, "
            f"{len(region.get('pickups') or [])} pickups, "
            f"bounds={region.get('bounds')}"
        )

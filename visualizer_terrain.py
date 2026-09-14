"""Dread pause-map terrain for the Hub visualizer.

Reads each scenario BMMAP (same world XY as the logic polygons) and stores:

- Navmesh outlines (occupied 100-unit minimap cells, one layer per Z)
- Heat / water / freeze / EMMI overlays
- Magnet rails, elevator ticks, door boxes, breakable occluders
- Station / elevator / tram / teleport / nav / CU / boss icons

Navmesh triangles are far too dense for SVG. Boundary edges of the 100-unit
grid are chained into even-odd fill loops instead.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
REGION_TO_SCENARIO = {
    "Artaria": "s010_cave",
    "Cataris": "s020_magma",
    "Dairon": "s030_baselab",
    "Burenia": "s040_aqua",
    "Ghavoran": "s050_forest",
    "Elun": "s060_quarantine",
    "Ferenia": "s070_basesanc",
    "Hanubia": "s080_shipyard",
    "Itorash": "s090_skybase",
}

ROOT = Path(__file__).resolve().parent
TERRAIN_PATH = ROOT / "dread-client-app" / "visualizer" / "terrain.json"
CONFIG_PATH = ROOT / "dread_direct_patch_config.json"

Point = Tuple[int, int]
Loop = List[Point]
FINITE = 10_000_000.0

SCENARIO_TO_REGION = {scenario: region for region, scenario in REGION_TO_SCENARIO.items()}
TOKEN_TO_REGION = {
    "cave": "Artaria",
    "magma": "Cataris",
    "baselab": "Dairon",
    "aqua": "Burenia",
    "forest": "Ghavoran",
    "quarantine": "Elun",
    "sanctuary": "Ferenia",
    "basesanc": "Ferenia",
    "shipyard": "Hanubia",
    "skybase": "Itorash",
    "commander": "Itorash",
}

# BMMAP sIconId → (kind, label). Item tanks stay off this layer — the visualizer
# already draws AP checks for those.
ICON_META: Dict[str, Tuple[str, str]] = {
    "UsableStationSave": ("save", "Save Station"),
    "UsableStationMap": ("map", "Map Station"),
    "UsableStationEnergy": ("energy", "Energy Recharge"),
    "UsableStationAmmo": ("ammo", "Ammo Recharge"),
    "UsableStationTotal": ("total", "Total Recharge"),
    "UsableAccessPoint": ("nav", "Navigation Station"),
    "UsableElevator": ("elevator", "Elevator"),
    "DisabledElevator": ("elevator", "Elevator"),
    "UsableTrain": ("tram", "Tram"),
    "UsableTransport": ("capsule", "Transport Capsule"),
    "UsableThermalDevice": ("device", "Thermal Device"),
    "UsableWaterValve": ("device", "Water Valve"),
    "UsablePowerGenerator": ("device", "Power Generator"),
    "UsableTeleportA": ("teleport", "Teleport A"),
    "UsableTeleportE": ("teleport", "Teleport E"),
    "UsableTeleportI": ("teleport", "Teleport I"),
    "UsableTeleportO": ("teleport", "Teleport O"),
    "UsableTeleportU": ("teleport", "Teleport U"),
    "UsableTeleportX": ("teleport", "Teleport X"),
    "UsableTeleportY": ("teleport", "Teleport Y"),
    "UsableTeleportZ": ("teleport", "Teleport Z"),
    "CentralUnit": ("cu", "Central Unit"),
    "Boss": ("boss", "Boss"),
    "BossDefeated": ("boss", "Boss"),
    "Gunship": ("ship", "Gunship"),
}


def snap_xy(x: float, y: float) -> Point:
    return int(round(float(x))), int(round(float(y)))


def _edge_key(a: Point, b: Point) -> Tuple[Point, Point]:
    return (a, b) if a < b else (b, a)


def boundary_edges(triangles: Sequence[Sequence[Point]]) -> List[Tuple[Point, Point]]:
    """Undirected edges that belong to exactly one triangle."""
    counts: Dict[Tuple[Point, Point], int] = defaultdict(int)
    for tri in triangles:
        if len(tri) < 3:
            continue
        a, b, c = tri[0], tri[1], tri[2]
        for u, v in ((a, b), (b, c), (c, a)):
            if u == v:
                continue
            counts[_edge_key(u, v)] += 1
    return [edge for edge, n in counts.items() if n == 1]


def chain_loops(edges: Sequence[Tuple[Point, Point]]) -> List[Loop]:
    """Walk unused boundary edges into closed loops."""
    adj: Dict[Point, List[Point]] = defaultdict(list)
    unused: set[Tuple[Point, Point]] = set()
    for a, b in edges:
        if a == b:
            continue
        key = _edge_key(a, b)
        if key in unused:
            continue
        unused.add(key)
        adj[a].append(b)
        adj[b].append(a)

    loops: List[Loop] = []
    while unused:
        start_a, start_b = next(iter(unused))
        unused.discard(_edge_key(start_a, start_b))
        path = [start_a, start_b]
        prev, cur = start_a, start_b
        while True:
            nxts = [
                p
                for p in adj[cur]
                if p != prev and _edge_key(cur, p) in unused
            ]
            if not nxts:
                break
            nxt = nxts[0]
            unused.discard(_edge_key(cur, nxt))
            path.append(nxt)
            prev, cur = cur, nxt
            if cur == path[0]:
                break
        if cur == path[0] and len(path) >= 4:
            loops.append(path[:-1])
    return loops


def collapse_collinear(loop: Sequence[Point]) -> Loop:
    """Drop vertices that sit on a straight run (axis-aligned or diagonal)."""
    pts = list(loop)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return pts
    out: Loop = []
    n = len(pts)
    for i in range(n):
        ax, ay = pts[(i - 1) % n]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % n]
        if (bx - ax) * (cy - by) == (by - ay) * (cx - bx):
            continue
        out.append((bx, by))
    return out if len(out) >= 3 else []


def loops_from_triangles(triangles: Sequence[Sequence[Point]]) -> List[Loop]:
    loops = []
    for loop in chain_loops(boundary_edges(triangles)):
        simple = collapse_collinear(loop)
        if simple:
            loops.append(simple)
    return loops


def _vec_xy(value: Any) -> Optional[Point]:
    if value is None:
        return None
    try:
        return snap_xy(value.x, value.y)
    except AttributeError:
        pass
    if isinstance(value, dict) and "x" in value and "y" in value:
        return snap_xy(value["x"], value["y"])
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return snap_xy(value[0], value[1])
    return None


def _geo_triangles(geo: Any) -> List[List[Point]]:
    verts_raw = getattr(geo, "aVertex", None) or (geo.get("aVertex") if isinstance(geo, dict) else None) or []
    idxs = list(getattr(geo, "aIndex", None) or (geo.get("aIndex") if isinstance(geo, dict) else None) or [])
    verts: List[Point] = []
    for vertex in verts_raw:
        point = _vec_xy(vertex)
        if point is None:
            return []
        verts.append(point)
    tris: List[List[Point]] = []
    for i in range(0, len(idxs) - 2, 3):
        a, b, c = int(idxs[i]), int(idxs[i + 1]), int(idxs[i + 2])
        if min(a, b, c) < 0 or max(a, b, c) >= len(verts):
            continue
        tris.append([verts[a], verts[b], verts[c]])
    return tris


def _geo_z(geo: Any) -> int:
    verts = getattr(geo, "aVertex", None) or (geo.get("aVertex") if isinstance(geo, dict) else None) or []
    if not verts:
        return 0
    first = verts[0]
    try:
        return int(round(float(first.z)))
    except AttributeError:
        if isinstance(first, dict) and "z" in first:
            return int(round(float(first["z"])))
    return 0


def loops_from_geos(geos: Iterable[Any], *, split_z: bool) -> List[dict]:
    """Return ``[{z, loops}, ...]`` or a single z=0 layer when *split_z* is false."""
    grouped: Dict[int, List[List[Point]]] = defaultdict(list)
    for geo in geos or []:
        tris = _geo_triangles(geo)
        if not tris:
            continue
        z = _geo_z(geo) if split_z else 0
        grouped[z].extend(tris)
    layers = []
    for z in sorted(grouped):
        loops = loops_from_triangles(grouped[z])
        if loops:
            layers.append({"z": z, "loops": [ [list(p) for p in loop] for loop in loops ]})
    return layers


def loops_from_geo_dict(mapping: Any) -> List[List[List[int]]]:
    out: List[List[List[int]]] = []
    if not mapping:
        return out
    values = mapping.values() if hasattr(mapping, "values") else []
    for geo in values:
        for layer in loops_from_geos([geo], split_z=False):
            out.extend(layer["loops"])
    return out


def _finite_box(box: Any) -> Optional[List[int]]:
    if box is None:
        return None
    try:
        min_x, min_y = float(box.Min.x), float(box.Min.y)
        max_x, max_y = float(box.Max.x), float(box.Max.y)
    except AttributeError:
        return None
    if max(abs(min_x), abs(min_y), abs(max_x), abs(max_y)) >= FINITE:
        return None
    x1, x2 = sorted((min_x, max_x))
    y1, y2 = sorted((min_y, max_y))
    if x2 - x1 < 1 or y2 - y1 < 1:
        return None
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


def _magnet_line(surface: Any) -> Optional[List[List[int]]]:
    poly = getattr(surface, "oPolyLine", None)
    segs = getattr(poly, "oSegmentData", None) if poly is not None else None
    if not segs:
        return None
    pts: List[List[int]] = []
    for seg in segs:
        point = _vec_xy(getattr(seg, "vPos", None))
        if point is None:
            continue
        if pts and pts[-1] == list(point):
            continue
        pts.append(list(point))
    return pts if len(pts) >= 2 else None


def classify_icon(icon_id: str) -> Optional[Tuple[str, str]]:
    """Return (kind, label) for a BMMAP ``sIconId``, or None to skip."""
    raw = str(icon_id or "")
    if raw in ICON_META:
        return ICON_META[raw]
    if raw.startswith("UsableTeleport") and len(raw) > len("UsableTeleport"):
        letter = raw[len("UsableTeleport") :]
        return "teleport", f"Teleport {letter}"
    return None


def dest_from_actor_name(name: str) -> str:
    """Guess the far side of a transport from its actor / sign name."""
    compact = str(name or "").lower().replace("-", "_")
    # Prefer explicit "fromX" (this pad's other end).
    for token, region in TOKEN_TO_REGION.items():
        if f"from{token}" in compact.replace("_", ""):
            return region
    hits = [region for token, region in TOKEN_TO_REGION.items() if token in compact]
    # Unique token wins (elevator_baselab_000 → Dairon).
    if len(set(hits)) == 1:
        return hits[0]
    return ""


def _entity_icon(name: Any, ent: Any, transports_by_name: Dict[str, str]) -> Optional[dict]:
    icon_id = str(getattr(ent, "sIconId", "") or "")
    meta = classify_icon(icon_id)
    if not meta:
        return None
    pos = _vec_xy(getattr(ent, "vPos", None))
    if pos is None:
        return None
    kind, label = meta
    dest = ""
    key = str(name)
    if key in transports_by_name:
        dest = SCENARIO_TO_REGION.get(transports_by_name[key], transports_by_name[key])
    if not dest:
        dest = dest_from_actor_name(key)
    letter = ""
    if kind == "teleport" and icon_id.startswith("UsableTeleport"):
        letter = icon_id[len("UsableTeleport") :]
    entry = {
        "name": key,
        "icon": icon_id,
        "kind": kind,
        "label": label,
        "x": pos[0],
        "y": pos[1],
    }
    if dest:
        entry["dest"] = dest
    if letter:
        entry["letter"] = letter
    return entry


def extract_map_icons(
    root: Any,
    transports_by_name: Dict[str, str],
    region: str = "",
) -> List[dict]:
    """Stations, elevators, trams, teleports, devices, CUs, bosses."""
    seen: set[Tuple[int, int, str]] = set()
    out: List[dict] = []
    layers = (
        getattr(root, "mapUsables", None),
        getattr(root, "mapCentralUnits", None),
        getattr(root, "mapBosses", None),
        getattr(root, "mapProps", None),
    )
    for mapping in layers:
        if not mapping:
            continue
        for name, ent in mapping.items():
            item = _entity_icon(name, ent, transports_by_name)
            if not item:
                continue
            if region and item.get("dest") == region:
                item.pop("dest", None)
            key = (item["x"], item["y"], item["kind"])
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    out.sort(key=lambda row: (row["kind"], row["y"], row["x"], row["name"]))
    return out


def resolve_romfs(path: Optional[Path] = None) -> Path:
    candidates: List[Path] = []
    if path:
        candidates.append(Path(path))
    if CONFIG_PATH.is_file():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        configured = Path(str(raw.get("base_rom_path") or ""))
        if configured:
            candidates.append(configured)
    candidates.extend(
        [
            Path(r"C:\Users\dummy\Downloads\md rando"),
            Path(r"C:\Users\dummy\Downloads\md modding"),
        ]
    )
    for cand in candidates:
        if (cand / "system" / "files.toc").is_file():
            return cand
        nested = cand / "romfs"
        if (nested / "system" / "files.toc").is_file():
            return nested
    raise FileNotFoundError(
        "No extracted Dread RomFS found. Set base_rom_path in dread_direct_patch_config.json."
    )


def extract_scenario_terrain(editor: Any, scenario: str) -> dict:
    root = editor.get_scenario_map(scenario).raw.Root
    terrain = loops_from_geos(root.aNavmeshGeos or [], split_z=True)
    occluders: List[List[List[int]]] = []
    for _room, cmap in (root.mapOccluderGeos or {}).items():
        values = cmap.values() if hasattr(cmap, "values") else []
        for geo in values:
            for layer in loops_from_geos([geo], split_z=False):
                occluders.extend(layer["loops"])

    doors = []
    for name, door in (root.mapDoors or {}).items():
        pos = _vec_xy(getattr(door, "vPos", None))
        if pos is None:
            continue
        entry = {
            "name": str(name),
            "x": pos[0],
            "y": pos[1],
        }
        left = _finite_box(getattr(door, "oBoxL", None))
        right = _finite_box(getattr(door, "oBoxR", None))
        if left:
            entry["left"] = left
        if right:
            entry["right"] = right
        doors.append(entry)

    magnets = []
    for _name, surface in (root.mapMagnetSurfaces or {}).items():
        line = _magnet_line(surface)
        if line:
            magnets.append(line)

    transports = []
    transports_by_name: Dict[str, str] = {}
    for name, sign in (root.mapTransportSigns or {}).items():
        start = _vec_xy(getattr(sign, "vPathStart", None))
        end = _vec_xy(getattr(sign, "vPathEnd", None))
        dest = str(getattr(sign, "sDestAreaId", "") or "")
        if dest:
            transports_by_name[str(name)] = dest
        if not start or not end:
            continue
        transports.append(
            {
                "name": str(name),
                "x1": start[0],
                "y1": start[1],
                "x2": end[0],
                "y2": end[1],
                "dest": dest,
            }
        )
    icons = extract_map_icons(root, transports_by_name, SCENARIO_TO_REGION.get(scenario, ""))

    blockages = []
    for name, ent in (root.mapBlockages or {}).items():
        box = _finite_box(getattr(ent, "oBox", None))
        pos = _vec_xy(getattr(ent, "vPos", None))
        if not box and pos is None:
            continue
        item = {"name": str(name), "icon": str(getattr(ent, "sIconId", "") or "")}
        if pos:
            item["x"] = pos[0]
            item["y"] = pos[1]
        if box:
            item["box"] = box
        blockages.append(item)

    return {
        "scenario": scenario,
        "terrain": terrain,
        "heat": loops_from_geo_dict(root.mapHeatRoomGeos),
        "water": loops_from_geo_dict(root.mapWaterPoolGeos),
        "freeze": loops_from_geo_dict(root.mapFreezeRoomGeos),
        "emmi": loops_from_geo_dict(root.mapEmmyRoomGeos),
        "occluders": occluders,
        "magnets": magnets,
        "doors": doors,
        "transports": transports,
        "blockages": blockages,
        "icons": icons,
    }


def build_visualizer_terrain(romfs: Optional[Path] = None) -> dict:
    from open_dread_rando.patcher_editor import PatcherEditor

    editor = PatcherEditor(resolve_romfs(romfs))
    regions: Dict[str, dict] = {}
    for region in REGION_ORDER:
        scenario = REGION_TO_SCENARIO.get(region)
        if not scenario:
            continue
        regions[region] = extract_scenario_terrain(editor, scenario)
    return {
        "coordinate_space": "dread_world_xy",
        "y_up": True,
        "source": "bmmap_navmesh",
        "region_order": [name for name in REGION_ORDER if name in regions],
        "regions": regions,
    }


def write_visualizer_terrain(
    path: Optional[Path] = None,
    romfs: Optional[Path] = None,
) -> Path:
    dest = path or TERRAIN_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = build_visualizer_terrain(romfs)
    dest.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return dest


if __name__ == "__main__":
    out = write_visualizer_terrain()
    data = json.loads(out.read_text(encoding="utf-8"))
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    for name in data.get("region_order") or []:
        region = data["regions"][name]
        loops = sum(len(layer.get("loops") or []) for layer in region.get("terrain") or [])
        pts = sum(
            len(loop)
            for layer in region.get("terrain") or []
            for loop in layer.get("loops") or []
        )
        print(
            f"  {name}: {loops} terrain loops ({pts} pts), "
            f"{len(region.get('heat') or [])} heat, "
            f"{len(region.get('water') or [])} water, "
            f"{len(region.get('emmi') or [])} emmi, "
            f"{len(region.get('doors') or [])} doors, "
            f"{len(region.get('magnets') or [])} magnets, "
            f"{len(region.get('icons') or [])} icons"
        )

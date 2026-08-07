
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .logic_parser import REGION_FILES, read_database_bytes

NodeId = Tuple[str, str, str]

LOGIC_DB = Path(__file__).parent / "logic_database"
DEFAULT_START: NodeId = ("Artaria", "Intro Room", "Start Point")
DEFAULT_PATCHER_REF = {"scenario": "s010_cave", "actor": "StartPoint0"}

@dataclass(frozen=True)
class StartingLocationInfo:
    region: str
    area: str
    node: str
    scenario: str
    actor: str

    @property
    def node_id(self) -> NodeId:
        return (self.region, self.area, self.node)

    @property
    def path(self) -> str:
        return f"{self.region}/{self.area}/{self.node}"

    @property
    def display_name(self) -> str:
        return f"{self.region} - {self.area} - {self.node}"

    @property
    def option_key(self) -> str:
        raw = f"{self.region}_{self.area}_{self.node}".lower()
        raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
        return raw

    @property
    def patcher_ref(self) -> Dict[str, str]:
        return {"scenario": self.scenario, "actor": self.actor}

    @property
    def is_default(self) -> bool:
        return self.node_id == DEFAULT_START

_CACHE: Optional[List[StartingLocationInfo]] = None
_BY_PATH: Optional[Dict[str, StartingLocationInfo]] = None
_BY_OPTION: Optional[Dict[str, StartingLocationInfo]] = None

def load_starting_locations() -> List[StartingLocationInfo]:
    global _CACHE, _BY_PATH, _BY_OPTION
    if _CACHE is not None:
        return _CACHE

    starts: List[StartingLocationInfo] = []
    for region_file in REGION_FILES:
        try:
            region_bytes = read_database_bytes(region_file, LOGIC_DB)
        except (FileNotFoundError, OSError):
            continue
        data = json.loads(region_bytes.decode("utf-8"))
        region = data.get("name") or Path(region_file).stem
        scenario = (data.get("extra") or {}).get("scenario_id")
        if not scenario:
            continue
        for area_name, area in (data.get("areas") or {}).items():
            for node_name, node in (area.get("nodes") or {}).items():
                if not node.get("valid_starting_location"):
                    continue
                actor = (node.get("extra") or {}).get("start_point_actor_name")
                if not actor:
                    continue
                starts.append(
                    StartingLocationInfo(
                        region=region,
                        area=area_name,
                        node=node_name,
                        scenario=scenario,
                        actor=actor,
                    )
                )

    starts.sort(key=lambda s: (not s.is_default, s.path))
    _CACHE = starts
    _BY_PATH = {s.path: s for s in starts}
    _BY_OPTION = {s.option_key: s for s in starts}
    return starts

def get_by_path(path: str) -> Optional[StartingLocationInfo]:
    load_starting_locations()
    assert _BY_PATH is not None
    return _BY_PATH.get(path)

def get_by_option_key(key: str) -> Optional[StartingLocationInfo]:
    load_starting_locations()
    assert _BY_OPTION is not None
    return _BY_OPTION.get(key)

def get_default() -> StartingLocationInfo:
    info = get_by_path(f"{DEFAULT_START[0]}/{DEFAULT_START[1]}/{DEFAULT_START[2]}")
    if info is not None:
        return info
    return StartingLocationInfo(
        region=DEFAULT_START[0],
        area=DEFAULT_START[1],
        node=DEFAULT_START[2],
        scenario=DEFAULT_PATCHER_REF["scenario"],
        actor=DEFAULT_PATCHER_REF["actor"],
    )

def patcher_ref_for_node(node: NodeId) -> Dict[str, str]:
    path = f"{node[0]}/{node[1]}/{node[2]}"
    info = get_by_path(path)
    if info is not None:
        return info.patcher_ref
    if node == DEFAULT_START:
        return dict(DEFAULT_PATCHER_REF)
    raise KeyError(f"No patcher start ref for {path}")

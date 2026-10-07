"""Dock-rando pools and config loaded from logic_database/header.json."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Optional

from worlds.metroid_bread.logic.logic_parser import read_database_bytes

# Use real files for standalone tools and pkgutil for zip installs.
_LOGIC_DB = Path(__file__).resolve().parents[1] / "logic_database"

# Door types AP can use as new Individual Doors locks.
BASIC_ODR_DOOR_TYPES: FrozenSet[str] = frozenset({
    "power_beam",
    "charge_beam",
    "grapple_beam",
    "wide_beam",
    "wave_beam",
    "plasma_beam",
    "missile",
    "super_missile",
    "ice_missile",
    "storm_missile",
    "diffusion_beam",
    "bomb",
    "cross_bomb",
    "power_bomb",
})

# Keep the longer Phase-2 name for callers using it.
EXPANDED_ODR_DOOR_TYPES: FrozenSet[str] = BASIC_ODR_DOOR_TYPES

# Never use these unsupported door types as patch targets.
ODR_CANNOT_ADD_DOOR_TYPES: FrozenSet[str] = frozenset({
    "phantom_cloak",
    "phase_shift",
})

# Exclude dead doors because AP cannot restore them safely.
DEFERRED_CHANGE_TO_DOOR_TYPES: FrozenSet[str] = frozenset({
    "closed",
})

# Actor types ODR recognizes as doors.
ODR_PATCHABLE_DOOR_ACTORDEFS: FrozenSet[str] = frozenset({
    "doorframe",
    "doorpowerpower",
    "doorpowerclosed",
    "doorclosedpower",
    "doorchargecharge",
    "doorchargeclosed",
    "doorclosedcharge",
    "doorgrapplegrapple",
    "doorgrappleclosed",
    "doorclosedgrapple",
    "doorpresencepresence",
    "doorframepresence",
    "doorpresenceframe",
})

# Ignore weaknesses that ODR does not recognize as door types.
NON_PATCHABLE_SOURCE_WEAKNESSES: FrozenSet[str] = frozenset({
    "Phase Shift Door",
    "Artaria Thermal Door",
    "Cataris Thermal Door",
    "Dairon Power Switch 1 Powered Door",
    "Dairon Power Switch 2 Powered Door",
})

_ACTOR_FAMILY_RE = re.compile(r"^([a-z][a-z0-9]*)(?:_\d+)?$", re.IGNORECASE)


def actor_def_family(actor_name: str) -> str:
    """``doorshutter_001`` → ``doorshutter``; ``doorpowerpower_000`` → ``doorpowerpower``."""
    name = str(actor_name or "").strip()
    if not name:
        return ""
    match = _ACTOR_FAMILY_RE.match(name)
    if match:
        return match.group(1).lower()
    return name.lower()


def actor_def_basename(actor_def: Optional[str]) -> str:
    """``actordef:actors/props/doorshutter/charclasses/doorshutter.bmsad`` → ``doorshutter``."""
    if not actor_def:
        return ""
    text = str(actor_def)
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    if text.endswith(".bmsad"):
        text = text[: -len(".bmsad")]
    return text.lower()


def is_odr_patchable_door_actor(
    actor_name: str,
    actor_def: Optional[str] = None,
) -> bool:
    """True when Mercury *instance* name is one ODR ``door_actor_to_type`` can ID."""
    family = actor_def_family(actor_name)
    if family not in ODR_PATCHABLE_DOOR_ACTORDEFS:
        return False
    if actor_def:
        basename = actor_def_basename(actor_def)
        if basename and basename not in ODR_PATCHABLE_DOOR_ACTORDEFS:
            return False
    return True


def is_patchable_door_source_node(node: dict) -> bool:
    """Dock is eligible as a physical door-rando source for ODR patches."""
    weakness = node.get("default_dock_weakness") or ""
    if weakness in NON_PATCHABLE_SOURCE_WEAKNESSES:
        return False
    extra = node.get("extra") or {}
    actor = extra.get("actor_name")
    if not actor:
        return False
    return is_odr_patchable_door_actor(str(actor), extra.get("actor_def"))


@lru_cache(maxsize=1)
def _header() -> dict:
    return json.loads(read_database_bytes("header.json", _LOGIC_DB).decode("utf-8"))


def _door_type_block() -> dict:
    dock_db = _header().get("dock_weakness_database") or {}
    types = dock_db.get("types") or {}
    return types.get("door") or {}


@lru_cache(maxsize=1)
def weakness_odr_types() -> Dict[str, str]:
    """Map weakness display name → ODR ``extra.type`` (when present)."""
    items = (_door_type_block().get("items") or {})
    out: Dict[str, str] = {}
    for name, data in items.items():
        if not isinstance(data, dict):
            continue
        odr = (data.get("extra") or {}).get("type")
        if odr:
            out[str(name)] = str(odr)
    return out


@lru_cache(maxsize=1)
def door_dock_rando_pools() -> dict:
    """``unlocked`` / ``locked`` / ``change_from`` / ``change_to`` for door type."""
    block = (_door_type_block().get("dock_rando") or {})
    return {
        "unlocked": block.get("unlocked") or "Power Beam Door",
        "locked": block.get("locked") or "Access Permanently Closed",
        "change_from": list(block.get("change_from") or []),
        "change_to": list(block.get("change_to") or []),
    }


@lru_cache(maxsize=1)
def dock_rando_config() -> dict:
    """Global dock_rando knobs (proportion, two-way, resolver budget)."""
    dock_db = _header().get("dock_weakness_database") or {}
    cfg = dock_db.get("dock_rando") or {}
    return {
        "force_change_two_way": bool(cfg.get("force_change_two_way", True)),
        "resolver_attempts": int(cfg.get("resolver_attempts") or 250),
        "to_shuffle_proportion": float(cfg.get("to_shuffle_proportion") or 0.6),
    }


def unlocked_weakness() -> str:
    return str(door_dock_rando_pools()["unlocked"])


def locked_weakness() -> str:
    return str(door_dock_rando_pools()["locked"])


def header_change_from() -> FrozenSet[str]:
    return frozenset(door_dock_rando_pools()["change_from"])


def header_change_to() -> FrozenSet[str]:
    return frozenset(door_dock_rando_pools()["change_to"])


def basic_change_to_weaknesses() -> FrozenSet[str]:
    """RDV change_to ∩ Phase-2 ODR-addable types (excl. Closed / Sensor)."""
    odr = weakness_odr_types()
    out = set()
    for name in header_change_to():
        dt = odr.get(name)
        if not dt or dt in ODR_CANNOT_ADD_DOOR_TYPES:
            continue
        if dt in DEFERRED_CHANGE_TO_DOOR_TYPES:
            continue
        if dt in BASIC_ODR_DOOR_TYPES:
            out.add(name)
    return frozenset(out)


def to_shuffle_proportion() -> float:
    """Legacy header proportion (0.6). Prefer ``reroute_shuffle_proportion``."""
    return float(dock_rando_config()["to_shuffle_proportion"])


def reroute_shuffle_proportion() -> float:
    """Fraction of non-assist eligible docks that enter the reroute (lock) set."""
    return 0.85


def force_change_two_way() -> bool:
    return bool(dock_rando_config()["force_change_two_way"])


def odr_type_for_weakness(weakness: str) -> Optional[str]:
    return weakness_odr_types().get(weakness)


def patchable_door_types() -> FrozenSet[str]:
    """ODR door_type strings allowed in door_patches (Phase-2 expanded pool)."""
    return EXPANDED_ODR_DOOR_TYPES

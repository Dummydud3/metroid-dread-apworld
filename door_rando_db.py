"""Dock-rando pools and config loaded from logic_database/header.json.

Source of truth for RDV Individual Doors parameters (change_from / change_to /
unlocked / locked / to_shuffle_proportion / force_change_two_way). AP still
intersects change_to with the basic ODR-safe beam/missile/grapple pool until
Phase 4.

Reads header.json via ``logic_parser.read_database_bytes`` so this works from a
loose ``worlds/metroid_bread`` folder *and* from ``metroid_bread.apworld``
(zipimport). Plain ``Path.open`` fails inside .apworld and aborts world load,
which hides the Metroid Bread Client from the Archipelago Launcher.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Optional

from .logic_parser import read_database_bytes

# Filesystem fallback for standalone tooling; zip-safe path uses pkgutil.
_LOGIC_DB = Path(__file__).resolve().parent / "logic_database"

# ODR-safe basic targets (Phase 2). Blast / closed stay out until Phase 4.
BASIC_ODR_DOOR_TYPES: FrozenSet[str] = frozenset({
    "power_beam",
    "charge_beam",
    "grapple_beam",
    "wide_beam",
    "wave_beam",
    "plasma_beam",
    "missile",
    "super_missile",
})

# Never emit as patch targets (ODR can_be_added=False or not a DoorType).
ODR_CANNOT_ADD_DOOR_TYPES: FrozenSet[str] = frozenset({
    "phantom_cloak",
    "phase_shift",
})

# Mercury actordef bases ODR ``DoorType`` / ``ActorData`` can identify as doors.
# Source: open_dread_rando.door_locks.door_patcher.ActorData (DOOR_* only).
# ``doorshutter`` / ``doorheat`` are deliberately absent — ``door_actor_to_type``
# raises ``ValueError: ... is not a patchable door!`` for those actors.
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

# Weaknesses that are never ODR DoorType sources (missing / non-enum ``extra.type``).
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
    """True when Mercury *instance* name is one ODR ``door_actor_to_type`` can ID.

    Requires the actor instance family (``doorpowerpower_000`` → ``doorpowerpower``)
    to be in ``ODR_PATCHABLE_DOOR_ACTORDEFS``. Symbolic labels like
    ``Door006 (CG-CG)`` are rejected even if ``actor_def`` points at a real door —
    ODR patches need the Mercury instance name, not the logic display label.

    When ``actor_def`` is provided, it must also resolve to an allowlisted
    basename (defense against mislabeled props).
    """
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
    """RDV change_to ∩ basic ODR types, excluding non-addable."""
    odr = weakness_odr_types()
    out = set()
    for name in header_change_to():
        dt = odr.get(name)
        if not dt or dt in ODR_CANNOT_ADD_DOOR_TYPES:
            continue
        if dt in BASIC_ODR_DOOR_TYPES:
            out.add(name)
    return frozenset(out)


def to_shuffle_proportion() -> float:
    return float(dock_rando_config()["to_shuffle_proportion"])


def force_change_two_way() -> bool:
    return bool(dock_rando_config()["force_change_two_way"])


def odr_type_for_weakness(weakness: str) -> Optional[str]:
    return weakness_odr_types().get(weakness)


def patchable_door_types() -> FrozenSet[str]:
    """ODR door_type strings allowed in door_patches (basic pool for now)."""
    return BASIC_ODR_DOOR_TYPES

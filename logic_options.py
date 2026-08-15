"""
Logic-relevant option values for generation ↔ client tracker parity.

The Hub / map tracker builds a lightweight DreadLogic world. Without these
values (especially trick difficulties), it silently assumes Disabled and
disagrees with the spoiler playthrough for Expert / trick-heavy seeds.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional

from .dread_logic import TRICK_TO_OPTION

# Ammo / DNA / misc-patch settings DreadLogic reads via world.options.<name>.value
_EXTRA_LOGIC_OPTIONS = (
    "required_dna",
    "energy_per_tank",
    "starting_power_bombs",
    "power_bomb_tank_ammo",
    "nerf_power_bombs",
    "door_lock_rando",
    "transport_rando",
)

LOGIC_OPTION_NAMES: tuple[str, ...] = tuple(
    sorted(set(TRICK_TO_OPTION.values()) | set(_EXTRA_LOGIC_OPTIONS))
)

# Spoiler header labels (Options.display_name) → option field
_SPOILER_LABEL_TO_OPTION: Dict[str, str] = {
    "Knowledge Tricks": "knowledge_tricks",
    "Movement Tricks": "movement_tricks",
    "Combat Tricks": "combat_tricks",
    "Pseudo-Wave Beam": "pseudo_wave",
    "Infinite Bomb Jump (IBJ)": "infinite_bomb_jump",
    "Water Bomb Jump (WBJ)": "water_bomb_jump",
    "Water Space Jump (WSJ)": "water_space_jump",
    "Single-wall Wall Jump (SWJ)": "single_wall_wall_jump",
    "Slide Jump": "slide_jump",
    "Speed Booster Conservation": "speedbooster_conservation",
    "Wall Jump Tricks": "wall_jump_tricks",
    "Heat/Cold Runs (Suitless)": "heat_cold_runs",
    "Reverse Grapple Block": "reverse_grapple_block",
    "Damage Boost": "damage_boost",
    "Stand on Frozen Enemy": "stand_on_frozen_enemy",
    "Grapple Movement": "grapple_movement",
    "Cross Bomb Skip": "cross_bomb_skip",
    "Climb Sloped Tunnels": "climb_sloped_tunnels",
    "Short Boost": "short_boost",
    "Diffusion Abuse": "diffusion_abuse",
    "Flash Shift Skip": "flash_shift_skip",
    "Diagonal Bomb Jump (DBJ)": "diagonal_bomb_jump",
    "Ledge Warp": "ledge_warp",
    "Cross Bomb Launch (CBL)": "cross_bomb_launch",
    "Floor Clip": "floor_clip",
    "Climb Sloped Surfaces": "climb_sloped_surfaces",
    "Required Metroid DNA": "required_dna",
    "Energy Per Tank": "energy_per_tank",
    "Starting Power Bombs": "starting_power_bombs",
    "Power Bomb Tank Ammo": "power_bomb_tank_ammo",
    "Nerf Power Bombs": "nerf_power_bombs",
    "Door Lock Randomizer": "door_lock_rando",
    "Transport Randomizer": "transport_rando",
}

_DIFFICULTY_WORDS: Dict[str, int] = {
    "disabled": 0,
    "beginner": 1,
    "easy": 2,
    "medium": 3,
    "hard": 4,
    "expert": 5,
    "yes": 1,
    "no": 0,
    "true": 1,
    "false": 0,
    "on": 1,
    "off": 0,
}


def collect_logic_options_from_options(options: Any) -> Dict[str, int]:
    """Read int values for all tracker-relevant options from a world.options object."""
    out: Dict[str, int] = {}
    for name in LOGIC_OPTION_NAMES:
        opt = getattr(options, name, None)
        if opt is None:
            continue
        try:
            out[name] = int(opt.value)
        except Exception:
            continue
    return out


def coerce_logic_options(raw: Any) -> Dict[str, int]:
    """Normalize a mapping of option name → value into int counts."""
    if not isinstance(raw, Mapping):
        return {}
    out: Dict[str, int] = {}
    for key, val in raw.items():
        name = str(key)
        if name not in LOGIC_OPTION_NAMES:
            continue
        try:
            out[name] = int(val)
        except Exception:
            continue
    return out


def parse_logic_options_from_spoiler_text(text: str) -> Dict[str, int]:
    """
    Parse trick / ammo settings from a full Archipelago spoiler header.

    Synthetic server spoilers often omit this block; full generate spoilers include
    lines like ``Knowledge Tricks:                Expert``.
    """
    if not text:
        return {}
    out: Dict[str, int] = {}
    # Stop at placements / playthrough so we don't match location names.
    header = text
    for marker in ("\nLocations:", "\nPlaythrough:", "\nDREAD_PATCH_EXTRAS_JSON:"):
        idx = header.find(marker)
        if idx >= 0:
            header = header[:idx]
    for label, opt_name in _SPOILER_LABEL_TO_OPTION.items():
        m = re.search(
            rf"^{re.escape(label)}:\s*(.+?)\s*$",
            header,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if not m:
            continue
        raw = m.group(1).strip()
        key = raw.lower()
        if key in _DIFFICULTY_WORDS:
            out[opt_name] = _DIFFICULTY_WORDS[key]
            continue
        try:
            out[opt_name] = int(raw)
        except Exception:
            continue
    return out


def merge_logic_option_sources(
    *sources: tuple[str, Mapping[str, int]],
) -> tuple[Dict[str, int], Optional[str]]:
    """
    Merge option dicts in priority order (first non-empty source wins per key).

    Returns (merged, primary_source_name) where primary is the first source that
    contributed any trick option (not just ammo defaults).
    """
    trick_names = set(TRICK_TO_OPTION.values())
    merged: Dict[str, int] = {}
    primary: Optional[str] = None
    for source_name, mapping in sources:
        if not mapping:
            continue
        contributed_trick = False
        for key, val in mapping.items():
            if key not in LOGIC_OPTION_NAMES:
                continue
            if key not in merged:
                merged[key] = int(val)
                if key in trick_names:
                    contributed_trick = True
        if primary is None and contributed_trick:
            primary = source_name
    return merged, primary

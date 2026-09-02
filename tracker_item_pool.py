"""Hub Map Tracker item-pool helpers (generation snapshot + old-seed fallback)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    try:
        return bool(int(value))
    except Exception:
        return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _pick(sources: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in sources and sources[key] is not None:
            return sources[key]
    return default


def synthesize_tracker_item_pool(
    sources: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, int]]:
    """
    Approximate seed item pool from progressive_* / tank / DNA / FS / SB options.

    Used by the Hub client when slot_data lacks ``tracker_item_pool`` (older seeds).
    Returns None when progressive options are unavailable so the tracker shows all icons.
    """
    if not isinstance(sources, Mapping) or not sources:
        return None

    # Require at least one progressive_* key so we do not invent a wrong filter.
    progressive_keys = (
        "progressive_beams",
        "progressive_charge",
        "progressive_missiles",
        "progressive_bombs",
        "progressive_suit",
        "progressive_spin",
    )
    if not any(k in sources for k in progressive_keys):
        return None

    pool: Dict[str, int] = {}

    if _as_bool(_pick(sources, "progressive_beams"), True):
        pool["Progressive Beam"] = 3
    else:
        pool["Wide Beam"] = 1
        pool["Plasma Beam"] = 1
        pool["Wave Beam"] = 1

    if _as_bool(_pick(sources, "progressive_charge"), True):
        pool["Progressive Charge Beam"] = 2
    else:
        pool["Charge Beam"] = 1
        pool["Diffusion Beam"] = 1

    if _as_bool(_pick(sources, "progressive_missiles"), False):
        pool["Progressive Missiles"] = 2
    else:
        pool["Super Missile"] = 1
        pool["Ice Missile"] = 1
    pool["Storm Missile"] = 1

    if _as_bool(_pick(sources, "progressive_bombs"), True):
        pool["Progressive Bombs"] = 2
    else:
        pool["Bomb"] = 1
        pool["Cross Bomb"] = 1

    if _as_bool(_pick(sources, "progressive_suit"), True):
        pool["Progressive Suit"] = 2
    else:
        pool["Varia Suit"] = 1
        pool["Gravity Suit"] = 1

    if _as_bool(_pick(sources, "progressive_spin"), True):
        pool["Progressive Spin"] = 2
    else:
        pool["Spin Boost"] = 1
        pool["Space Jump"] = 1

    for name in (
        "Grapple Beam",
        "Phantom Cloak",
        "Morph Ball",
        "Power Bomb",
        "Spider Magnet",
        "Speed Booster",
        "Screw Attack",
        "Pulse Radar",
    ):
        pool[name] = 1

    try:
        try:
            from .flash_shift import plan_from_extras
        except ImportError:
            from flash_shift import plan_from_extras

        if "vanilla_flash_shift_behaviour" in sources:
            fs_plan = plan_from_extras(sources)
        else:
            # Options defaults: vanilla Flash Shift on → one main, no upgrades.
            fs_plan = {"main_count": 1, "upgrade_count": 0}
    except Exception:
        fs_plan = {
            "main_count": 1,
            "upgrade_count": 0,
        }
    main_n = int(fs_plan.get("main_count") or 0)
    up_n = int(fs_plan.get("upgrade_count") or 0)
    if main_n > 0:
        pool["Flash Shift"] = main_n
    if up_n > 0:
        pool["Flash Shift Upgrade"] = up_n

    sb_up = _as_int(_pick(sources, "speed_booster_upgrade_count"), 0)
    if sb_up > 0:
        pool["Speed Booster Upgrade"] = sb_up

    energy_tanks = _as_int(_pick(sources, "energy_tanks"), 8)
    energy_parts = _as_int(_pick(sources, "energy_parts"), 16)
    missile_tanks = _as_int(_pick(sources, "missile_tanks"), 35)
    missile_plus = _as_int(_pick(sources, "missile_plus_tanks"), 10)
    pb_tanks = _as_int(_pick(sources, "power_bomb_tanks"), 12)
    if energy_tanks > 0:
        pool["Energy Tank"] = energy_tanks
    if energy_parts > 0:
        pool["Energy Part"] = energy_parts
    # Mirror create_items: FS upgrades displace Missile Tank filler 1:1.
    if up_n > 0:
        missile_tanks = max(0, missile_tanks - up_n)
    if missile_tanks > 0:
        pool["Missile Tank"] = missile_tanks
    if missile_plus > 0:
        pool["Missile+ Tank"] = missile_plus
    if pb_tanks > 0:
        pool["Power Bomb Tank"] = pb_tanks

    required_dna = _as_int(
        _pick(sources, "required_dna", "required_artifacts"),
        0,
    )
    if required_dna > 0:
        pool["Metroid DNA"] = required_dna

    return {name: count for name, count in pool.items() if count > 0}


def normalize_tracker_item_pool(raw: Any) -> Optional[Dict[str, int]]:
    """Coerce a slot/patch pool dict to name→count (>0 only)."""
    if not isinstance(raw, Mapping) or not raw:
        return None
    out: Dict[str, int] = {}
    for name, count in raw.items():
        try:
            n = int(count)
        except Exception:
            continue
        if n > 0 and name:
            out[str(name)] = n
    return out or None


def merge_option_sources(*maps: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Shallow-merge mappings; later maps win. Skips non-dicts."""
    out: Dict[str, Any] = {}
    for m in maps:
        if isinstance(m, Mapping):
            out.update(m)
    return out

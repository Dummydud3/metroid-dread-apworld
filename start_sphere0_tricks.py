"""Minimum trick upgrades that open sphere 0 without raising Starting Items."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Keep in sync with Hub TRICKS list / Options trick fields (difficulty 0–5).
TRICK_KEYS: Tuple[str, ...] = (
    "knowledge_tricks",
    "movement_tricks",
    "combat_tricks",
    "slide_jump",
    "wall_jump_tricks",
    "infinite_bomb_jump",
    "water_bomb_jump",
    "water_space_jump",
    "single_wall_wall_jump",
    "diagonal_bomb_jump",
    "cross_bomb_launch",
    "grapple_movement",
    "speedbooster_conservation",
    "short_boost",
    "flash_shift_skip",
    "heat_cold_runs",
    "climb_sloped_tunnels",
    "climb_sloped_surfaces",
    "floor_clip",
    "damage_boost",
    "pseudo_wave",
    "diffusion_abuse",
    "stand_on_frozen_enemy",
    "cross_bomb_skip",
    "ledge_warp",
)

TRICK_DISPLAY: Dict[str, str] = {
    "knowledge_tricks": "Knowledge",
    "movement_tricks": "Movement",
    "combat_tricks": "Combat",
    "slide_jump": "Slide Jump",
    "wall_jump_tricks": "Wall Jump",
    "infinite_bomb_jump": "Infinite Bomb Jump",
    "water_bomb_jump": "Water Bomb Jump",
    "water_space_jump": "Water Space Jump",
    "single_wall_wall_jump": "Single-wall Wall Jump",
    "diagonal_bomb_jump": "Diagonal Bomb Jump",
    "cross_bomb_launch": "Cross Bomb Launch",
    "grapple_movement": "Grapple Movement",
    "speedbooster_conservation": "Speed Booster Conservation",
    "short_boost": "Short Boost",
    "flash_shift_skip": "Flash Shift Skip",
    "heat_cold_runs": "Heat/Cold Runs",
    "climb_sloped_tunnels": "Climb Sloped Tunnels",
    "climb_sloped_surfaces": "Climb Sloped Surfaces",
    "floor_clip": "Floor Clip",
    "damage_boost": "Damage Boost",
    "pseudo_wave": "Pseudo-Wave Beam",
    "diffusion_abuse": "Diffusion Abuse",
    "stand_on_frozen_enemy": "Stand on Frozen Enemy",
    "cross_bomb_skip": "Cross Bomb Skip",
    "ledge_warp": "Ledge Warp",
}

LEVEL_NAMES: Tuple[str, ...] = (
    "Disabled",
    "Beginner",
    "Intermediate",
    "Advanced",
    "Expert",
    "Ludicrous",
)


def level_name(level: int) -> str:
    if 0 <= level < len(LEVEL_NAMES):
        return LEVEL_NAMES[level]
    return str(level)


def format_trick_alt(entries: Optional[Sequence[Dict[str, Any]]]) -> str:
    """Human line for Hub: 'Slide Jump at Beginner+' / comma-separated."""
    if not entries:
        return ""
    parts: List[str] = []
    for e in entries:
        name = e.get("display") or TRICK_DISPLAY.get(str(e.get("key")), str(e.get("key")))
        lvl = e.get("level_name") or level_name(int(e.get("level", 0)))
        parts.append(f"{name} at {lvl}+")
    return ", ".join(parts)


def _budget_meets(world, budget: int) -> bool:
    from . import StartKit

    budget = max(0, int(budget))
    if budget <= 0:
        return StartKit.start_checks(world, {}) >= StartKit.MIN_START_LOCATIONS
    kit = StartKit.build_start_kit(world, max_kit=budget)
    return (
        StartKit.start_checks(world, StartKit.kit_counts(kit))
        >= StartKit.MIN_START_LOCATIONS
    )


def _entries(pairs: Iterable[Tuple[str, int]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, level in pairs:
        out.append(
            {
                "key": key,
                "level": int(level),
                "display": TRICK_DISPLAY.get(key, key),
                "level_name": level_name(int(level)),
            }
        )
    return out


def find_min_trick_alt(world, budget: int) -> Optional[List[Dict[str, Any]]]:
    """
    Smallest trick raise(s) from the world's *current* trick levels so
    Starting Items=``budget`` already opens sphere 0 (≥ MIN_START_LOCATIONS).

    Mutates ``world.options`` temporarily; always restores the baseline.
    Prefers one trick at the lowest level; otherwise a subtractive-greedy
    subset of tricks raised from all-max. Returns None if impossible.
    """
    opts = world.options._values
    baseline = {k: int(opts.get(k, 0)) for k in TRICK_KEYS}

    def apply(overlay: Dict[str, int]) -> None:
        opts.update(overlay)
        world.logic.clear_cache()

    def restore() -> None:
        apply(dict(baseline))

    if _budget_meets(world, budget):
        return None

    all_max = {k: max(baseline[k], 5) for k in TRICK_KEYS}
    apply({**baseline, **all_max})
    ok_max = _budget_meets(world, budget)
    restore()
    if not ok_max:
        return None

    # --- single trick (optimal when one suffices) ---
    best_single: Optional[Tuple[int, int, str, int]] = None  # delta, level, key, level
    for key in TRICK_KEYS:
        cur = baseline[key]
        if cur >= 5:
            continue
        for level in range(cur + 1, 6):
            apply({**baseline, key: level})
            ok = _budget_meets(world, budget)
            restore()
            if ok:
                cand = (level - cur, level, key, level)
                if best_single is None or cand < best_single:
                    best_single = cand
                break
    if best_single is not None:
        _k, _lvl = best_single[2], best_single[3]
        return _entries([(_k, _lvl)])

    # --- multi-trick: start at all-max, lower each trick as far as possible ---
    state = dict(all_max)
    apply(state)
    for key in TRICK_KEYS:
        if state[key] <= baseline[key]:
            continue
        kept = state[key]
        # Try baseline first (drop this trick entirely).
        state[key] = baseline[key]
        apply(state)
        if _budget_meets(world, budget):
            continue
        # Smallest level that still works.
        found_lvl = kept
        for level in range(baseline[key] + 1, kept + 1):
            state[key] = level
            apply(state)
            if _budget_meets(world, budget):
                found_lvl = level
                break
        state[key] = found_lvl
        apply(state)

    raised = [(k, state[k]) for k in TRICK_KEYS if state[k] > baseline[k]]
    restore()
    return _entries(raised) if raised else None


def find_min_tricks_for_full_accessibility(
    world,
    *,
    has_uncleared,
) -> Tuple[Optional[List[Dict[str, Any]]], bool]:
    """
    Smallest trick raise(s) so ``has_uncleared()`` is False (Full accessibility).

    ``has_uncleared`` is a zero-arg callable that inspects the world after option
    mutations. Mutates ``world.options`` temporarily; always restores baseline.

    Returns ``(entries_or_None, solvable_with_tricks)``.
    - solvable False: still uncleared even with every trick at Ludicrous.
    - entries None + solvable True: already clear (caller shouldn't invoke).
    """
    opts = world.options._values
    baseline = {k: int(opts.get(k, 0)) for k in TRICK_KEYS}

    def apply(overlay: Dict[str, int]) -> None:
        opts.update(overlay)
        world.logic.clear_cache()

    def restore() -> None:
        apply(dict(baseline))

    if not has_uncleared():
        return None, True

    all_max = {k: max(baseline[k], 5) for k in TRICK_KEYS}
    apply({**baseline, **all_max})
    ok_max = not has_uncleared()
    restore()
    if not ok_max:
        return None, False

    best_single: Optional[Tuple[int, int, str, int]] = None
    for key in TRICK_KEYS:
        cur = baseline[key]
        if cur >= 5:
            continue
        for level in range(cur + 1, 6):
            apply({**baseline, key: level})
            ok = not has_uncleared()
            restore()
            if ok:
                cand = (level - cur, level, key, level)
                if best_single is None or cand < best_single:
                    best_single = cand
                break
    if best_single is not None:
        return _entries([(best_single[2], best_single[3])]), True

    state = dict(all_max)
    apply(state)
    for key in TRICK_KEYS:
        if state[key] <= baseline[key]:
            continue
        kept = state[key]
        state[key] = baseline[key]
        apply(state)
        if not has_uncleared():
            continue
        found_lvl = kept
        for level in range(baseline[key] + 1, kept + 1):
            state[key] = level
            apply(state)
            if not has_uncleared():
                found_lvl = level
                break
        state[key] = found_lvl
        apply(state)

    raised = [(k, state[k]) for k in TRICK_KEYS if state[k] > baseline[k]]
    restore()
    return (_entries(raised) if raised else None), True

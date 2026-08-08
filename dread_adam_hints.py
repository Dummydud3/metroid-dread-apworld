"""
Adam Nav Station hints for open-dread-rando (DIAG_ADAM_* via patcher hints[]).

Matches Randovania's 11 access-point terminals. Texts use Dread color codes:
  {c1} item  {c5} region  {c0} reset  {c4} joke
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

# Fixed terminals — actors from Randovania / sample_patcher_WORKING.json
ADAM_HINT_TERMINALS: List[dict] = [
    {"hint_id": "CAVE_1", "accesspoint_actor": {"scenario": "s010_cave", "actor": "PRP_CV_AccessPoint001"}},
    {"hint_id": "CAVE_2", "accesspoint_actor": {"scenario": "s010_cave", "actor": "PRP_CV_AccessPoint002"}},
    {"hint_id": "MAGMA_1", "accesspoint_actor": {"scenario": "s020_magma", "actor": "accesspoint"}},
    {"hint_id": "MAGMA_2", "accesspoint_actor": {"scenario": "s020_magma", "actor": "accesspoint_000"}},
    {"hint_id": "LAB_1", "accesspoint_actor": {"scenario": "s030_baselab", "actor": "accesspoint_000"}},
    {"hint_id": "LAB_2", "accesspoint_actor": {"scenario": "s030_baselab", "actor": "accesspoint_001"}},
    {"hint_id": "AQUA_1", "accesspoint_actor": {"scenario": "s040_aqua", "actor": "accesspoint_000"}},
    {"hint_id": "AQUA_2", "accesspoint_actor": {"scenario": "s040_aqua", "actor": "accesspoint_001"}},
    {"hint_id": "FOREST_1", "accesspoint_actor": {"scenario": "s050_forest", "actor": "accesspoint_000"}},
    {"hint_id": "SANC_1", "accesspoint_actor": {"scenario": "s070_basesanc", "actor": "accesspoint_000"}},
    {"hint_id": "SHIP_1", "accesspoint_actor": {"scenario": "s080_shipyard", "actor": "accesspoint_000"}},
]

# Prefer these majors for region hints (order = priority).
INTERESTING_ITEMS = (
    "Morph Ball",
    "Bomb",
    "Cross Bomb",
    "Progressive Bombs",
    "Power Bomb",
    "Speed Booster",
    "Spider Magnet",
    "Screw Attack",
    "Spin Boost",
    "Space Jump",
    "Progressive Spin",
    "Varia Suit",
    "Gravity Suit",
    "Progressive Suit",
    "Wide Beam",
    "Plasma Beam",
    "Wave Beam",
    "Progressive Beam",
    "Charge Beam",
    "Diffusion Beam",
    "Progressive Charge Beam",
    "Grapple Beam",
    "Super Missile",
    "Ice Missile",
    "Progressive Missiles",
    "Storm Missile",
    "Phantom Cloak",
    "Flash Shift Upgrade",
    "Flash Shift",
    "Pulse Radar",
)

JOKE_HINTS = (
    "{c4}1, 2, 3, 4! Of randomization I want more!{c0}",
    "{c4}Adam has misplaced the briefing notes. Try another station.{c0}",
    "{c4}Nothing to report. The Chozo archives are being reorganized.{c0}",
)

Placement = Tuple  # region, area, node, item, item_player, is_ours


def _display_item(name: str) -> str:
    return name.replace("_", " ")


def _article(item: str) -> str:
    first = item[:1].lower()
    return "An" if first in "aeiou" else "A"


def format_region_hint(item_name: str, region: str) -> str:
    display = _display_item(item_name)
    art = _article(display)
    return f"{art} {{c1}}{display}{{c0}} can be found in {{c5}}{region}{{c0}}."


def _interesting_rank(item: str) -> int:
    try:
        return INTERESTING_ITEMS.index(item)
    except ValueError:
        return 999


def pick_hint_candidates(
    placements: Sequence[Placement],
    *,
    our_player: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """
    Return up to N (item_name, region) pairs for Adam hints.
    Prefers our player's majors when present; otherwise any Dread major on the map.
    """
    scored: List[Tuple[int, str, str]] = []
    seen_items = set()
    for region, area, node, item, item_player, is_ours in placements:
        # Hint where the item sits (location region), for items that matter to us
        # or are Dread majors for this world.
        if our_player and item_player != our_player and not is_ours:
            # Still hint foreign majors that landed in our world? Prefer ours.
            pass
        rank = _interesting_rank(item)
        if rank >= 999:
            continue
        key = item
        if key in seen_items:
            continue
        seen_items.add(key)
        # Prefer local ownership slightly
        if not is_ours:
            rank += 100
        scored.append((rank, item, region))

    scored.sort(key=lambda t: t[0])
    return [(item, region) for _, item, region in scored]


def build_adam_hints(
    placements: Sequence[Placement],
    *,
    our_player: Optional[str] = None,
) -> List[dict]:
    """Build the patcher `hints` array for all 11 Adam terminals."""
    candidates = pick_hint_candidates(placements, our_player=our_player)
    hints: List[dict] = []
    for i, terminal in enumerate(ADAM_HINT_TERMINALS):
        if i < len(candidates):
            item, region = candidates[i]
            text = format_region_hint(item, region)
        else:
            text = JOKE_HINTS[i % len(JOKE_HINTS)]
        hints.append(
            {
                "accesspoint_actor": dict(terminal["accesspoint_actor"]),
                "hint_id": terminal["hint_id"],
                "text": text,
            }
        )
    return hints

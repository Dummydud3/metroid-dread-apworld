"""Tracker-only story gates that must not be RDV-auto-collected."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Optional, Set, Tuple

# Use the exact event item names from Events.py.
QUIET_ROBE_EVENT = "Event - Quiet Robe"
ELUN_RELEASE_X_EVENT = "Event - Elun - Release X Parasites"

# Send short event keys in GAME_STATE boss or story fields.
QUIET_ROBE_BOSS_KEY = "quiet_robe"
ELUN_RELEASE_X_STORY_KEY = "elun_release_x"

# Save flags using the same pattern as AP_BossBeaten.
ELUN_RELEASE_X_BB = "AP_StoryEvent_elun_release_x"


@dataclass(frozen=True)
class TrackerGateEvent:
    """One story/map gate withheld from tracker auto-collect."""

    key: str
    event_item: str
    # Reuse an All Bosses detection key when possible.
    boss_key: Optional[str] = None
    # Read the GAME_PROGRESS flag from any scenario when available.
    progress_prop: Optional[str] = None
    # Have Lua save the flag once the event is confirmed.
    blackboard_prop: Optional[str] = None
    # Explain why this event affects the map tracker.
    reason: str = ""


# Confirm these events from the game, not inventory reachability alone.
TRACKER_GATE_EVENTS: Tuple[TrackerGateEvent, ...] = (
    TrackerGateEvent(
        key=QUIET_ROBE_BOSS_KEY,
        event_item=QUIET_ROBE_EVENT,
        boss_key=QUIET_ROBE_BOSS_KEY,
        progress_prop="PROFESSOR_MET",
        reason="Unlocks Upper Burenia Hub (blue gate) and downstream Ferenia/Burenia routes.",
    ),
    TrackerGateEvent(
        key=ELUN_RELEASE_X_STORY_KEY,
        event_item=ELUN_RELEASE_X_EVENT,
        progress_prop="X_RELEASE_TRUE",
        blackboard_prop=ELUN_RELEASE_X_BB,
        reason="X parasites / post-Elun world state; gates Z-57 tunnel and many Artaria/Cataris X checks.",
    ),
)

TRACKER_EXCLUDE_AUTO_EVENTS: FrozenSet[str] = frozenset(
    g.event_item for g in TRACKER_GATE_EVENTS
)


def story_progress_checks() -> Tuple[TrackerGateEvent, ...]:
    """Gates that need a dedicated Lua GAME_PROGRESS / scenario probe."""
    return tuple(
        g for g in TRACKER_GATE_EVENTS if g.blackboard_prop and g.progress_prop
    )


def confirmed_event_items(
    *,
    beaten_boss_keys: Optional[Iterable[str]] = None,
    story_keys: Optional[Iterable[str]] = None,
    seed_default_x_released: bool = False,
) -> Set[str]:
    """AP event item names the tracker may treat as collected."""
    bosses = set(beaten_boss_keys or ())
    stories = set(story_keys or ())
    out: Set[str] = set()
    for gate in TRACKER_GATE_EVENTS:
        if gate.boss_key and gate.boss_key in bosses:
            out.add(gate.event_item)
            continue
        if gate.key in stories:
            out.add(gate.event_item)
            continue
        if seed_default_x_released and gate.event_item == ELUN_RELEASE_X_EVENT:
            out.add(gate.event_item)
    return out


def apply_confirmed_events_to_counts(
    counts: Dict[str, int],
    confirmed: Iterable[str],
) -> Dict[str, int]:
    """Return a copy of counts with confirmed event items forced to ≥1."""
    out = dict(counts)
    for name in confirmed:
        out[name] = max(int(out.get(name, 0) or 0), 1)
    return out


# Add other useful events once their detection is reliable.
RECOMMENDED_FUTURE_GATES: Tuple[Tuple[str, str], ...] = (
    (
        "Event - Ghavoran - Ferenia Transport Grapple Box",
        "Opens Ghavoran↔Ferenia transport path; easy to show early if auto-collected from Grapple reachability.",
    ),
    (
        "Event - Cataris - First Thermal Device",
        "Lava-level / heat routing in Cataris; major map section feel if flipped before the device is used.",
    ),
    (
        "Event - Cataris - Final Thermal Device",
        "End of Cataris thermal chain; same class of surprise as Quiet Robe for post-coolant checks.",
    ),
    (
        "Event - Artaria - Thermal Device",
        "Artaria heat gate; less severe than Quiet Robe but still a distant unlock from a local interact.",
    ),
    (
        "Event - Artaria - Chain Reaction End",
        "Opens post-chain Artaria routes; auto-collect can paint a large chunk once the device room opens.",
    ),
    (
        "Major boss events (Corpius/Kraid/…)",
        "Already tracked via spawn/pickup probes for the Bosses pane; map in-logic still auto-collects "
        "them today. Only withhold if players want post-boss rooms gated until the kill is confirmed.",
    ),
)

"""
All Bosses goal — canonical combat/story boss list for Metroid Bread.

Exact list (verified against Events.py / Locations.py / RDV logic DB):

Arena / major bosses
  1. Corpius              — event ``Event - Corpius``
  2. Kraid                — event ``Event - Kraid``
  3. Drogyga              — event ``Event - Drogyga``
  4. Escue                — event ``Event - Escue``
  5. Golzuna              — event ``Event - Golzuna``
  6. Z-57                 — no kill event; win via checking
                            ``Cataris - Above Z-57 Fight - Pickup (Z-57)``
  7. Raven Beak           — victory item ``Raven Beak Defeated`` /
                            client ``Init.bBeatenSinceLastReboot`` (final)

Story / additional bosses (user requested every RDV boss fight)
  8. Quiet Robe           — ``Event - Quiet Robe``
  9. Elun Chozo Soldier   — ``Event - Elun - Chozo Soldier Fight``
 10. Chozo-X              — ``Event - Ghavoran - Chozo-X``
 11. Hanubia Gold Chozo   — ``Event - Hanubia - Gold Chozo Fight``
 12. Hanubia Red Chozo    — ``Event - Hanubia - Red Chozo Fight``
 13. Burenia Twin Robots  — ``Event - Burenia - Twin Robot Fight``
 14. Ferenia Twin Robots  — ``Event - Ferenia - Twin Robot Fight``
 15. Ghavoran Gold Robot  — ``Event - Ghavoran - Gold Robot Fight``

Client beaten detection (Hub tracker / All Bosses gate), in priority order:
  - Raven Beak: ``Init.bBeatenSinceLastReboot`` / finished_game
  - Pickup-backed: AP location checked (``check_location`` / special index)
  - Spawn-group probe: scenario ``SPAWNGROUP.iNumDeaths`` → ``AP_BossBeaten_<key>``
  - Progress prop: ``GAME_PROGRESS`` boolean (Quiet Robe ``PROFESSOR_MET``)
  - Fallback: same-region event unlock inference only (never shared-arena /
    cross-region; that previously marked Burenia Twin Robots when Ghavoran
    Gold Robot died)

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

NodeId = Tuple[str, str, str]

# GameGoal.option_all_bosses
GOAL_ALL_BOSSES = 2

Z57_LOCATION_NAME = "Cataris - Above Z-57 Fight - Pickup (Z-57)"
Z57_NODE: NodeId = ("Cataris", "Above Z-57 Fight", "Pickup (Z-57)")
RAVEN_BEAK_KEY = "raven_beak"
RAVEN_BEAK_ITEM = "Raven Beak Defeated"
RAVEN_BEAK_NODE: NodeId = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")


@dataclass(frozen=True)
class BossDef:
    """One required boss for All Bosses (generation + tracker + client)."""

    key: str
    display_name: str
    # Locked event item from Events.py (None for Z-57 / Raven Beak).
    event_item: Optional[str]
    # RDV node that marks the kill / fight resolution (or Z-57 pickup / RB boss).
    node: NodeId
    # Optional AP pickup location used as a client "beaten" signal.
    check_location: Optional[str] = None
    # Live-game SPAWNGROUP probe (scenario actor; only readable in that scenario).
    spawn_scenario: Optional[str] = None
    spawn_group: Optional[str] = None
    # Vanilla scripts use ``iNumDeaths > N``; we store the threshold as ``>= min_deaths``.
    min_deaths: int = 1
    # Optional GAME_PROGRESS blackboard boolean (readable from any scenario).
    progress_prop: Optional[str] = None


# Order is stable for tracker UI and tests.
ALL_BOSSES: Tuple[BossDef, ...] = (
    BossDef(
        "corpius",
        "Corpius",
        "Event - Corpius",
        ("Artaria", "Corpius Arena", "Event - Corpius"),
        "Artaria - Corpius Arena - Pickup (Phantom Cloak)",
    ),
    BossDef(
        "kraid",
        "Kraid",
        "Event - Kraid",
        ("Cataris", "Kraid Arena", "Event - Kraid"),
        "Cataris - Kraid Arena - Pickup (Kraid)",
    ),
    BossDef(
        "drogyga",
        "Drogyga",
        "Event - Drogyga",
        ("Burenia", "Drogyga Arena", "Event - Drogyga"),
        "Burenia - Drogyga Arena - Pickup (Drogyga)",
    ),
    BossDef(
        "escue",
        "Escue",
        "Event - Escue",
        ("Ferenia", "Escue Arena", "Event - Escue"),
        "Ferenia - Escue Arena - Pickup (Storm Missile)",
    ),
    BossDef(
        "golzuna",
        "Golzuna",
        "Event - Golzuna",
        ("Ghavoran", "Golzuna Arena", "Event - Golzuna"),
        "Ghavoran - Golzuna Arena - Pickup (Cross Bomb)",
    ),
    BossDef(
        "z57",
        "Z-57",
        None,
        Z57_NODE,
        Z57_LOCATION_NAME,
    ),
    BossDef(
        "quiet_robe",
        "Quiet Robe",
        "Event - Quiet Robe",
        ("Ferenia", "Quiet Robe Room", "Event - Quiet Robe"),
        progress_prop="PROFESSOR_MET",
    ),
    BossDef(
        "elun_chozo_soldier",
        "Elun Chozo Soldier",
        "Event - Elun - Chozo Soldier Fight",
        ("Elun", "Chozo Soldier Arena", "Event - Chozo Soldier Fight"),
        spawn_scenario="s060_quarantine",
        spawn_group="SG_ChozoWarriorX",
        min_deaths=2,
    ),
    BossDef(
        "chozo_x",
        "Chozo-X",
        "Event - Ghavoran - Chozo-X",
        ("Ghavoran", "Chozo Warrior Arena", "Event - Chozo-X"),
        spawn_scenario="s050_forest",
        spawn_group="SG_ChozoWarriorX",
        min_deaths=1,
    ),
    BossDef(
        "hanubia_gold_chozo",
        "Hanubia Gold Chozo",
        "Event - Hanubia - Gold Chozo Fight",
        ("Hanubia", "Gold Chozo Warrior Arena", "Event - Gold Chozo Fight"),
        spawn_scenario="s080_shipyard",
        spawn_group="SG_CWX",
        min_deaths=2,
    ),
    BossDef(
        "hanubia_red_chozo",
        "Hanubia Red Chozo",
        "Event - Hanubia - Red Chozo Fight",
        ("Hanubia", "Orange EMMI Introduction", "Event - Red Chozo Fight"),
        "Hanubia - Orange EMMI Introduction - Pickup (Power Bomb)",
    ),
    BossDef(
        "burenia_twin_robots",
        "Burenia Twin Robots",
        "Event - Burenia - Twin Robot Fight",
        ("Burenia", "Gravity Suit Tower", "Event - Twin Robot Fight"),
        spawn_scenario="s040_aqua",
        spawn_group="SG_2RCW_000",
        min_deaths=2,
    ),
    BossDef(
        "ferenia_twin_robots",
        "Ferenia Twin Robots",
        "Event - Ferenia - Twin Robot Fight",
        ("Ferenia", "Twin Robot Arena", "Event - Twin Robot Fight"),
        "Ferenia - Twin Robot Arena - Pickup (Power Bomb Tank)",
        spawn_scenario="s070_basesanc",
        spawn_group="SG_2ChozoRobots",
        min_deaths=2,
    ),
    BossDef(
        "ghavoran_gold_robot",
        "Ghavoran Gold Robot",
        "Event - Ghavoran - Gold Robot Fight",
        ("Ghavoran", "Robot Fight Arena", "Event - Gold Robot Fight"),
        spawn_scenario="s050_forest",
        spawn_group="SG_ChozoRobotSoldier",
        min_deaths=1,
    ),
    BossDef(
        RAVEN_BEAK_KEY,
        "Raven Beak",
        RAVEN_BEAK_ITEM,
        RAVEN_BEAK_NODE,
    ),
)


def boss_spawn_checks() -> Tuple[BossDef, ...]:
    """Bosses that expose a scenario SPAWNGROUP death counter."""
    return tuple(b for b in ALL_BOSSES if b.spawn_group and b.spawn_scenario)


def boss_progress_prop_checks() -> Tuple[BossDef, ...]:
    """Bosses marked via GAME_PROGRESS blackboard booleans."""
    return tuple(b for b in ALL_BOSSES if b.progress_prop)


def boss_blackboard_prop(key: str) -> str:
    """Persistent player-blackboard flag written when a spawn/progress probe fires."""
    return f"AP_BossBeaten_{key}"


def boss_event_items() -> Tuple[str, ...]:
    """Event / victory items required for All Bosses (excludes Z-57)."""
    return tuple(b.event_item for b in ALL_BOSSES if b.event_item)


def boss_nodes_for_access() -> Tuple[NodeId, ...]:
    """Non-RB boss nodes that must be in logic before Raven Beak opens."""
    return tuple(b.node for b in required_bosses_excluding_raven())


def required_bosses_excluding_raven() -> Tuple[BossDef, ...]:
    return tuple(b for b in ALL_BOSSES if b.key != RAVEN_BEAK_KEY)


def check_location_ids() -> Dict[str, int]:
    """Boss key → AP location id for pickup-backed bosses."""
    from .Locations import location_table

    out: Dict[str, int] = {}
    for boss in ALL_BOSSES:
        if not boss.check_location:
            continue
        data = location_table.get(boss.check_location)
        if data is not None and data.id is not None:
            out[boss.key] = int(data.id)
    return out


def state_has_all_bosses(state, player: int) -> bool:
    """
    Generation completion helper: Raven Beak defeated and every All-Bosses
    node reachable under current inventory.

    Boss event items are ``ItemClassification.filler`` and are never recorded in
    ``CollectionState.prog_items`` (``World.collect`` skips them). RDV logic
    auto-grants those events when their nodes open (``collect_events=True``),
    so node reachability is the correct generation proxy — not ``state.has``.
    Z-57 has no event item; its pickup node is included in
    ``boss_nodes_for_access``.
    """
    if not state.has(RAVEN_BEAK_ITEM, player):
        return False
    world = state.multiworld.worlds[player]
    return inventory_reaches_all_boss_nodes(world, state)


def inventory_reaches_all_boss_nodes(world, state) -> bool:
    """True when every All-Bosses node is reachable with the current inventory."""
    logic = world.logic
    reachable = logic.get_reachable_nodes(logic.inventory_from_state(state))
    return all(node in reachable for node in boss_nodes_for_access())


def missing_bosses_at_state(world, state) -> List[str]:
    """Display names of bosses whose nodes are still locked."""
    logic = world.logic
    reachable = logic.get_reachable_nodes(logic.inventory_from_state(state))
    return [b.display_name for b in ALL_BOSSES if b.node not in reachable]


def tracker_boss_rows(
    *,
    in_logic_keys: Set[str],
    beaten_keys: Set[str],
) -> List[dict]:
    """Payload rows for the Hub tracker Bosses pane."""
    rows = []
    for boss in ALL_BOSSES:
        rows.append(
            {
                "key": boss.key,
                "name": boss.display_name,
                "in_logic": boss.key in in_logic_keys,
                "beaten": boss.key in beaten_keys,
            }
        )
    return rows

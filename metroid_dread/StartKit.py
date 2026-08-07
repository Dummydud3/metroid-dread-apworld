"""Minimum starting kit needed to make a rolled starting location fillable.

Randovania flags ~35 nodes as valid_starting_location, but most of them are save
rooms tucked behind a Morph tunnel or a bomb block: with a completely empty
inventory there is no pickup in logic at all. Archipelago's assumed fill walks
the item pool backwards and needs a reachable, empty location for every step, so
an empty sphere 0 makes the fill mathematically impossible and generation dies
with "No more spots to place N items".

Randovania solves this by handing out starting items with a random start. We do
the same: grant the smallest set of items that reopens the start, precollect
them instead of shuffling them into the pool, and mirror them into the
open-dread-rando `starting_items` block so the game agrees with the logic.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

from .dread_logic import PROGRESSIVE_EXPAND

# Sphere-0 pickups to aim for. This is a floor that makes the fill work, not a
# difficulty knob, and every point costs the player a major item out of the
# pool — but two is measurably too tight. The fill still dead-ends placing the
# last progression item maybe one seed in twenty when the start has only two
# checks, so three it is.
MIN_START_LOCATIONS = 3

# Never hand out more than this, even if the start stays cramped.
MAX_START_KIT = 5

# A kit item is just the pool item consumed; progressives may repeat, and the
# stage the player ends up with follows from how many copies the kit holds.
KitItem = str

# Logical item -> open-dread-rando starting_items grants.
ODR_STARTING_ITEMS: Dict[str, Dict[str, int]] = {
    "Morph Ball": {"ITEM_MORPH_BALL": 1},
    "Spider Magnet": {"ITEM_MAGNET_GLOVE": 1},
    "Grapple Beam": {"ITEM_WEAPON_GRAPPLE_BEAM": 1},
    "Speed Booster": {"ITEM_SPEED_BOOSTER": 1},
    "Phantom Cloak": {"ITEM_OPTIC_CAMOUFLAGE": 1},
    "Screw Attack": {"ITEM_SCREW_ATTACK": 1},
    "Storm Missile": {"ITEM_MULTILOCKON": 1},
    "Pulse Radar": {"ITEM_SONAR": 1},
    "Power Bomb": {"ITEM_WEAPON_POWER_BOMB": 1, "ITEM_WEAPON_POWER_BOMB_MAX": 2},
    "Bomb": {"ITEM_WEAPON_BOMB": 1},
    "Cross Bomb": {"ITEM_WEAPON_LINE_BOMB": 1},
    "Wide Beam": {"ITEM_WEAPON_WIDE_BEAM": 1},
    "Plasma Beam": {"ITEM_WEAPON_PLASMA_BEAM": 1},
    "Wave Beam": {"ITEM_WEAPON_WAVE_BEAM": 1},
    "Charge Beam": {"ITEM_WEAPON_CHARGE_BEAM": 1},
    "Diffusion Beam": {"ITEM_WEAPON_DIFFUSION_BEAM": 1},
    "Super Missile": {"ITEM_WEAPON_SUPER_MISSILE": 1},
    "Ice Missile": {"ITEM_WEAPON_ICE_MISSILE": 1},
    "Varia Suit": {"ITEM_VARIA_SUIT": 1},
    "Gravity Suit": {"ITEM_GRAVITY_SUIT": 1},
    "Spin Boost": {"ITEM_DOUBLE_JUMP": 1},
    "Space Jump": {"ITEM_SPACE_JUMP": 1},
    # Ghost Aura is normally unlocked by the first upgrade's script hook, which
    # does not run for pre-granted items, so grant it alongside the chain.
    "Flash Shift Upgrade": {"ITEM_GHOST_AURA": 1, "ITEM_UPGRADE_FLASH_SHIFT_CHAIN": 1},
}

_SINGLE_CANDIDATES = (
    "Morph Ball",
    "Spider Magnet",
    "Grapple Beam",
    "Speed Booster",
    "Phantom Cloak",
    "Screw Attack",
    "Power Bomb",
    "Storm Missile",
    "Flash Shift Upgrade",
)

# Progressive pool item -> the option that turns the group on.
_PROGRESSIVE_OPTIONS = (
    ("Progressive Beam", "progressive_beams"),
    ("Progressive Charge Beam", "progressive_charge"),
    ("Progressive Missiles", "progressive_missiles"),
    ("Progressive Bombs", "progressive_bombs"),
    ("Progressive Suit", "progressive_suit"),
    ("Progressive Spin", "progressive_spin"),
)


def candidate_items(options) -> List[KitItem]:
    """Pool items that exist for these options, repeated per progressive stage.

    Second stages matter: Burenia's south save room is underwater and only
    opens up for Gravity Suit, which is the *second* Progressive Suit.
    """
    candidates: List[KitItem] = list(_SINGLE_CANDIDATES)
    if not options.start_with_pulse_radar:
        candidates.append("Pulse Radar")
    for pool_item, option_name in _PROGRESSIVE_OPTIONS:
        stages = PROGRESSIVE_EXPAND[pool_item]
        if getattr(options, option_name):
            candidates.extend([pool_item] * len(stages))
        else:
            candidates.extend(stages)
    return candidates


def kit_counts(kit: Iterable[KitItem]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for pool_item in kit:
        counts[pool_item] = counts.get(pool_item, 0) + 1
    return counts


def logical_names(kit: Iterable[KitItem]) -> List[str]:
    """What the player actually ends up holding, expanding progressive stacks."""
    names: List[str] = []
    for pool_item, count in kit_counts(kit).items():
        stages = PROGRESSIVE_EXPAND.get(pool_item)
        if stages:
            names.extend(stages[:count])
        else:
            names.extend([pool_item] * count)
    return names


def odr_starting_items(kit: Iterable[KitItem]) -> Dict[str, int]:
    grants: Dict[str, int] = {}
    for name in logical_names(kit):
        for item_id, qty in ODR_STARTING_ITEMS.get(name, {}).items():
            grants[item_id] = max(grants.get(item_id, 0), int(qty))
    return grants


def start_checks(world, counts: Dict[str, int]) -> int:
    """Active locations in logic from the current start with `counts` in hand."""
    logic = world.logic
    active = set(world.active_location_names())
    nodes = logic.get_reachable_nodes(logic.inventory_from_counts(counts))
    return sum(
        1 for name, node in logic.pickup_nodes.items()
        if node in nodes and name in active
    )


def build_start_kit(
    world,
    min_locations: int = MIN_START_LOCATIONS,
    base_kit: Sequence[KitItem] = (),
) -> List[KitItem]:
    """Greedily pick the fewest items that give the start `min_locations` checks.

    `base_kit` is kept and extended, so a kit rolled against the vanilla graph
    can be reused after door / transport rando instead of starting over.
    """
    logic = world.logic
    active = set(world.active_location_names())

    def score(counts: Dict[str, int]) -> Tuple[int, int]:
        """(checks in logic, nodes in logic).

        Node count is the tie-breaker: plenty of starts are behind a two-item
        gate where the first item reaches no new pickup but does open up rooms,
        and without that gradient the greedy search has nothing to climb.
        """
        nodes = logic.get_reachable_nodes(logic.inventory_from_counts(counts))
        checks = sum(
            1 for name, node in logic.pickup_nodes.items()
            if node in nodes and name in active
        )
        return checks, len(nodes)

    kit: List[KitItem] = list(base_kit)
    counts = kit_counts(kit)
    current = score(counts)
    if current[0] >= min_locations:
        return kit

    pool = candidate_items(world.options)
    for pool_item in kit:
        if pool_item in pool:
            pool.remove(pool_item)
    # Deterministic per seed, but stops every cramped start from opening with
    # the exact same item.
    world.random.shuffle(pool)

    def with_items(step: Sequence[KitItem]) -> Dict[str, int]:
        trial = dict(counts)
        for pool_item in step:
            trial[pool_item] = trial.get(pool_item, 0) + 1
        return trial

    def best_step(budget: int) -> List[KitItem]:
        """Best single item, or best pair when no single item changes anything.

        Some starts sit behind a two-item AND gate — Dairon's west save room
        only opens to a Morph Ball Launcher, which wants Morph Ball *and* Bomb —
        and a purely one-at-a-time search sees a flat landscape and gives up.
        """
        best: List[KitItem] = []
        best_score = current
        for pool_item in pool:
            found = score(with_items((pool_item,)))
            if found > best_score:
                best, best_score = [pool_item], found
        if best or budget < 2:
            return best
        for i, first in enumerate(pool):
            for second in pool[i + 1:]:
                found = score(with_items((first, second)))
                if found > best_score:
                    best, best_score = [first, second], found
        return best

    while len(kit) < MAX_START_KIT and pool:
        step = best_step(MAX_START_KIT - len(kit))
        if not step:
            break
        for pool_item in step:
            pool.remove(pool_item)
            counts[pool_item] = counts.get(pool_item, 0) + 1
            kit.append(pool_item)
        current = score(counts)
        if current[0] >= min_locations:
            break

    return kit

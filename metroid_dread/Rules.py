"""
Metroid Dread access rules — live Randovania graph evaluation.
"""

from worlds.generic.Rules import set_rule
from BaseClasses import MultiWorld, CollectionState

from .Options import MetroidDreadOptions
from .Events import event_locations
from .Locations import location_table
from . import victory_clearance


def set_rules(multiworld: MultiWorld, player: int, options: MetroidDreadOptions):
    world = multiworld.worlds[player]
    logic = world.logic

    def make_rule(location_name: str):
        def rule(state: CollectionState, name=location_name) -> bool:
            return logic.can_reach_location_name(name, state)
        return rule

    for loc_name in location_table:
        try:
            set_rule(multiworld.get_location(loc_name, player), make_rule(loc_name))
        except KeyError:
            pass

    for ev in event_locations:
        try:
            set_rule(multiworld.get_location(ev.name, player), make_rule(ev.name))
        except KeyError:
            pass

    # Victory implies >=90%: Raven Beak is only in logic once enough clearable
    # pickups (full-inventory reachability from this start) are also in logic.
    # One BFS per evaluation keeps fill / sphere sweeps affordable.
    clearable_nodes = victory_clearance.clearable_pickup_nodes(world)
    world.clearable_pickup_count = len(clearable_nodes)

    def raven_beak_rule(state: CollectionState) -> bool:
        return victory_clearance.inventory_reaches_victory_and_clearance(
            world, state, clearable_nodes
        )

    try:
        set_rule(multiworld.get_location("Raven Beak", player), raven_beak_rule)
    except KeyError:
        pass

    # Goal is always defeat Raven Beak (DNA is a gate, not a separate win).
    multiworld.completion_condition[player] = lambda state: (
        state.has("Raven Beak Defeated", player)
    )

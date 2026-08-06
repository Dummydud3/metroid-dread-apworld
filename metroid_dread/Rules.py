"""
Metroid Dread access rules — live Randovania graph evaluation.
"""

from worlds.generic.Rules import set_rule
from BaseClasses import MultiWorld, CollectionState

from .Options import MetroidDreadOptions
from .Events import event_locations
from .Locations import location_table


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

    try:
        set_rule(multiworld.get_location("Raven Beak", player), make_rule("Raven Beak"))
    except KeyError:
        pass

    # Goal is always defeat Raven Beak (DNA is a gate, not a separate win).
    multiworld.completion_condition[player] = lambda state: (
        state.has("Raven Beak Defeated", player)
    )

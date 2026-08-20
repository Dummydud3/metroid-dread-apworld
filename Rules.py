"""
Metroid Bread access rules — live Randovania graph evaluation.
"""

from worlds.generic.Rules import set_rule
from BaseClasses import MultiWorld, CollectionState

from .Options import MetroidBreadOptions, GameGoal
from .Events import event_locations
from .Locations import location_table
from . import bosses
from . import victory_clearance


def set_rules(multiworld: MultiWorld, player: int, options: MetroidBreadOptions):
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

    # Raven Beak is only in logic once enough clearable pickups (full-inventory
    # reachability from this start) are also in logic. Defeat Raven Beak uses
    # >=90%; Game Goal 100% requires every clearable check. All Bosses keeps
    # 90% and also requires every non-RB boss node in logic.
    clearable_nodes = victory_clearance.clearable_pickup_nodes(world)
    world.clearable_pickup_count = len(clearable_nodes)
    all_bosses = options.game_goal == GameGoal.option_all_bosses

    def raven_beak_rule(state: CollectionState) -> bool:
        if not victory_clearance.inventory_reaches_victory_and_clearance(
            world, state, clearable_nodes
        ):
            return False
        if all_bosses and not bosses.inventory_reaches_all_boss_nodes(world, state):
            return False
        return True

    try:
        set_rule(multiworld.get_location("Raven Beak", player), raven_beak_rule)
    except KeyError:
        pass

    # Win: defeat Raven Beak. For 100%, also require every real check in the
    # active pool (non-clearable checks are stripped for that goal). For All
    # Bosses, require every boss event (+ Z-57 pickup) as well.
    if options.game_goal == GameGoal.option_one_hundred_percent:
        active = set(world.active_location_names())
        check_names = [
            loc.name
            for loc in victory_clearance.real_check_locations(world)
            if loc.name in active
        ]

        def completion(state: CollectionState, names=check_names) -> bool:
            if not state.has("Raven Beak Defeated", player):
                return False
            for name in names:
                try:
                    if not state.can_reach(name, "Location", player):
                        return False
                except KeyError:
                    return False
            return True

        multiworld.completion_condition[player] = completion
    elif options.game_goal == GameGoal.option_all_bosses:
        multiworld.completion_condition[player] = lambda state: (
            bosses.state_has_all_bosses(state, player)
        )
    else:
        multiworld.completion_condition[player] = lambda state: (
            state.has("Raven Beak Defeated", player)
        )

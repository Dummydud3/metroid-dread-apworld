"""Metroid Bread access rules — live Randovania graph evaluation."""



from worlds.generic.Rules import set_rule

from BaseClasses import MultiWorld, CollectionState



from .Options import MetroidBreadOptions, GameGoal

from .Events import event_locations

from .Locations import location_table

from worlds.metroid_bread.logic import bosses

from worlds.metroid_bread.logic import victory_clearance





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



    # Open Raven Beak only after enough checks are reachable.

    # Count checks reachable from this start with a full inventory.

    # Raven Beak needs 90%; 100% needs every reachable check.

    # All Bosses also needs every other boss node reachable.

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



    # Winning normally means defeating Raven Beak.

    # For 100%, also finish every active AP check.

    # For All Bosses, also finish all boss events and the Z-57 pickup.

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


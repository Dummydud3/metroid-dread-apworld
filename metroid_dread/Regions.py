
from BaseClasses import Region, Entrance, MultiWorld, ItemClassification
from .Locations import MetroidDreadLocation, location_table
from .Events import event_locations

def area_region_name(game_region: str, area: str) -> str:
    return f"{game_region}/{area}"

def create_regions(multiworld: MultiWorld, player: int):
    world = multiworld.worlds[player]
    logic = world.logic

    menu = Region("Menu", player, multiworld)
    multiworld.regions.append(menu)

    area_regions = {}
    for game_region, region_data in logic.parser.regions.items():
        for area_name in region_data.get("areas", {}):
            name = area_region_name(game_region, area_name)
            region = Region(name, player, multiworld)
            area_regions[name] = region
            multiworld.regions.append(region)

    for loc_name, loc_data in location_table.items():
        node = logic.pickup_nodes.get(loc_name)
        if node:
            game_region, area, _node = node
            parent_name = area_region_name(game_region, area)
        else:
            parent_name = area_region_name(loc_data.region, loc_data.region)
            candidates = [n for n in area_regions if n.startswith(loc_data.region + "/")]
            parent_name = candidates[0] if candidates else parent_name

        parent = area_regions.get(parent_name)
        if parent is None:
            parent = next(iter(area_regions.values()))
        location = MetroidDreadLocation(player, loc_name, loc_data.id, parent)
        parent.locations.append(location)

    def _event_path_priority(ev) -> int:
        n = ev.node.lower()
        penalty = 0
        for bad in ("ledge warp", "through wall", "through floor", "with ledge"):
            if bad in n:
                penalty += 10
        return penalty

    seen_event_items = set()
    for ev in sorted(event_locations, key=_event_path_priority):
        if ev.event_item in seen_event_items:
            continue
        seen_event_items.add(ev.event_item)
        parent = area_regions.get(ev.region)
        if parent is None:
            continue
        location = MetroidDreadLocation(player, ev.name, None, parent)
        event_item = world.create_item(ev.event_item)
        event_item.classification = ItemClassification.filler
        location.place_locked_item(event_item)
        parent.locations.append(location)

    victory_parent = area_regions.get("Itorash/Raven Beak Arena")
    if victory_parent is not None:
        victory_location = MetroidDreadLocation(player, "Raven Beak", None, victory_parent)
        victory_location.place_locked_item(world.create_item("Raven Beak Defeated"))
        victory_parent.locations.append(victory_location)
        logic.pickup_nodes["Raven Beak"] = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")

    start = logic.starting_node
    start_region_name = area_region_name(start[0], start[1])
    start_region = area_regions.get(start_region_name)
    if start_region is None and area_regions:
        start_region = next(iter(area_regions.values()))

    if start_region is not None:
        entrance = Entrance(player, "Start Game", menu)
        menu.exits.append(entrance)
        entrance.connect(start_region)

    for name, region in area_regions.items():
        if region is start_region:
            continue
        ent = Entrance(player, f"Logic Bridge to {name}", menu)
        menu.exits.append(ent)
        ent.connect(region)

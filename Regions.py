"""
Metroid Dread regions for Archipelago

One AP Region per Randovania area. Pickup and event locations attach to their
area. Intra-Dread reachability is enforced by RDV BFS access rules (see Rules.py),
not by coarse bidirectional mega-region links.
"""

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

    # Create one region per RDV area
    area_regions = {}
    for game_region, region_data in logic.parser.regions.items():
        for area_name in region_data.get("areas", {}):
            name = area_region_name(game_region, area_name)
            region = Region(name, player, multiworld)
            area_regions[name] = region
            multiworld.regions.append(region)

    # Attach pickup locations (stable AP names / IDs)
    for loc_name, loc_data in location_table.items():
        node = logic.pickup_nodes.get(loc_name)
        if node:
            game_region, area, _node = node
            parent_name = area_region_name(game_region, area)
        else:
            # Fallback: LocationData.region is the game region name
            parent_name = area_region_name(loc_data.region, loc_data.region)
            # Prefer any area region under that game region
            candidates = [n for n in area_regions if n.startswith(loc_data.region + "/")]
            parent_name = candidates[0] if candidates else parent_name

        parent = area_regions.get(parent_name)
        if parent is None:
            # Last resort: create orphan under first Artaria area
            parent = next(iter(area_regions.values()))
        location = MetroidDreadLocation(player, loc_name, loc_data.id, parent)
        parent.locations.append(location)

    # Attach locked event locations (one AP location per unique event item).
    # Events are filler classification: reachability is granted inside DreadLogic
    # BFS, so accessibility:items does not require every event node (including
    # trick-only / self-gated alternates).
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

    # Victory: locked event when Boss - Raven Beak node is reachable
    victory_parent = area_regions.get("Itorash/Raven Beak Arena")
    if victory_parent is not None:
        victory_location = MetroidDreadLocation(player, "Raven Beak", None, victory_parent)
        victory_location.place_locked_item(world.create_item("Raven Beak Defeated"))
        victory_parent.locations.append(victory_location)
        # Register alias for logic BFS
        logic.pickup_nodes["Raven Beak"] = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")

    # Menu -> starting area only (no free cross-region graph)
    start = logic.starting_node
    start_region_name = area_region_name(start[0], start[1])
    start_region = area_regions.get(start_region_name)
    if start_region is None and area_regions:
        start_region = next(iter(area_regions.values()))

    if start_region is not None:
        entrance = Entrance(player, "Start Game", menu)
        menu.exits.append(entrance)
        entrance.connect(start_region)

    # Connect every area region to Menu via a unreachable stub? No —
    # AP requires parent_region.can_reach for locations. With only Menu->start,
    # other area regions are never reachable via AP entrances.
    #
    # Fix: connect Menu to ALL area regions with trivial entrances so AP's
    # region sweep can reach every Location object; real gating is on
    # location.access_rule via RDV BFS.
    for name, region in area_regions.items():
        if region is start_region:
            continue
        ent = Entrance(player, f"Logic Bridge to {name}", menu)
        menu.exits.append(ent)
        ent.connect(region)

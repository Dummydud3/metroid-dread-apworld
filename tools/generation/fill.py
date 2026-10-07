"""Custom Fill Algorithm for Metroid Bread"""

from pathlib import Path

import sys

WORLD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORLD))
sys.path.insert(0, str(WORLD.parents[1]))

from typing import Dict, Set, List, Tuple, Optional, FrozenSet
from BaseClasses import MultiWorld, Item, Location, CollectionState
from worlds.metroid_bread.logic.logic_parser import RandovaniaLogicParser
if __package__:
    from .reachability import ReachabilityAnalyzer
else:
    from reachability import ReachabilityAnalyzer

import random


class MetroidBreadFillAlgorithm:
    """Custom fill algorithm that places items in accessibility order."""
    
    def __init__(self, world):
        self.world = world
        self.multiworld = world.multiworld
        self.player = world.player
        
        # Load RDV logic.
        logic_path = WORLD / "logic_database"
        self.parser = RandovaniaLogicParser(logic_path)
        self.parser.load_database()
        self.analyzer = ReachabilityAnalyzer(self.parser)
        
        # Find the starting node.
        starting_nodes = self.parser.get_starting_nodes()
        self.starting_node = starting_nodes[0] if starting_nodes else ("Artaria", "Intro Room", "Start Point")
        
        # Map AP location names to RDV nodes.
        self.location_to_node = {}
        for region, area, node, pickup_idx in self.parser.get_pickup_locations():
            location_name = f"{region} - {area} - {node}"
            self.location_to_node[location_name] = (region, area, node)
    
    def get_all_ap_item_names(self) -> List[str]:
        """Get all Archipelago progression item names"""
        items = []
        if "items" in self.parser.resources:
            for item_short_name in self.parser.resources["items"].keys():
                ap_name = self.parser._map_resource_to_ap_item("items", item_short_name)
                if ap_name and ap_name not in ["Missile Tank", "Missile+ Tank", "Energy Tank", 
                                                 "Energy Part", "Power Bomb Tank"]:
                    items.append(ap_name)
        return items
    
    def get_reachable_unfilled_locations(
        self, 
        filled_locations: Set[str],
        collected_items: Set[str]
    ) -> Set[str]:
        """Get all unfilled locations that are currently reachable with collected items."""
        # Find nodes reachable in RDV logic.
        reachable_nodes = self.analyzer.get_reachable_pickups(
            self.starting_node,
            frozenset(collected_items)
        )
        
        # Convert reached nodes to AP location names.
        reachable_locations = set()
        for location_name, node_tuple in self.location_to_node.items():
            if node_tuple in reachable_nodes and location_name not in filled_locations:
                reachable_locations.add(location_name)
        
        return reachable_locations
    
    def custom_fill(
        self, 
        all_locations: List[Location],
        progression_items: List[Item],
        filler_items: List[Item]
    ) -> bool:
        """Custom fill algorithm using forward-fill / assumed fill approach."""
        print(f"\n{'='*60}")
        print("METROID DREAD CUSTOM FILL ALGORITHM")
        print(f"{'='*60}")
        print(f"Locations: {len(all_locations)}")
        print(f"Progression items: {len(progression_items)}")
        print(f"Filler items: {len(filler_items)}")
        
        # Track placed items and items collected so far.
        filled_locations = set()
        collected_items = set()
        
        # Build a lookup for locations.
        location_lookup = {loc.name: loc for loc in all_locations}
        
        # Place progression items using the assumed inventory.
        print("\n--- Phase 1: Placing Progression Items ---")
        
        remaining_progression = list(progression_items)
        random.shuffle(remaining_progression)
        
        placement_count = 0
        sphere = 0
        items_placed_this_sphere = 0
        sphere_locations = []
        
        while remaining_progression:
            # Find every currently reachable location.
            reachable = self.get_reachable_unfilled_locations(filled_locations, collected_items)
            
            if not reachable:
                # Relax the search if no location is reachable.
                print(f"\n[WARNING] No reachable locations with current logic!")
                print(f"  {len(remaining_progression)} items left: {[i.name for i in remaining_progression[:5]]}")
                print(f"  Collected so far: {len(collected_items)} items")
                print(f"  Trying fallback: place at any unfilled location")
                
                # As a fallback, use any empty location.
                all_unfilled = [loc.name for loc in all_locations if not loc.item]
                if not all_unfilled:
                    print(f"[ERROR] No unfilled locations at all!")
                    return False
                reachable = set(all_unfilled)
            
            # Start the next step after filling the previous reachable set.
            if items_placed_this_sphere == 0:
                if sphere > 0:
                    print(f"  Placed {len(sphere_locations)} items")
                    if sphere_locations:
                        for loc in sphere_locations[:3]:
                            print(f"    - {loc}")
                        if len(sphere_locations) > 3:
                            print(f"    ... and {len(sphere_locations) - 3} more")
                
                print(f"\nSphere {sphere}: {len(reachable)} reachable locations, {len(remaining_progression)} items to place")
                items_placed_this_sphere = 0
                sphere_locations = []
            
            # Place one item at a random reachable location.
            location_name = random.choice(list(reachable))
            location = location_lookup.get(location_name)
            
            if not location or location.item:
                # Skip locations that already have an item.
                filled_locations.add(location_name)
                continue
            
            # Choose the next progression item.
            item = remaining_progression.pop(0)
            
            # Place this item.
            location.item = item
            item.location = location
            
            # Remember the placement.
            filled_locations.add(location_name)
            collected_items.add(item.name)
            
            items_placed_this_sphere += 1
            sphere_locations.append(location_name)
            placement_count += 1
            
            # Check whether to advance the playthrough step.
            is_key_item = any(key in item.name for key in [
                "Morph Ball", "Bomb", "Spider", "Beam", "Missile", 
                "Grapple", "Phantom", "Flash", "Suit", "Space", "Spin", "Screw"
            ])
            
            if is_key_item or items_placed_this_sphere >= 3:
                sphere += 1
                items_placed_this_sphere = 0
            
            # Stop if the loop exceeds its limit.
            if sphere > 30:
                print(f"\n[ERROR] Exceeded maximum spheres (30). Likely infinite loop.")
                return False
        
        # Print the final playthrough-step counts.
        if sphere_locations:
            print(f"  Placed {len(sphere_locations)} items")
            for loc in sphere_locations[:3]:
                print(f"    - {loc}")
        
        print(f"\n[OK] All {placement_count} progression items placed in {sphere} spheres!")
        
        # Fill the remaining checks with filler items.
        print("\n--- Phase 2: Placing Filler Items ---")
        
        unfilled_locations = [loc for loc in all_locations if not loc.item]
        print(f"Filling {len(unfilled_locations)} remaining locations with {len(filler_items)} filler items")
        
        if len(unfilled_locations) != len(filler_items):
            print(f"[WARNING] Mismatch: {len(unfilled_locations)} locations but {len(filler_items)} filler items")
            # Place as much remaining filler as possible.
            if len(unfilled_locations) < len(filler_items):
                print(f"[ERROR] More filler items than locations!")
                return False
        
        random.shuffle(unfilled_locations)
        for location, item in zip(unfilled_locations, filler_items):
            location.item = item
            item.location = location
        
        print(f"[OK] All filler items placed!")
        
        print(f"\n{'='*60}")
        print("FILL COMPLETE")
        print(f"{'='*60}\n")
        
        return True


def fill_restrictive(multiworld: MultiWorld, base_state: CollectionState, locations: List[Location],
                     items: List[Item]) -> None:
    """Archipelago's fill hook for restrictive fill."""
    # Use the custom placement method for Metroid Bread.
    if not locations:
        return
    
    # Find the world instance.
    player = locations[0].player
    world = multiworld.worlds[player]
    
    # Check whether this is the Metroid Bread world.
    if not hasattr(world, 'game') or world.game != "Metroid Bread":
        # Leave other worlds unchanged.
        return
    
    # Split progression items from filler.
    progression_items = []
    filler_items = []
    
    for item in items:
        if item.advancement:
            progression_items.append(item)
        else:
            filler_items.append(item)
    
    print(f"\n[Metroid Bread] Using custom fill algorithm")
    print(f"  Progression: {len(progression_items)}")
    print(f"  Filler: {len(filler_items)}")
    
    # Create and run the custom placement helper.
    fill_algorithm = MetroidBreadFillAlgorithm(world)
    success = fill_algorithm.custom_fill(locations, progression_items, filler_items)
    
    if not success:
        raise Exception("Metroid Bread custom fill failed!")

"""Smart Rule Generator for Metroid Bread"""



from pathlib import Path

import sys

WORLD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORLD))
sys.path.insert(0, str(WORLD.parents[1]))


from typing import Dict, Set, List, Tuple, FrozenSet

from worlds.metroid_bread.logic.logic_parser import RandovaniaLogicParser

if __package__:
    from .reachability import ReachabilityAnalyzer
else:
    from reachability import ReachabilityAnalyzer

from collections import defaultdict





class SmartRuleGenerator:

    """Generates Archipelago rules using sphere-based analysis"""

    

    def __init__(self, parser: RandovaniaLogicParser, analyzer: ReachabilityAnalyzer):

        self.parser = parser

        self.analyzer = analyzer

        

    def get_all_item_names(self) -> List[str]:

        """Get all Archipelago item names"""

        items = set()

        if "items" in self.parser.resources:

            for item_short_name in self.parser.resources["items"].keys():

                ap_name = self.parser._map_resource_to_ap_item("items", item_short_name)

                if ap_name:

                    items.add(ap_name)

        return sorted(list(items))

    

    def perform_sphere_analysis(self, starting_node: Tuple[str, str, str]) -> Dict[Tuple[str, str, str], int]:

        """Perform forward-fill sphere analysis to determine minimum sphere for each location"""

        all_items = self.get_all_item_names()

        all_locations = [(r, a, n) for r, a, n, _ in self.parser.get_pickup_locations()]

        

        # Check that Charge Tutorial is listed.

        charge_tutorial_locs_debug = [loc for loc in all_locations if "Charge Tutorial" in loc[1]]

        if charge_tutorial_locs_debug:

            print(f"DEBUG: Found {len(charge_tutorial_locs_debug)} Charge Tutorial locations in all_locations")

            print(f"  Example: {charge_tutorial_locs_debug[0]}")

        else:

            print("DEBUG: NO Charge Tutorial locations found in all_locations!")

            # Print a few sample locations.

            print(f"  Total locations: {len(all_locations)}")

            if all_locations:

                print(f"  Example location: {all_locations[0]}")

        

        print("Performing sphere analysis...")

        

        # Track the first step each location becomes reachable.

        location_spheres = {}

        collected_items = set()

        remaining_locations = set(all_locations)

        

        sphere = 0

        max_spheres = 50  # Limit the loop so it cannot run forever.

        

        while remaining_locations and sphere < max_spheres:

            print(f"\n  Sphere {sphere}:")

            

            # Find locations reachable with the current items.

            reachable_now = self.analyzer.get_reachable_pickups(

                starting_node, 

                frozenset(collected_items)

            )

            

            # Record new locations for this step.

            newly_accessible = []

            for loc in remaining_locations:

                if loc in reachable_now:

                    location_spheres[loc] = sphere

                    newly_accessible.append(loc)

            

            if not newly_accessible:

                # Stop if no more locations become reachable.

                print(f"    No new locations accessible. {len(remaining_locations)} locations unreachable.")

                # Use step 999 for unreachable locations.

                for loc in remaining_locations:

                    location_spheres[loc] = 999

                break

            

            print(f"    Found {len(newly_accessible)} accessible locations")

            

            # Print details for the starting checks.

            if sphere == 0 and newly_accessible:

                print("    Sphere 0 locations (first 5):")

                for i, loc in enumerate(sorted(newly_accessible)[:5]):

                    print(f"      - {loc[0]} / {loc[1]} / {loc[2]}")

                

                # Check Charge Tutorial specifically.

                charge_tutorial_in_remaining = [loc for loc in remaining_locations if loc[1] == "Charge Tutorial"]

                if charge_tutorial_in_remaining:

                    print(f"\n    DEBUG: Charge Tutorial check:")

                    for loc_tuple in charge_tutorial_in_remaining:

                        in_sphere_0 = loc_tuple in newly_accessible

                        print(f"      - {loc_tuple[0]} / {loc_tuple[1]} / {loc_tuple[2]}: {'IN Sphere 0' if in_sphere_0 else 'NOT in Sphere 0'}")

            

            # Test progression items at each newly reached location.

            # Find items that open more locations.

            # Add only items that improve reachability.

            

            items_that_unlock_new = set()

            current_reachable = reachable_now

            

            for item_name in all_items:

                # Skip ammo and energy filler.

                if item_name in ["Missile Tank", "Missile+ Tank", "Energy Tank", 

                                "Energy Part", "Power Bomb Tank"]:

                    continue

                

                # Skip items already owned.

                if item_name in collected_items:

                    continue

                

                # Check whether this item opens new locations.

                test_items = collected_items | {item_name}

                test_reachable = self.analyzer.get_reachable_pickups(

                    starting_node,

                    frozenset(test_items)

                )

                

                if len(test_reachable) > len(current_reachable):

                    # This item opens more checks.

                    items_that_unlock_new.add(item_name)

                    print(f"      + {item_name} unlocks {len(test_reachable) - len(current_reachable)} new locations")

            

            # Add items that open new areas.

            collected_items.update(items_that_unlock_new)

            

            if not items_that_unlock_new:

                print(f"      No progression items found that unlock new areas")

            

            # Remove locations already recorded.

            remaining_locations -= set(newly_accessible)

            sphere += 1

        

        print(f"\nSphere analysis complete: {len(location_spheres)} locations categorized")

        

        # Count locations in each playthrough step.

        sphere_counts = defaultdict(int)

        for sphere_num in location_spheres.values():

            sphere_counts[sphere_num] += 1

        

        for s in sorted(sphere_counts.keys()):

            print(f"  Sphere {s}: {sphere_counts[s]} locations")

        

        return location_spheres

    

    def find_sufficient_items_for_location(

        self, 

        location: Tuple[str, str, str], 

        starting_node: Tuple[str, str, str],

        sphere: int

    ) -> Set[frozenset]:

        """Find ALL possible item combinations that make this location accessible."""

        # Check empty-inventory access first.

        sphere_0_reachable = self.analyzer.get_reachable_pickups(

            starting_node,

            frozenset()

        )

        if location in sphere_0_reachable:

            # Do not add requirements to starting checks.

            location_name = f"{location[0]} - {location[1]} - {location[2]}"

            print(f"  [SKIP] {location_name} is reachable from start (no rule needed)")

            return {frozenset()}  # The location is open from the start.

        

        # Also skip checks marked as starting locations.

        if sphere == 0:

            return {frozenset()}

        

        all_items = self.get_all_item_names()

        possible_paths = []  # Store item combinations that work.

        

        # Treat each working single item as a separate path.

        for item in all_items:

            # Skip ammo and energy filler.

            if item in ["Missile Tank", "Missile+ Tank", "Energy Tank", 

                       "Energy Part", "Power Bomb Tank"]:

                continue

            

            reachable = self.analyzer.get_reachable_pickups(

                starting_node,

                frozenset([item])

            )

            if location in reachable:

                possible_paths.append(frozenset([item]))

        

        # Try common pairs only if no single item works.

        if not possible_paths:

            common_pairs = [

                ["Morph Ball", "Charge Beam"],

                ["Morph Ball", "Wide Beam"],

                ["Morph Ball", "Bomb"],

                ["Charge Beam", "Wide Beam"],

                ["Grapple Beam", "Space Jump"],

                ["Varia Suit", "Gravity Suit"],

                ["Morph Ball", "Varia Suit"],

                ["Charge Beam", "Varia Suit"],

            ]

            

            for pair in common_pairs:

                valid_pair = [item for item in pair if item in all_items]

                if len(valid_pair) == 2:

                    reachable = self.analyzer.get_reachable_pickups(

                        starting_node,

                        frozenset(valid_pair)

                    )

                    if location in reachable:

                        possible_paths.append(frozenset(valid_pair))

        

        # Return working paths, or an empty set if none were found.

        return set(possible_paths) if possible_paths else set()

    

    def generate_location_rule(self, required_items: Set[str]) -> str:

        """Generate Python lambda for location rule"""

        if not required_items:

            return None  # No rule is needed here.

        

        if len(required_items) == 1:

            item = list(required_items)[0]

            return f"lambda state: state.has('{item}', player)"

        

        if len(required_items) == 2:

            items = sorted(list(required_items))

            return f"lambda state: (state.has('{items[0]}', player) and state.has('{items[1]}', player))"

        

        # Skip requirements of three or more items for now.

        return None

    

    def generate_entrance_rule(self, paths: Set[frozenset]) -> str:

        """Generate Python lambda for entrance rule with OR logic"""

        if not paths or frozenset() in paths:

            return None  # The location is unrestricted or reachable from the start.

        

        # Remove paths with no items.

        non_empty_paths = [p for p in paths if p]

        

        if not non_empty_paths:

            return None

        

        if len(non_empty_paths) == 1:

            # Require every item in a single path.

            items = sorted(list(non_empty_paths[0]))

            if len(items) == 1:

                return f"lambda state: state.has('{items[0]}', player)"

            else:

                conditions = [f"state.has('{item}', player)" for item in items]

                return f"lambda state: ({' and '.join(conditions)})"

        

        # Allow any one of the working paths.

        path_conditions = []

        for path in sorted(non_empty_paths, key=lambda p: (len(p), sorted(list(p)))):

            items = sorted(list(path))

            if len(items) == 1:

                path_conditions.append(f"state.has('{items[0]}', player)")

            else:

                conditions = [f"state.has('{item}', player)" for item in items]

                path_conditions.append(f"({' and '.join(conditions)})")

        

        return f"lambda state: ({' or '.join(path_conditions)})"

    

    def analyze_region_connections(self, starting_node: Tuple[str, str, str]) -> Dict[Tuple[str, str], Set[str]]:

        """Analyze inter-region dock connections to determine what items are needed"""

        print("\n" + "="*60)

        print("ANALYZING REGION CONNECTIVITY")

        print("="*60)

        

        # Read links between regions.

        dock_connections = self.parser.get_dock_connections()

        

        # Group links by source and target region.

        region_connections = defaultdict(set)  # Map each region pair to its door nodes.

        

        for source_region, source_area, source_node, target_region, target_area, target_node, weakness in dock_connections:

            if source_region != target_region:

                # This link crosses regions.

                # Store the source door where its item requirement applies.

                region_connections[(source_region, target_region)].add((source_region, source_area, source_node))

        

        print(f"\nFound {len(region_connections)} inter-region connections:")

        for (source, target), docks in region_connections.items():

            print(f"  {source} -> {target}: {len(docks)} docks")

        

        # Find required items for each region link.

        region_requirements = {}

        

        print("\nAnalyzing requirements for each connection...")

        all_items = self.get_all_item_names()

        

    def analyze_region_connections(self, starting_node: Tuple[str, str, str]) -> Dict[Tuple[str, str], Set[frozenset]]:

        """Analyze inter-region dock connections using ACTUAL Randovania requirements."""

        print("\n" + "="*60)

        print("ANALYZING REGION CONNECTIVITY (Using Randovania Logic)")

        print("="*60)

        

        # Read the actual door nodes for each region link.

        dock_connections = self.parser.get_dock_connections()

        

        # Group source doors and requirements by source and target region.

        region_connections = defaultdict(lambda: defaultdict(list))

        

        for source_region, source_area, source_node, target_region, target_area, target_node, door_requirement in dock_connections:

            if source_region != target_region:

                # Store the door node and its parsed requirement.

                region_connections[source_region][target_region].append(

                    ((source_region, source_area, source_node), door_requirement)

                )

        

        print(f"\nAnalyzing requirements for each connection...")

        region_requirements = {}

        

        for source_region in sorted(region_connections.keys()):

            print(f"\nFrom {source_region}:")

            

            for target_region in sorted(region_connections[source_region].keys()):

                docks_and_reqs = region_connections[source_region][target_region]

                print(f"  -> {target_region}: {len(docks_and_reqs)} dock(s)")

                

                # Check both reaching the door and opening it.

                dock_paths = []

                

                for (dock_loc, door_requirement) in docks_and_reqs:

                    # The parser already provides a requirement dictionary.

                    # Check whether the door can be reached from the start.

                    reachable_sphere_0 = self.analyzer.get_reachable_nodes(starting_node, frozenset())

                    

                    if dock_loc not in reachable_sphere_0:

                        # Find items that let the player reach this door.

                        # Test single items only for now.

                        all_items = self.get_all_item_names()

                        dock_reachable_with = None

                        

                        for item in all_items:

                            if item in ["Missile Tank", "Missile+ Tank", "Energy Tank", "Energy Part", "Power Bomb Tank"]:

                                continue

                            

                            reachable = self.analyzer.get_reachable_nodes(starting_node, frozenset([item]))

                            if dock_loc in reachable:

                                dock_reachable_with = frozenset([item])

                                break

                        

                        if not dock_reachable_with:

                            # Skip doors that need more than one item to reach.

                            continue

                    else:

                        dock_reachable_with = frozenset()  # The door is reachable from the start.

                    

                    # Find items needed to open the door.

                    door_items = self._extract_items_from_requirement(door_requirement)

                    

                    # Combine the items needed to reach and open it.

                    total_required = dock_reachable_with | door_items

                    dock_paths.append(total_required)

                

                if not dock_paths:

                    print(f"     No accessible paths found (skipping)")

                    continue

                

                # Remove repeated requirements.

                unique_paths = set(dock_paths)

                

                if frozenset() in unique_paths:

                    print(f"     At least one path accessible from start (no restrictions)")

                    region_requirements[(source_region, target_region)] = {frozenset()}

                else:

                    region_requirements[(source_region, target_region)] = unique_paths

                    # Print a short result summary.

                    if len(unique_paths) == 1:

                        path = list(unique_paths)[0]

                        items_str = " AND ".join(sorted(path)) if path else "nothing"

                        print(f"     Requires: {items_str}")

                    else:

                        paths_strs = []

                        for path in sorted(unique_paths, key=lambda p: (len(p), sorted(p))):

                            paths_strs.append(" AND ".join(sorted(path)) if path else "nothing")

                        print(f"     Requires: {' OR '.join(paths_strs)}")

        

        return region_requirements

    

    def _extract_items_from_requirement(self, requirement: Dict) -> frozenset:

        """Extract the set of items needed to satisfy a requirement."""

        if not requirement:

            return frozenset()

        

        req_type = requirement.get("type")

        

        if req_type == "trivial":

            return frozenset()

        

        if req_type == "impossible":

            return frozenset(["IMPOSSIBLE"])  # Mark requirements that can never pass.

        

        if req_type == "resource":

            data = requirement.get("data", {})

            resource_type = data.get("type")

            resource_name = data.get("name")

            ap_item = self.parser._map_resource_to_ap_item(resource_type, resource_name)

            

            if ap_item:

                return frozenset([ap_item])

            return frozenset()  # No mapped item is needed for this resource.

        

        if req_type == "template":

            template_name = requirement.get("data")

            if template_name in self.parser.templates:

                template_req = self.parser.templates[template_name].get("requirement")

                return self._extract_items_from_requirement(template_req)

            return frozenset()

        

        if req_type == "and":

            # Require all items from all parts.

            items = set()

            for sub_req in requirement.get("data", {}).get("items", []):

                items.update(self._extract_items_from_requirement(sub_req))

            return frozenset(items)

        

        if req_type == "or":

            # Choose the smallest working alternative.

            sub_reqs = requirement.get("data", {}).get("items", [])

            if not sub_reqs:

                return frozenset()

            

            # Find all working paths.

            all_paths = [self._extract_items_from_requirement(sub_req) for sub_req in sub_reqs]

            # Choose the path needing the fewest items.

            return min(all_paths, key=len)

        

        return frozenset()

    

        # Keep both directions of a two-way link.

        # Each direction can have different requirements.

        # For example, check both Artaria-to-Cataris and Cataris-to-Artaria.

        print("\nFinalizing requirements...")

        final_requirements = {}

        

        for (source, target), paths in sorted(region_requirements.items()):

            if frozenset() in paths:

                # No items are required.

                final_requirements[(source, target)] = {frozenset()}

            else:

                final_requirements[(source, target)] = paths

        

        return final_requirements

    

    def generate_rules_file(self, output_path: str, starting_node: Tuple[str, str, str]):

        """Generate complete Rules.py with sphere-based analysis"""

        print("="*60)

        print("SMART RULE GENERATION")

        print("="*60)

        

        # Find the playthrough steps.

        location_spheres = self.perform_sphere_analysis(starting_node)

        

        # Check links between regions.

        region_requirements = self.analyze_region_connections(starting_node)

        

        # Find each location's requirements.

        all_locations = self.parser.get_pickup_locations()

        location_rules = {}

        

        print("\nAnalyzing location requirements...")

        rules_generated = 0

        rules_skipped = 0

        

        for i, (region, area, node, pickup_idx) in enumerate(all_locations):

            if (i + 1) % 20 == 0:

                print(f"  Processed {i + 1}/{len(all_locations)} locations...")

            

            location = (region, area, node)

            location_name = f"{region} - {area} - {node}"

            sphere = location_spheres.get(location, 999)

            

            # Write rules only for the starting checks and the next step.

            # Let AP handle later checks with more complex requirements.

            if sphere > 1:

                rules_skipped += 1

                continue

            

            # Skip early checks that hold only ammo or energy filler.

            # They do not open progression and may have complex paths.

            if sphere == 1 and ("Energy Tank" in node or "Missile Tank" in node or 

                               "Energy Part" in node or "Power Bomb Tank" in node or

                               "Missile+ Tank" in node):

                rules_skipped += 1

                continue

            

            # Also skip locations whose requirements depend on themselves.

            # Checking every alternative path is too expensive here.

            problematic_locations = [

                "Artaria - Varia Suit Room - Pickup (Varia Suit)",

                "Artaria - Central Unit Access - Pickup (Spider Magnet)",

                "Cataris - Central Unit Access - Pickup (Morph Ball)",

            ]

            if location_name in problematic_locations:

                rules_skipped += 1

                continue

            

            # Find enough items to reach this location.

            required_item_paths = self.find_sufficient_items_for_location(

                location, starting_node, sphere

            )

            

            # Use the entrance-rule helper to allow alternative paths.

            rule_lambda = self.generate_entrance_rule(required_item_paths)

            

            if rule_lambda:

                location_rules[location_name] = rule_lambda

                rules_generated += 1

            else:

                rules_skipped += 1

        

        print(f"\n[OK] Analysis complete:")

        print(f"  Rules generated: {rules_generated}")

        print(f"  Rules skipped: {rules_skipped}")

        

        # Write Rules.py.

        print(f"\nGenerating {output_path}...")

        with open(output_path, 'w', encoding='utf-8') as f:

            self._write_rules_file(f, location_rules, region_requirements)

        

        print(f"[OK] Rules file generated!")

    

    def _write_rules_file(self, f, location_rules: Dict[str, str], region_requirements: Dict[Tuple[str, str], Set[frozenset]]):

        """Write the actual Rules.py content"""

        f.write('"""\n')

        f.write('Metroid Bread Logic Rules for Archipelago\n')

        f.write('AUTO-GENERATED from Randovania logic using sphere analysis\n')

        f.write('Generated by: generate_rules_smart.py\n')

        f.write('"""\n\n')

        

        f.write('from worlds.generic.Rules import set_rule\n')

        f.write('from BaseClasses import MultiWorld\n')

        f.write('from .Options import MetroidBreadOptions\n\n')

        

        f.write('def set_rules(multiworld: MultiWorld, player: int, options: MetroidBreadOptions):\n')

        f.write('    """Set location and region access rules based on sphere analysis"""\n\n')

        

        # Write rules for links between regions.

        f.write('    # ===== REGION CONNECTIVITY RULES =====\n')

        f.write('    # Define which items are needed to travel between regions\n')

        f.write('    # Multiple paths use OR logic (any path works)\n\n')

        

        region_rules_written = 0

        for (source_region, target_region), paths in sorted(region_requirements.items()):

            entrance_name = f"{source_region} to {target_region}"

            rule_lambda = self.generate_entrance_rule(paths)

            

            if rule_lambda:

                f.write(f'    # {source_region} -> {target_region}\n')

                f.write(f'    try:\n')

                f.write(f'        set_rule(\n')

                f.write(f'            multiworld.get_entrance("{entrance_name}", player),\n')

                f.write(f'            {rule_lambda}\n')

                f.write(f'        )\n')

                f.write(f'    except KeyError:\n')

                f.write(f'        pass  # Entrance may not exist in all seeds\n\n')

                region_rules_written += 1

        

        if region_rules_written == 0:

            f.write('    # No region restrictions found - all regions accessible from start\n\n')

        

        # Write rules for each location.

        f.write('    # ===== LOCATION ACCESS RULES =====\n')

        f.write('    # Generated using forward-fill sphere analysis\n')

        f.write('    # Only includes rules for locations with simple, clear requirements\n\n')

        

        for location_name, rule_lambda in sorted(location_rules.items()):

            f.write(f'    set_rule(\n')

            f.write(f'        multiworld.get_location("{location_name}", player),\n')

            f.write(f'        {rule_lambda}\n')

            f.write(f'    )\n')

        

        f.write('\n    # ===== VICTORY CONDITION =====\n\n')

        f.write('    if options.game_goal.value == 0:  # Defeat Raven Beak\n')

        f.write('        multiworld.completion_condition[player] = lambda state: (\n')

        f.write('            state.has("Raven Beak Defeated", player)\n')

        f.write('        )\n')

        f.write('    elif options.game_goal.value == 1:  # DNA Hunt\n')

        f.write('        dna_required = int(options.dna_count.value * options.dna_required.value / 100)\n')

        f.write('        multiworld.completion_condition[player] = lambda state: (\n')

        f.write('            state.has("Metroid DNA", player, dna_required)\n')

        f.write('        )\n')





def main():

    """Generate smart rules from Randovania logic"""

    logic_path = WORLD / "logic_database"

    output_path = WORLD / "Rules.py"

    

    print("="*60)

    print("SMART METROID DREAD RULE GENERATOR")

    print("="*60)

    print("\nStep 1: Loading Randovania logic database...")

    parser = RandovaniaLogicParser(logic_path)

    parser.load_database()

    

    print("\nStep 2: Creating reachability analyzer...")

    analyzer = ReachabilityAnalyzer(parser)

    

    print("\nStep 3: Finding starting location...")

    starting_nodes = parser.get_starting_nodes()

    if not starting_nodes:

        starting_node = ("Artaria", "Intro Room", "Start Point")

        print(f"  Using default: {starting_node}")

    else:

        starting_node = starting_nodes[0]

        print(f"  Found: {starting_node}")

    

    print("\nStep 4: Creating smart rule generator...")

    generator = SmartRuleGenerator(parser, analyzer)

    

    print("\nStep 5: Generating rules with sphere analysis...")

    generator.generate_rules_file(output_path, starting_node)

    

    print(f"\n{'='*60}")

    print(f"SUCCESS! Rules generated at:")

    print(f"  {output_path}")

    print(f"{'='*60}\n")





if __name__ == "__main__":

    main()


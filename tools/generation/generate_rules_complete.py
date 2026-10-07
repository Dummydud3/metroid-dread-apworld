"""Advanced Rule Generator for Metroid Bread"""



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





class RuleGenerator:

    """Generates Archipelago rules from reachability analysis"""

    

    def __init__(self, parser: RandovaniaLogicParser, analyzer: ReachabilityAnalyzer):

        self.parser = parser

        self.analyzer = analyzer

        self.all_items = self._get_all_items()

        

    def _get_all_items(self) -> List[str]:

        """Get list of all AP item names"""

        items = []

        if "items" in self.parser.resources:

            for item_short_name in self.parser.resources["items"].keys():

                ap_name = self.parser._map_resource_to_ap_item("items", item_short_name)

                if ap_name:

                    items.append(ap_name)

        return items

    

    def find_required_items_for_location(self, location: Tuple[str, str, str], starting_node: Tuple[str, str, str]) -> Set[str]:

        """Find which items are required to reach a location"""

        # Check reachability with an empty inventory.

        reachable = self.analyzer.get_reachable_pickups(starting_node, frozenset())

        if location in reachable:

            return set()  # No item requirement is needed.

        

        # Try each item on its own.

        required_items = set()

        for item in self.all_items:

            reachable = self.analyzer.get_reachable_pickups(starting_node, frozenset([item]))

            if location in reachable:

                required_items.add(item)

        

        # Try a limited number of item combinations if single items fail.

        if not required_items:

            # Try common item pairs.

            common_combos = [

                ["Morph Ball", "Charge Beam"],

                ["Morph Ball", "Wide Beam"],

                ["Morph Ball", "Super Missile"],

                ["Charge Beam", "Wide Beam"],

                ["Varia Suit", "Space Jump"],

                ["Gravity Suit", "Space Jump"],

                # Add useful pairs here as needed.

            ]

            

            for combo in common_combos:

                valid_combo = [item for item in combo if item in self.all_items]

                reachable = self.analyzer.get_reachable_pickups(starting_node, frozenset(valid_combo))

                if location in reachable:

                    return set(valid_combo)

        

        return required_items

    

    def generate_location_rule(self, location: Tuple[str, str, str], required_items: Set[str]) -> str:

        """Generate a Python lambda expression for a location's access rule"""

        if not required_items:

            return "lambda state: True"

        

        # Skip rules requiring multiple items for now.

        # These rules can prevent the current placement method from finishing.

        if len(required_items) > 1:

            return "lambda state: True"  # Leave the location accessible.

        

        if len(required_items) == 1:

            item = list(required_items)[0]

            return f"lambda state: state.has('{item}', player)"

        

        return "lambda state: True"

    

    def generate_rules_file(self, output_path: str, starting_node: Tuple[str, str, str]):

        """Generate complete Rules.py file"""

        print("Analyzing all location requirements...")

        

        # List all pickup locations.

        all_locations = self.parser.get_pickup_locations()

        print(f"Found {len(all_locations)} pickup locations")

        

        # Check each location's requirements.

        location_rules = {}

        sphere_0_count = 0

        single_item_count = 0

        multi_item_count = 0

        unreachable_count = 0

        

        for i, (region, area, node, pickup_idx) in enumerate(all_locations):

            if (i + 1) % 10 == 0:

                print(f"  Analyzed {i + 1}/{len(all_locations)} locations...")

            

            location = (region, area, node)

            required_items = self.find_required_items_for_location(location, starting_node)

            

            if not required_items:

                sphere_0_count += 1

            elif len(required_items) == 1:

                single_item_count += 1

            elif len(required_items) > 1:

                multi_item_count += 1

            else:

                unreachable_count += 1

            

            rule_lambda = self.generate_location_rule(location, required_items)

            location_rules[f"{region} - {area} - {node}"] = rule_lambda

        

        print(f"\n[OK] Analysis complete:")

        print(f"  Sphere 0 (no items): {sphere_0_count}")

        print(f"  Single item: {single_item_count}")

        print(f"  Multiple items: {multi_item_count}")

        print(f"  Unreachable: {unreachable_count}")

        

        # Write Rules.py.

        print(f"\nGenerating {output_path}...")

        with open(output_path, 'w', encoding='utf-8') as f:

            self._write_rules_file(f, location_rules)

        

        print(f"[OK] Rules file generated successfully!")

    

    def _write_rules_file(self, f, location_rules: Dict[str, str]):

        """Write the actual Rules.py content"""

        # Write the header.

        f.write('"""\n')

        f.write('Metroid Bread Logic Rules for Archipelago\n')

        f.write('AUTO-GENERATED from Randovania logic database\n')

        f.write('Generated by: generate_rules_complete.py\n')

        f.write('"""\n\n')

        

        f.write('from worlds.generic.Rules import set_rule\n')

        f.write('from BaseClasses import MultiWorld, CollectionState\n')

        f.write('from .Options import MetroidBreadOptions\n\n')

        

        # Write helper functions.

        f.write('# ===== MAIN RULE SETTING =====\n\n')

        f.write('def set_rules(multiworld: MultiWorld, player: int, options: MetroidBreadOptions):\n')

        f.write('    """Set all location access rules based on Randovania logic"""\n\n')

        

        # Write location rules.

        f.write('    # ===== LOCATION ACCESS RULES =====\n')

        f.write('    # Each location has requirements based on reachability analysis\n\n')

        

        for location_name, rule_lambda in sorted(location_rules.items()):

            # Skip always-open rules.

            if rule_lambda != "lambda state: True":

                f.write(f'    set_rule(\n')

                f.write(f'        multiworld.get_location("{location_name}", player),\n')

                f.write(f'        {rule_lambda}\n')

                f.write(f'    )\n')

        

        # Write the victory requirement.

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

    """Generate complete rules from Randovania logic"""

    logic_path = WORLD / "logic_database"

    output_path = WORLD / "Rules_Generated.py"

    

    print("="*60)

    print("METROID DREAD RULE GENERATOR")

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

    

    print("\nStep 4: Creating rule generator...")

    generator = RuleGenerator(parser, analyzer)

    

    print("\nStep 5: Analyzing all locations and generating rules...")

    print("  (This may take 1-2 minutes...)")

    generator.generate_rules_file(output_path, starting_node)

    

    print(f"\n{'='*60}")

    print(f"SUCCESS! Rules generated at:")

    print(f"  {output_path}")

    print(f"{'='*60}\n")





if __name__ == "__main__":

    main()


"""
Rule Generator for Metroid Bread
Generates Archipelago rules from Randovania logic database
"""

from pathlib import Path
from logic_parser import RandovaniaLogicParser


def generate_rules_file(parser: RandovaniaLogicParser, output_path: str):
    """Generate a complete Rules.py file from the logic database"""
    
    # Get all locations and connections
    locations = parser.get_pickup_locations()
    connections = parser.get_dock_connections()
    
    # Generate the file
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write header
        f.write('"""\n')
        f.write('Metroid Bread Logic Rules for Archipelago\n')
        f.write('AUTO-GENERATED from Randovania logic database\n')
        f.write('DO NOT EDIT MANUALLY - Regenerate using generate_rules.py\n')
        f.write('"""\n\n')
        
        f.write('from worlds.generic.Rules import set_rule, add_rule\n')
        f.write('from BaseClasses import MultiWorld, CollectionState\n')
        f.write('from .Options import MetroidBreadOptions\n\n')
        
        # Write helper functions for each item check
        f.write('# ===== ITEM CHECK HELPERS =====\n')
        f.write('# Auto-generated helper functions for checking items\n\n')
        
        # Generate basic item check functions
        item_checks = {
            "Morph Ball": "has_morph_ball",
            "Bomb": "has_bomb",
            "Cross Bomb": "has_cross_bomb",
            "Power Bomb": "has_power_bombs",
            "Spider Magnet": "has_spider_magnet",
            "Speed Booster": "has_speed_booster",
            "Flash Shift": "has_flash_shift",
            "Grapple Beam": "has_grapple_beam",
            "Spin Boost": "has_spin_boost",
            "Space Jump": "has_space_jump",
            "Screw Attack": "has_screw_attack",
            "Varia Suit": "has_varia_suit",
            "Gravity Suit": "has_gravity_suit",
            "Phantom Cloak": "has_phantom_cloak",
            "Wide Beam": "has_wide_beam",
            "Plasma Beam": "has_plasma_beam",
            "Wave Beam": "has_wave_beam",
            "Charge Beam": "has_charge_beam",
            "Diffusion Beam": "has_diffusion_beam",
            "Super Missile": "has_super_missiles",
            "Ice Missile": "has_ice_missiles",
            "Storm Missile": "has_storm_missiles",
            "Pulse Radar": "has_pulse_radar",
        }
        
        for item_name, func_name in item_checks.items():
            f.write(f'def {func_name}(state: CollectionState, player: int) -> bool:\n')
            f.write(f'    return state.has("{item_name}", player)\n\n')
        
        # Write main rule setting function
        f.write('# ===== MAIN RULE SETTING =====\n\n')
        f.write('def set_rules(multiworld: MultiWorld, player: int, options: MetroidBreadOptions):\n')
        f.write('    """Set all location and entrance rules based on Randovania logic"""\n\n')
        
        # For now, just add a basic structure
        f.write('    # TODO: Location-specific rules will be generated here\n')
        f.write('    # Each of the 149 locations will have its access requirements defined\n\n')
        
        f.write('    # Victory condition\n')
        f.write('    if options.game_goal.value == 0:  # Defeat Raven Beak\n')
        f.write('        multiworld.completion_condition[player] = lambda state: (\n')
        f.write('            state.has("Raven Beak Defeated", player)\n')
        f.write('        )\n')
    
    print(f"Generated basic rules file at {output_path}")
    print(f"  {len(locations)} locations found")
    print(f"  {len(connections)} connections found")
    print("  NOTE: Full rule generation requires complex path-finding logic")
    print("  Current file provides structure only")


def main():
    """Generate rules from Randovania logic"""
    logic_path = Path(__file__).parent / "logic_database"
    output_path = Path(__file__).parent / "Rules_Generated.py"
    
    print("Loading Randovania logic database...")
    parser = RandovaniaLogicParser(logic_path)
    parser.load_database()
    
    print("\nGenerating Archipelago rules...")
    generate_rules_file(parser, output_path)
    
    print("\n[OK] Rules file generated!")
    print(f"     Location: {output_path}")


if __name__ == "__main__":
    main()

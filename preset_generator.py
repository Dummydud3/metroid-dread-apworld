#!/usr/bin/env python3
"""
Generate a minimal game preset for non-Dread games to include in multiworld .rdvgame files.
This allows Randovania to display foreign item names correctly.
"""

def create_minimal_preset(game_name, player_name):
    """
    Create a minimal preset structure for a non-Dread game.
    
    For Archipelago multiworld, we need a preset so Randovania can display
    foreign item names. However, if the game isn't supported by Randovania,
    we use a supported game as a placeholder (the item names still display correctly).
    """
    
    # Map common Archipelago game names to Randovania game identifiers
    # For unsupported games, we use a placeholder Randovania game
    GAME_NAME_MAPPING = {
        # Supported Randovania games
        "Metroid Prime": "prime1",
        "Metroid Prime 2": "prime2", 
        "Metroid Prime 3": "prime3",
        "Super Metroid": "super_metroid",
        "Cave Story": "cave_story",
        "Metroid Dread": "dread",
        "AM2R": "am2r",
        "Metroid Fusion": "fusion",
        "Samus Returns": "samus_returns",
        
        # Unsupported games → use placeholder
        # The actual item names (strings) will still display correctly!
        "Hollow Knight": "prime1",  # Use Prime as placeholder
        "HKPlayer": "prime1",
        "A Link to the Past": "prime1",
        "Zelda": "prime1",
        # Add more as needed - all map to prime1 as safe placeholder
    }
    
    # Get game identifier
    game_id = GAME_NAME_MAPPING.get(game_name)
    
    # If unknown, try to infer from player name
    if not game_id:
        if "HK" in player_name or "Hollow" in player_name:
            game_id = "prime1"  # Placeholder
        elif "Prime" in player_name or "Metroid" in player_name:
            game_id = "prime1"
        else:
            game_id = "prime1"  # Safe default placeholder
    
    # Create minimal preset with required configuration
    # Note: Even though we use prime1 as game ID, the ITEM NAMES are what get displayed,
    # so "Monomon" will still show as "Monomon" in-game!
    
    # Get minimal configuration based on game type
    configuration = get_minimal_configuration(game_id)
    
    preset = {
        "schema_version": 111,  # Use current schema version to avoid migration issues
        "base_preset_uuid": None,
        "name": f"{game_name} Items (Archipelago)",
        "uuid": f"00000000-0000-0000-0000-{hash(player_name) % 1000000000000:012d}",
        "description": f"Placeholder preset for displaying {game_name} item names in Archipelago multiworld",
        "game": game_id,  # Use supported game as placeholder
        "configuration": configuration
    }
    
    return preset


def get_minimal_configuration(game_id):
    """
    Get minimal required configuration for each game type.
    For Prime 1, we use a complete working configuration to avoid schema issues.
    """
    
    if game_id == "prime1":
        # Load complete Prime 1 configuration shipped next to this module.
        # Empty pickups_state is invalid: Randovania fills missing pickups with
        # StandardPickupState(included_ammo=()), but Missile Launcher / Power Bomb
        # require included_ammo length matching pickup.ammo (size 1).
        import os
        import json

        module_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(module_dir, "prime_config_complete.json"),
            # Legacy mistaken path (repo root) — keep as last resort
            os.path.join(module_dir, "..", "..", "prime_config_complete.json"),
        ]
        last_error = None
        for config_path in candidates:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                _ensure_prime_ammo_included(cfg)
                print(f"[INFO] Loaded Prime placeholder config: {config_path}")
                return cfg
            except Exception as e:
                last_error = e
        print(f"[WARNING] Could not load complete Prime config: {last_error}")
        print("[WARNING] Falling back to embedded minimal Prime config")
        return get_minimal_prime_config()
    
    elif game_id == "dread":
        # Metroid Dread configuration
        return {
            "trick_level": {
                "minimal_logic": False,
                "specific_levels": {}
            },
            "starting_location": [
                {
                    "region": "Artaria",
                    "area": "Intro Room",
                    "node": "Start"
                }
            ],
            "available_locations": {
                "randomization_mode": "full",
                "excluded_indices": []
            },
            "standard_pickup_configuration": {
                "pickups_state": {}
            },
            "ammo_pickup_configuration": {
                "pickups_state": {}
            }
        }
    
    else:
        # Generic fallback (shouldn't happen if we always use prime1/dread)
        return {
            "trick_level": {
                "minimal_logic": False,
                "specific_levels": {}
            }
        }


# Randovania prime1 pickups that declare ammo[] — included_ammo must match length.
# See randovania/games/prime1/pickup_database/pickup-database.json
PRIME1_AMMO_PICKUP_DEFAULTS = {
    "Missile Launcher": {
        "num_shuffled_pickups": 1,
        "included_ammo": [5],
    },
    "Power Bomb": {
        "num_shuffled_pickups": 1,
        "included_ammo": [4],
    },
}


def _ensure_prime_ammo_included(cfg):
    """Guarantee Missile Launcher / Power Bomb have correct included_ammo sizes."""
    try:
        pickups = cfg["standard_pickup_configuration"]["pickups_state"]
    except (KeyError, TypeError):
        return
    for name, defaults in PRIME1_AMMO_PICKUP_DEFAULTS.items():
        state = pickups.get(name)
        if not isinstance(state, dict):
            pickups[name] = dict(defaults)
            continue
        ammo = state.get("included_ammo")
        if not isinstance(ammo, list) or len(ammo) != len(defaults["included_ammo"]):
            state["included_ammo"] = list(defaults["included_ammo"])
            if "num_shuffled_pickups" not in state and "num_included_in_starting_pickups" not in state:
                state["num_shuffled_pickups"] = defaults["num_shuffled_pickups"]


def get_minimal_prime_config():
    """Fallback minimal Prime config if complete config can't be loaded."""
    # Must include Missile Launcher / Power Bomb included_ammo (length 1 each).
    # An empty pickups_state causes Randovania to reject the preset with:
    #   Mismatched included_ammo array size. (Missile Launcher)
    return {
        "trick_level": {
            "minimal_logic": False,
            "specific_levels": {}
        },
        "starting_location": [
            {
                "region": "Tallon Overworld",
                "area": "Landing Site",
                "node": "Ship"
            }
        ],
        "available_locations": {
            "randomization_mode": "full",
            "excluded_indices": []
        },
        "standard_pickup_configuration": {
            "pickups_state": {
                "Charge Beam": {"num_shuffled_pickups": 2},
                "Power Beam": {"num_included_in_starting_pickups": 1},
                "Wave Beam": {"num_shuffled_pickups": 1},
                "Ice Beam": {"num_shuffled_pickups": 1},
                "Plasma Beam": {"num_shuffled_pickups": 1},
                "Missile Launcher": {
                    "num_shuffled_pickups": 1,
                    "included_ammo": [5],
                },
                "Grapple Beam": {"num_shuffled_pickups": 1},
                "Combat Visor": {"num_included_in_starting_pickups": 1},
                "Scan Visor": {"num_included_in_starting_pickups": 1},
                "Thermal Visor": {"num_shuffled_pickups": 1},
                "X-Ray Visor": {"num_shuffled_pickups": 1},
                "Space Jump Boots": {"num_shuffled_pickups": 1},
                "Energy Tank": {"num_shuffled_pickups": 14},
                "Morph Ball": {"num_shuffled_pickups": 1},
                "Morph Ball Bomb": {"num_shuffled_pickups": 1},
                "Boost Ball": {"num_shuffled_pickups": 1},
                "Spider Ball": {"num_shuffled_pickups": 1},
                "Power Bomb": {
                    "num_shuffled_pickups": 1,
                    "included_ammo": [4],
                },
                "Power Suit": {"num_included_in_starting_pickups": 1},
                "Varia Suit": {"num_shuffled_pickups": 1},
                "Gravity Suit": {"num_shuffled_pickups": 1},
                "Phazon Suit": {"num_shuffled_pickups": 1},
                "Super Missile": {"num_shuffled_pickups": 1},
                "Wavebuster": {"num_shuffled_pickups": 1},
                "Ice Spreader": {"num_shuffled_pickups": 1},
                "Flamethrower": {"num_shuffled_pickups": 1},
            },
            "default_pickups": {},
            "minimum_random_starting_pickups": 0,
            "maximum_random_starting_pickups": 0
        },
        "ammo_pickup_configuration": {
            "pickups_state": {
                "Missile Expansion": {
                    "ammo_count": [5],
                    "pickup_count": 49,
                    "requires_main_item": False,
                },
                "Power Bomb Expansion": {
                    "ammo_count": [1],
                    "pickup_count": 4,
                    "requires_main_item": False,
                },
                "Energy Refill": {
                    "ammo_count": [20],
                    "pickup_count": 0,
                    "requires_main_item": False,
                },
                "Missile Refill": {
                    "ammo_count": [5],
                    "pickup_count": 0,
                    "requires_main_item": False,
                },
                "Power Bomb Refill": {
                    "ammo_count": [1],
                    "pickup_count": 0,
                    "requires_main_item": False,
                },
            }
        },
        "damage_strictness": 1.5,
        "pickup_model_style": "all-visible",
        "pickup_model_data_source": "etm",
        "logical_resource_action": "randomly",
        "first_progression_must_be_local": False,
        "dock_rando": {
            "mode": "vanilla",
            "types_state": {
                "door": {
                    "can_change_from": [
                        "Ice Door",
                        "Missile Blast Shield (randomprime)",
                        "Normal Door",
                        "Plasma Door",
                        "Wave Door"
                    ],
                    "can_change_to": [
                        "Ice Door",
                        "Missile Blast Shield (randomprime)",
                        "Normal Door",
                        "Permanently Locked",
                        "Plasma Door",
                        "Wave Door"
                    ]
                }
            }
        },
        "single_set_for_pickups_that_solve": True,
        "staggered_multi_pickup_placement": False,
        "check_if_beatable_after_base_patches": False,
        "logical_pickup_placement": False,
        "hints": {
            "enable_random_hints": True,
            "enable_specific_location_hints": True,
            "specific_pickup_hints": {
                "artifacts": "precise",
                "phazon_suit": "hide-area"
            },
            "minimum_available_locations_for_hint_placement": 0,
            "minimum_location_weight_for_hint_placement": 0.0,
            "use_resolver_hints": False
        },
        "teleporters": {
            "mode": "vanilla",
            "excluded_teleporters": [
                {
                    "region": "Frigate Orpheon",
                    "area": "Exterior Docking Hangar",
                    "node": "Teleporter to Tallon Overworld"
                },
                {
                    "region": "Impact Crater",
                    "area": "Crater Entry Point",
                    "node": "Teleporter to Tallon Overworld"
                },
                {
                    "region": "Impact Crater",
                    "area": "Metroid Prime Lair",
                    "node": "Teleporter to Credits"
                },
                {
                    "region": "Tallon Overworld",
                    "area": "Artifact Temple",
                    "node": "Teleporter to Impact Crater"
                }
            ],
            "excluded_targets": [],
            "skip_final_bosses": False,
            "allow_unvisited_room_names": True
        },
        "energy_per_tank": 100,
        "artifact_target": 0,
        "artifact_required": 0,
        "artifact_minimum_progression": 0,
        "pre_place_artifact": False,
        "pre_place_phazon": False,
        "heat_damage": 10.0,
        "warp_to_start": True,
        "damage_reduction": "Additive",
        "allow_underwater_movement_without_gravity": False,
        "small_samus": False,
        "large_samus": False,
        "shuffle_item_pos": False,
        "items_every_room": False,
        "random_boss_sizes": False,
        "no_doors": False,
        "superheated_probability": 0,
        "submerged_probability": 0,
        "room_rando": "None",
        "spring_ball": False,
        "main_plaza_door": True,
        "blue_save_doors": True,
        "backwards_frigate": False,
        "backwards_labs": False,
        "backwards_upper_mines": False,
        "backwards_lower_mines": False,
        "phazon_elite_without_dynamo": True,
        "remove_bars_great_tree_hall": False,
        "legacy_mode": False,
        "qol_cutscenes": "Skippable",
        "ingame_difficulty": "Normal",
        "blast_shield_lockon": False,
        "enemy_attributes": None
    }


# game_modifications.starting_location must be "Region/Area/Node".
# NodeIdentifier.from_string splits on "/" and calls create(region, area, node).
# A bare string like "Default" raises:
#   NodeIdentifier.create() missing 2 required positional arguments: 'area' and 'node'
DEFAULT_STARTING_LOCATIONS = {
    "prime1": "Tallon Overworld/Landing Site/Ship",
    "prime2": "Temple Grounds/Landing Site/Ship",
    "prime3": "Norion/Landing Site/Ship",
    "dread": "Artaria/Intro Room/Start Point",
    "super_metroid": "Crateria/Landing Site/Ship",
    "am2r": "Main Deck/Landing Site/Ship",
    "samus_returns": "Surface/Landing Site/Ship",
    "fusion": "Main Deck/Landing Site/Ship",
    "cave_story": "Starting Point/Start/Start",
}


def _starting_pickups_for_game(game_id):
    """
    Pickups that the placeholder preset puts in starting inventory.
    Must be listed under starting_equipment.pickups so Randovania can
    pull them from the generated pool when decoding game_modifications.
    """
    if game_id != "prime1":
        return []

    try:
        cfg = get_minimal_configuration(game_id)
        pickups_state = cfg.get("standard_pickup_configuration", {}).get("pickups_state", {})
        starting = []
        for name, state in pickups_state.items():
            if not isinstance(state, dict):
                continue
            count = int(state.get("num_included_in_starting_pickups") or 0)
            starting.extend([name] * count)
        if starting:
            return starting
    except Exception:
        pass

    # Fallback matching prime_config_complete.json defaults
    return ["Power Beam", "Combat Visor", "Scan Visor", "Power Suit"]


def create_minimal_game_modification(game_id, player_index):
    """
    Create a minimal game_modifications entry for a non-Dread game.
    
    We include this so Randovania knows the game exists in the multiworld,
    but locations stay empty since we're only patching Dread.
    
    Fields must match schema-40 decode expectations in
    randovania.layout.game_patches_serializer.decode_single.
    """
    starting_location = DEFAULT_STARTING_LOCATIONS.get(
        game_id, "Tallon Overworld/Landing Site/Ship"
    )

    return {
        "game": game_id,
        "starting_location": starting_location,
        "starting_equipment": {
            "pickups": _starting_pickups_for_game(game_id),
        },
        "dock_connections": {},
        "dock_weakness": {},
        "locations": [],  # Empty - no locations for this game in our file
        "hints": {},
        "game_specific": {},
    }


# For reference: games Randovania supports
RANDOVANIA_SUPPORTED_GAMES = {
    "am2r": "AM2R",
    "cave_story": "Cave Story",
    "dread": "Metroid Dread",
    "echoes": "Metroid Prime 2: Echoes",
    "fusion": "Metroid Fusion",
    "hk": "Hollow Knight",  # If supported
    "prime1": "Metroid Prime",
    "prime2": "Metroid Prime 2: Echoes",
    "prime3": "Metroid Prime 3: Corruption",
    "samus_returns": "Metroid: Samus Returns",
    "super_metroid": "Super Metroid",
}

# Game name mapping (same as in create_minimal_preset)
GAME_NAME_MAPPING = {
    # Supported Randovania games
    "Metroid Prime": "prime1",
    "Metroid Prime 2": "prime2", 
    "Metroid Prime 3": "prime3",
    "Super Metroid": "super_metroid",
    "Cave Story": "cave_story",
    "Metroid Dread": "dread",
    "AM2R": "am2r",
    "Metroid Fusion": "fusion",
    "Samus Returns": "samus_returns",
    
    # Unsupported games → use placeholder
    "Hollow Knight": "prime1",
    "HKPlayer": "prime1",
    "A Link to the Past": "prime1",
    "Zelda": "prime1",
}

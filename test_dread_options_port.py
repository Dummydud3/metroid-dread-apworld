"""Tests for door/transport/DNA/cosmetic options wiring."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


class TestDoorRandoConstants(unittest.TestCase):
    def test_basic_change_to_subset(self):
        from worlds.metroid_dread.DoorRando import (
            BASIC_DOOR_TYPES,
            DEFAULT_CHANGE_DOORS_TO,
            WEAKNESS_DOOR_TYPE,
        )
        for name in DEFAULT_CHANGE_DOORS_TO:
            self.assertIn(WEAKNESS_DOOR_TYPE[name], BASIC_DOOR_TYPES)


class TestPatchExtrasMerge(unittest.TestCase):
    def test_apply_door_and_objective(self):
        import ap_to_patcher as ap

        patcher = {
            "door_patches": [],
            "elevators": [],
            "objective": {},
            "starting_items": {"ITEM_FLOOR_SLIDE": 1},
            "cosmetic_patches": {},
            "game_patches": {},
        }
        extras = {
            "door_patches": [
                {"actor": {"scenario": "s010_cave", "actor": "door_a"}, "door_type": "missile"}
            ],
            "elevators": [
                {
                    "teleporter": {"scenario": "s010_cave", "actor": "elev_a"},
                    "destination": {"scenario": "s020_magma", "actor": "plat_b"},
                    "connection_name": "Cataris - Thermal Device",
                    "source_camera": "collision_camera_077",
                }
            ],
            "required_artifacts": 3,
            "cosmetic_combat": {
                "enable_death_counter": True,
                "energy_per_tank": 120,
                "default_x_released": False,
                "enable_room_name_display": "NEVER",
            },
            "starting_missiles": 20,
            "start_with_pulse_radar": True,
        }
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        self.assertEqual(len(patcher["door_patches"]), 1)
        self.assertEqual(len(patcher["elevators"]), 1)
        self.assertEqual(
            patcher["cosmetic_patches"]["lua"]["custom_init"]["enable_room_name_display"],
            "ALWAYS",
        )
        self.assertEqual(
            patcher["cosmetic_patches"]["lua"]["camera_names_dict"]["s010_cave"][
                "collision_camera_077"
            ],
            "Transport to Cataris - Thermal Device",
        )
        self.assertEqual(patcher["objective"]["required_artifacts"], 3)
        self.assertEqual(patcher["starting_items"]["ITEM_RANDO_ARTIFACT_4"], 1)
        self.assertNotIn("ITEM_RANDO_ARTIFACT_3", patcher["starting_items"])
        self.assertEqual(patcher["energy_per_tank"], 120)
        self.assertEqual(patcher["starting_items"]["ITEM_WEAPON_MISSILE_MAX"], 20)
        self.assertEqual(patcher["starting_items"]["ITEM_SONAR"], 1)

    def test_all_bosses_hints_use_required_dna_not_forced_artifacts(self):
        """All Bosses DNA=0 forces artifacts=1 for the door, but ADAM text stays boss-only."""
        import ap_to_patcher as ap

        patcher = {"objective": {}, "starting_items": {}, "cosmetic_patches": {}}
        extras = {
            "game_goal": 2,
            "required_artifacts": 1,
            "required_dna": 0,
        }
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        self.assertEqual(patcher["objective"]["required_artifacts"], 1)
        self.assertEqual(
            patcher["objective"]["hints"],
            ["Defeat every boss, then defeat Raven Beak."],
        )
        self.assertEqual(patcher["starting_items"].get("ITEM_RANDO_ARTIFACT_2"), 1)
        self.assertNotIn("ITEM_RANDO_ARTIFACT_1", patcher["starting_items"])

    def test_objective_hints_all_bosses_with_dna(self):
        import ap_to_patcher as ap

        self.assertEqual(
            ap._objective_hints_for(3, game_goal=2),
            ["Defeat every boss, collect 3 Metroid DNA, then defeat Raven Beak."],
        )

    def test_metroidnization_grant_lua(self):
        import dread_client_bridge as bridge

        lua = bridge.format_metroidnization_grant_lua(reason="All Bosses")
        self.assertIn("ITEM_METROIDNIZATION", lua)
        self.assertIn("SetItemAmount", lua)
        self.assertIn("All Bosses", lua)

    def test_show_player_damage_false_writes_aimanager(self):
        """YAML show_player_damage:false must clear ODR AIManager.bShowPlayerDamage."""
        import ap_to_patcher as ap

        patcher = {
            "cosmetic_patches": {
                "config": {
                    "AIManager": {
                        "bShowBossLifebar": True,
                        "bShowEnemyLife": True,
                        "bShowEnemyDamage": True,
                        "bShowPlayerDamage": True,
                    }
                }
            }
        }
        extras = {
            "cosmetic_combat": {
                "bShowBossLifebar": False,
                "bShowEnemyLife": False,
                "bShowEnemyDamage": False,
                "bShowPlayerDamage": False,
            }
        }
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        ai = patcher["cosmetic_patches"]["config"]["AIManager"]
        self.assertFalse(ai["bShowPlayerDamage"])
        self.assertFalse(ai["bShowBossLifebar"])
        self.assertFalse(ai["bShowEnemyLife"])
        self.assertFalse(ai["bShowEnemyDamage"])

    def test_immediate_energy_parts_and_env_damage_write_odr_root(self):
        """YAML immediate / constant env damage must hit ODR top-level keys."""
        import ap_to_patcher as ap

        patcher = {
            "immediate_energy_parts": False,
            "energy_per_tank": 100,
            "constant_environment_damage": {"heat": None, "cold": None, "lava": None},
            "cosmetic_patches": {},
            "game_patches": {},
        }
        extras = {
            "cosmetic_combat": {
                "immediate_energy_parts": True,
                "energy_per_tank": 120,
                "constant_environment_damage": {
                    "heat": 20,
                    "cold": 15,
                    "lava": 0,  # 0 / omitted → null (vanilla)
                },
            }
        }
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        self.assertTrue(patcher["immediate_energy_parts"])
        self.assertEqual(patcher["energy_per_tank"], 120)
        self.assertEqual(
            patcher["constant_environment_damage"],
            {"heat": 20, "cold": 15, "lava": None},
        )

    def test_immediate_energy_parts_false_forces_tank_100(self):
        """RDV: Energy Per Tank only applies with Immediate Energy Parts."""
        import ap_to_patcher as ap

        patcher = {
            "immediate_energy_parts": True,
            "energy_per_tank": 200,
            "constant_environment_damage": {},
            "cosmetic_patches": {},
            "game_patches": {},
        }
        extras = {
            "cosmetic_combat": {
                "immediate_energy_parts": False,
                "energy_per_tank": 200,
            }
        }
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        self.assertFalse(patcher["immediate_energy_parts"])
        self.assertEqual(patcher["energy_per_tank"], 100.0)

    def test_show_dna_in_hud_omitted_for_old_odr_schema(self):
        """ODR ≤2.18 rejects show_dna_in_hud (additionalProperties: false)."""
        import ap_to_patcher as ap

        patcher = {"cosmetic_patches": {}, "objective": {}, "starting_items": {}}
        extras = {
            "cosmetic_combat": {
                "enable_death_counter": True,
                "enable_room_name_display": "WITH_FADE",
                "show_dna_in_hud": True,
            }
        }
        old_schema_keys = frozenset(
            {"enable_death_counter", "enable_room_name_display"}
        )
        with mock.patch.object(
            ap, "_load_odr_custom_init_properties", return_value=old_schema_keys
        ):
            ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        custom_init = patcher["cosmetic_patches"]["lua"]["custom_init"]
        self.assertTrue(custom_init.get("enable_death_counter"))
        self.assertEqual(custom_init.get("enable_room_name_display"), "WITH_FADE")
        self.assertNotIn("show_dna_in_hud", custom_init)

    def test_sanitize_custom_init_strips_show_dna_for_old_odr(self):
        import ap_to_patcher as ap

        patcher = {
            "cosmetic_patches": {
                "lua": {
                    "custom_init": {
                        "enable_death_counter": True,
                        "enable_room_name_display": "WITH_FADE",
                        "show_dna_in_hud": True,
                    }
                }
            }
        }
        old_schema_keys = frozenset(
            {"enable_death_counter", "enable_room_name_display"}
        )
        with mock.patch.object(
            ap, "_load_odr_custom_init_properties", return_value=old_schema_keys
        ):
            removed = ap.sanitize_custom_init_for_odr(patcher)
        self.assertEqual(removed, ["show_dna_in_hud"])
        self.assertNotIn(
            "show_dna_in_hud",
            patcher["cosmetic_patches"]["lua"]["custom_init"],
        )

    def test_sanitize_root_strips_has_flash_for_old_odr(self):
        """ODR ≤2.18 rejects has_flash_upgrades at root (additionalProperties)."""
        import ap_to_patcher as ap

        patcher = {
            "configuration_identifier": "AP",
            "has_flash_upgrades": True,
            "has_speed_upgrades": False,
            "enable_logging": False,
        }
        old_root = frozenset(
            {
                "configuration_identifier",
                "starting_location",
                "starting_items",
                "pickups",
                "enable_remote_lua",
            }
        )
        with mock.patch.object(ap, "_load_odr_root_properties", return_value=old_root):
            removed = ap.sanitize_root_for_odr(patcher)
        self.assertEqual(
            set(removed),
            {"has_flash_upgrades", "has_speed_upgrades", "enable_logging"},
        )
        self.assertNotIn("has_flash_upgrades", patcher)
        self.assertIn("configuration_identifier", patcher)

    def test_sanitize_patcher_strips_skew_fields(self):
        import ap_to_patcher as ap

        patcher = {
            "has_flash_upgrades": True,
            "cosmetic_patches": {
                "split_saves": True,
                "lua": {"custom_init": {"show_dna_in_hud": True, "enable_death_counter": True}},
            },
        }
        with mock.patch.object(
            ap,
            "_load_odr_root_properties",
            return_value=frozenset({"cosmetic_patches", "pickups"}),
        ), mock.patch.object(
            ap,
            "_load_odr_schema",
            return_value={
                "properties": {
                    "cosmetic_patches": {
                        "properties": {
                            "config": {},
                            "lua": {
                                "properties": {
                                    "custom_init": {
                                        "properties": {
                                            "enable_death_counter": {},
                                            "enable_room_name_display": {},
                                        }
                                    }
                                }
                            },
                            "shield_versions": {},
                        }
                    }
                }
            },
        ), mock.patch.object(
            ap,
            "_load_odr_custom_init_properties",
            return_value=frozenset(
                {"enable_death_counter", "enable_room_name_display"}
            ),
        ):
            removed = ap.sanitize_patcher_for_odr(patcher)
        self.assertIn("has_flash_upgrades", removed)
        self.assertIn("cosmetic_patches.split_saves", removed)
        self.assertIn("show_dna_in_hud", removed)
        self.assertNotIn("has_flash_upgrades", patcher)
        self.assertNotIn("split_saves", patcher["cosmetic_patches"])
        self.assertNotIn(
            "show_dna_in_hud",
            patcher["cosmetic_patches"]["lua"]["custom_init"],
        )

    def test_apply_upgrade_menu_flags_respects_schema(self):
        import ap_to_patcher as ap

        patcher = {
            "starting_items": {"ITEM_UPGRADE_FLASH_SHIFT_CHAIN": 1},
            "pickups": [
                {
                    "resources": [
                        [{"item_id": "ITEM_UPGRADE_SPEED_BOOST_CHARGE", "quantity": 1}]
                    ]
                }
            ],
        }
        with mock.patch.object(ap, "_root_field_supported", return_value=True):
            ap.apply_upgrade_menu_flags(patcher)
        self.assertTrue(patcher["has_flash_upgrades"])
        self.assertTrue(patcher["has_speed_upgrades"])

        with mock.patch.object(ap, "_root_field_supported", return_value=False):
            ap.apply_upgrade_menu_flags(patcher)
        self.assertNotIn("has_flash_upgrades", patcher)
        self.assertNotIn("has_speed_upgrades", patcher)

    def test_apply_disabled_lights(self):
        import ap_to_patcher as ap

        patcher = {"mass_delete_actors": {"to_remove": [], "to_keep": []}}
        extras = {"disabled_lights": ["artaria", "cataris"]}
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        mda = patcher["mass_delete_actors"]
        self.assertIsInstance(mda, dict)
        self.assertEqual(
            mda["to_remove"],
            [
                {"scenario": "s010_cave", "actor_layer": "rLightsLayer", "method": "all"},
                {"scenario": "s020_magma", "actor_layer": "rLightsLayer", "method": "all"},
            ],
        )

    def test_coerce_legacy_mass_delete_format(self):
        import ap_to_patcher as ap

        patcher = {
            "mass_delete_actors": [
                {
                    "scenario": "s010_cave",
                    "actor_layer": "rLightsLayer",
                    "method": ["all"],
                }
            ]
        }
        extras = {"disabled_lights": ["burenia"]}
        ap.apply_dread_patch_extras(patcher, extras, our_player="Samus")
        mda = patcher["mass_delete_actors"]
        self.assertIsInstance(mda, dict)
        self.assertEqual(mda["to_remove"][0]["method"], "all")
        self.assertEqual(
            mda["to_remove"][-1],
            {"scenario": "s040_aqua", "actor_layer": "rLightsLayer", "method": "all"},
        )

    def test_parse_extras_from_spoiler_lines(self):
        import ap_to_patcher as ap

        with tempfile.TemporaryDirectory() as td:
            spoiler = Path(td) / "spoiler.txt"
            payload = {"required_artifacts": 2, "door_patches": []}
            spoiler.write_text(
                "Seed: 1\n"
                f"DREAD_PATCH_EXTRAS_JSON:Samus:{json.dumps(payload)}\n"
                'DREAD_DNA_LOCATIONS:Samus:["Artaria - Central Unit Access - Pickup (Spider Magnet)"]\n',
                encoding="utf-8",
            )
            extras = ap.parse_dread_patch_extras(spoiler, "Samus")
            self.assertEqual(extras["required_artifacts"], 2)
            self.assertEqual(len(extras["dna_locations"]), 1)


class TestDnaArtifactLogic(unittest.TestCase):
    def test_artifacts_open_when_required_zero(self):
        from worlds.metroid_dread.dread_logic import DreadLogic

        class Opt:
            required_dna = type("o", (), {"value": 0})()
            energy_per_tank = type("o", (), {"value": 100})()
            starting_power_bombs = type("o", (), {"value": 0})()
            power_bomb_tank_ammo = type("o", (), {"value": 1})()

            def __getattr__(self, name):
                return type("o", (), {"value": 0})()

        class World:
            player = 1
            options = Opt()

        with mock.patch("builtins.print"):
            logic = DreadLogic(World())
        inv = logic.inventory_from_counts({})
        self.assertTrue(
            logic._resource_ok("items", "Artifact1", 1, inv)
        )
        self.assertTrue(
            logic._resource_ok("items", "Artifact12", 1, inv)
        )

    def test_artifacts_need_dna_when_required(self):
        from worlds.metroid_dread.dread_logic import DreadLogic

        class Opt:
            required_dna = type("o", (), {"value": 3})()
            energy_per_tank = type("o", (), {"value": 100})()
            starting_power_bombs = type("o", (), {"value": 0})()
            power_bomb_tank_ammo = type("o", (), {"value": 1})()

            def __getattr__(self, name):
                return type("o", (), {"value": 0})()

        class World:
            player = 1
            options = Opt()

        with mock.patch("builtins.print"):
            logic = DreadLogic(World())
        empty = logic.inventory_from_counts({})
        self.assertFalse(logic._resource_ok("items", "Artifact1", 1, empty))
        # Beyond required are pre-granted
        self.assertTrue(logic._resource_ok("items", "Artifact4", 1, empty))
        with_dna = logic.inventory_from_counts({"Metroid DNA": 3})
        self.assertTrue(logic._resource_ok("items", "Artifact3", 1, with_dna))


class TestOptionsImport(unittest.TestCase):
    def test_options_dataclass_has_new_fields(self):
        from worlds.metroid_dread.Options import MetroidDreadOptions

        fields = MetroidDreadOptions.__dataclass_fields__
        for name in (
            "game_goal",
            "required_dna",
            "dna_placement",
            "door_lock_rando",
            "transport_rando",
            "energy_per_tank",
            "show_boss_lifebar",
            "include_boss_pickups",
            "immediate_energy_parts",
            "constant_heat_damage",
            "constant_cold_damage",
            "constant_lava_damage",
        ):
            self.assertIn(name, fields)


class TestTransportRandoSpawn(unittest.TestCase):
    def test_itorash_excluded_from_transport_shuffle(self):
        from worlds.metroid_dread.TransportRando import (
            _is_shufflable,
            roll_matching,
        )

        transports = {
            "Hanubia/Transport to Itorash/Elevator to Itorash": {
                "node_id": ("Hanubia", "Transport to Itorash", "Elevator to Itorash"),
                "type": "elevator",
                "vanilla_dest": ("Itorash", "Transport to Hanubia", "Elevator to Hanubia"),
            },
            "Itorash/Transport to Hanubia/Elevator to Hanubia": {
                "node_id": ("Itorash", "Transport to Hanubia", "Elevator to Hanubia"),
                "type": "elevator",
                "vanilla_dest": ("Hanubia", "Transport to Itorash", "Elevator to Itorash"),
            },
            "Artaria/A/E": {
                "node_id": ("Artaria", "A", "E"),
                "type": "elevator",
                "vanilla_dest": ("Cataris", "C", "E"),
            },
            "Cataris/C/E": {
                "node_id": ("Cataris", "C", "E"),
                "type": "elevator",
                "vanilla_dest": ("Artaria", "A", "E"),
            },
        }
        self.assertFalse(
            _is_shufflable(transports["Itorash/Transport to Hanubia/Elevator to Hanubia"])
        )
        self.assertFalse(
            _is_shufflable(transports["Hanubia/Transport to Itorash/Elevator to Itorash"])
        )
        self.assertTrue(_is_shufflable(transports["Artaria/A/E"]))

        class _Rng:
            def shuffle(self, xs):
                xs.sort()

        matching = roll_matching(transports, _Rng(), mode="randomized")
        self.assertNotIn("Itorash/Transport to Hanubia/Elevator to Hanubia", matching)
        self.assertNotIn("Hanubia/Transport to Itorash/Elevator to Itorash", matching)
        self.assertEqual(matching.get("Artaria/A/E"), "Cataris/C/E")

    def test_arrival_spawn_prefers_local_start_point(self):
        from worlds.metroid_dread.TransportRando import _arrival_spawn

        extra = {
            "target_spawn_point": "LE_Platform_Elevator_FromMagma",
            "start_point_actor_name": "LE_Platform_Elevator_FromCave",
            "actor_name": "LE_Elevator_FromCave",
        }
        self.assertEqual(
            _arrival_spawn(extra, "LE_Elevator_FromCave"),
            "LE_Platform_Elevator_FromCave",
        )

    def test_matching_uses_arrival_spawn_and_transporter_name(self):
        from worlds.metroid_dread.TransportRando import matching_to_elevators

        transports = {
            "A/Ta/Na": {
                "node_id": ("Artaria", "Transport to Cataris", "Elevator"),
                "scenario": "s010_cave",
                "actor": "LE_Elevator_FromMagma",
                "arrival_spawn": "LE_Platform_Elevator_FromMagma",
                "asset_id": "collision_camera_077",
                "transporter_name": "Artaria - Hot Feet",
            },
            "C/Ta/Na": {
                "node_id": ("Cataris", "Transport to Artaria", "Elevator"),
                "scenario": "s020_magma",
                "actor": "LE_Elevator_FromCave",
                "arrival_spawn": "LE_Platform_Elevator_FromCave",
                "asset_id": "collision_camera_000",
                "transporter_name": "Cataris - Entrance",
            },
        }
        matching = {"A/Ta/Na": "C/Ta/Na", "C/Ta/Na": "A/Ta/Na"}
        elevators = matching_to_elevators(matching, transports)
        by_actor = {e["teleporter"]["actor"]: e for e in elevators}
        artaria = by_actor["LE_Elevator_FromMagma"]
        self.assertEqual(artaria["destination"]["scenario"], "s020_magma")
        self.assertEqual(
            artaria["destination"]["actor"], "LE_Platform_Elevator_FromCave"
        )
        self.assertEqual(artaria["connection_name"], "Cataris - Entrance")
        self.assertEqual(artaria["source_camera"], "collision_camera_077")


def _fake_start_kit_world(start_node_id, trick_value=5, trick_key="expert"):
    """Minimal world stub for StartKit.build_start_kit unit tests."""
    import random

    from worlds.metroid_dread.dread_logic import DreadLogic

    class _O:
        def __init__(self, v=0, key="disabled"):
            self.value = v
            self.current_key = key

        def __bool__(self):
            return bool(self.value)

    class FakeOpt:
        required_dna = _O(0)
        progressive_beams = _O(0)
        progressive_charge = _O(1)
        progressive_missiles = _O(0)
        progressive_bombs = _O(0)
        progressive_suit = _O(1)
        progressive_spin = _O(1)
        start_with_pulse_radar = _O(0)
        reverse_grapple_block = _O(1)

        def __getattr__(self, _name):
            return _O(trick_value, trick_key)

    class FakeWorld:
        player = 1
        options = FakeOpt()

        def active_location_names(self):
            return set(self.logic.pickup_nodes)

    world = FakeWorld()
    world.random = random.Random(0)
    world.logic = DreadLogic(world)
    world.logic.set_starting_node(start_node_id)
    return world


class TestStartKitTightFit(unittest.TestCase):
    def test_hanubia_prefers_bomb_over_power_bomb(self):
        """Hanubia must not be handed Power Bomb just to open sphere 0."""
        from worlds.metroid_dread import StartKit
        from worlds.metroid_dread.starting_locations import get_by_option_key

        world = _fake_start_kit_world(
            get_by_option_key("hanubia_navigation_station_save_station").node_id
        )
        kit = StartKit.build_start_kit(world)
        self.assertIn("Morph Ball", kit)
        self.assertTrue("Bomb" in kit or "Cross Bomb" in kit)
        self.assertNotIn("Power Bomb", kit)
        self.assertGreaterEqual(
            StartKit.start_checks(world, StartKit.kit_counts(kit)),
            StartKit.MIN_START_LOCATIONS,
        )

    def test_artaria_intro_empty_kit_at_min_two(self):
        """Intro already has two in-logic checks; min=2 must not grant Cloak etc."""
        from worlds.metroid_dread import StartKit
        from worlds.metroid_dread.starting_locations import DEFAULT_START

        self.assertEqual(StartKit.MIN_START_LOCATIONS, 2)
        world = _fake_start_kit_world(DEFAULT_START)
        empty_checks = StartKit.start_checks(world, {})
        self.assertGreaterEqual(empty_checks, StartKit.MIN_START_LOCATIONS)
        kit = StartKit.build_start_kit(world)
        self.assertEqual(kit, [])
        self.assertNotIn("Phantom Cloak", kit)


class TestAmmoYieldOverrides(unittest.TestCase):
    def test_yields_rewrite_pickup_resources(self):
        import ap_to_patcher as ap

        resources, caption, _ = ap._pickup_resources_and_caption(
            "Missile Tank",
            False,
            yield_plan={
                "missile_tank_ammo": 5,
                "missile_plus_tank_ammo": 20,
                "power_bomb_tank_ammo": 3,
                "energy_per_tank": 200,
            },
        )
        self.assertEqual(resources[0][0]["quantity"], 5)
        self.assertIn("5", caption)

        resources, caption, _ = ap._pickup_resources_and_caption(
            "Energy Tank",
            False,
            yield_plan={
                "missile_tank_ammo": 2,
                "missile_plus_tank_ammo": 10,
                "power_bomb_tank_ammo": 1,
                "energy_per_tank": 200,
            },
        )
        self.assertEqual(resources[0][0]["quantity"], 200)
        self.assertIn("200", caption)

    def test_client_bridge_uses_extras_yields(self):
        import dread_client_bridge as bridge

        prog = bridge.get_item_resources(
            "Power Bomb Tank",
            extras={"power_bomb_tank_ammo": 4},
        )
        self.assertEqual(prog[0][0]["quantity"], 4)


if __name__ == "__main__":
    unittest.main()

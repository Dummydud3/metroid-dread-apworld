"""
Tests for Metroid Bread victory-implies-90% clearance.
"""

from __future__ import annotations

import unittest
import warnings

warnings.filterwarnings("ignore")


def _bootstrap():
    from worlds.AutoWorld import AutoWorldRegister, call_all
    from Fill import FillError, distribute_items_restrictive
    from test.general import gen_steps, setup_multiworld
    from worlds.metroid_bread import victory_clearance
    import worlds.metroid_bread as md

    return {
        "AutoWorldRegister": AutoWorldRegister,
        "call_all": call_all,
        "FillError": FillError,
        "distribute_items_restrictive": distribute_items_restrictive,
        "gen_steps": gen_steps,
        "setup_multiworld": setup_multiworld,
        "victory_clearance": victory_clearance,
        "md": md,
        "world_type": AutoWorldRegister.world_types["Metroid Bread"],
    }


class TestVictoryClearance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ap = _bootstrap()

    def _gen(self, seed: int, options: dict):
        ap = self.ap
        mw = ap["setup_multiworld"](
            ap["world_type"], steps=ap["gen_steps"], seed=seed, options=options
        )
        ap["distribute_items_restrictive"](mw)
        return mw

    def test_required_clearance_count_ceil_90(self):
        vc = self.ap["victory_clearance"]
        self.assertEqual(vc.required_clearance_count(0), 0)
        self.assertEqual(vc.required_clearance_count(1), 1)
        self.assertEqual(vc.required_clearance_count(10), 9)
        self.assertEqual(vc.required_clearance_count(100), 90)
        self.assertEqual(vc.allowed_missing_at_victory(100), 10)
        self.assertEqual(vc.required_clearance_count(100, 1.0), 100)
        self.assertEqual(vc.allowed_missing_at_victory(100, 1.0), 0)

    def test_game_goal_option_names(self):
        from worlds.metroid_bread.Options import GameGoal

        self.assertEqual(GameGoal.get_option_name(GameGoal.option_one_hundred_percent), "100%")
        self.assertEqual(GameGoal.get_option_name(GameGoal.option_all_bosses), "All Bosses")
        self.assertEqual(GameGoal.option_defeat_raven_beak, 0)
        self.assertEqual(GameGoal.option_one_hundred_percent, 1)
        self.assertEqual(GameGoal.option_all_bosses, 2)

    def test_boss_catalog_covers_required_fights(self):
        from worlds.metroid_bread import bosses

        keys = {b.key for b in bosses.ALL_BOSSES}
        for required in (
            "corpius",
            "kraid",
            "drogyga",
            "escue",
            "golzuna",
            "z57",
            "quiet_robe",
            "elun_chozo_soldier",
            "chozo_x",
            "hanubia_gold_chozo",
            "hanubia_red_chozo",
            "burenia_twin_robots",
            "ferenia_twin_robots",
            "ghavoran_gold_robot",
            "raven_beak",
        ):
            self.assertIn(required, keys)
        z57 = next(b for b in bosses.ALL_BOSSES if b.key == "z57")
        self.assertIsNone(z57.event_item)
        self.assertEqual(z57.check_location, bosses.Z57_LOCATION_NAME)
        self.assertEqual(bosses.check_location_ids()["z57"], 84037)

        gold = next(b for b in bosses.ALL_BOSSES if b.key == "ghavoran_gold_robot")
        twin = next(b for b in bosses.ALL_BOSSES if b.key == "burenia_twin_robots")
        self.assertEqual(gold.spawn_group, "SG_ChozoRobotSoldier")
        self.assertEqual(gold.spawn_scenario, "s050_forest")
        self.assertEqual(twin.spawn_group, "SG_2RCW_000")
        self.assertEqual(twin.spawn_scenario, "s040_aqua")
        self.assertNotEqual(gold.spawn_group, twin.spawn_group)

        # Every non-RB boss must have a unique primary detection path.
        seen_spawn = set()
        for boss in bosses.required_bosses_excluding_raven():
            has_check = bool(boss.check_location)
            has_spawn = bool(boss.spawn_group and boss.spawn_scenario)
            has_progress = bool(boss.progress_prop)
            self.assertTrue(
                has_check or has_spawn or has_progress,
                msg=f"{boss.key} needs check_location, spawn probe, or progress_prop",
            )
            if has_spawn:
                sig = (boss.spawn_scenario, boss.spawn_group, boss.min_deaths)
                self.assertNotIn(sig, seen_spawn, msg=f"duplicate spawn probe {sig}")
                seen_spawn.add(sig)

        self.assertEqual(
            bosses.check_location_ids()["hanubia_red_chozo"],
            84143,
        )

    def test_all_bosses_post_fill(self):
        """All Bosses: Raven Beak opens only with every boss node in logic."""
        vc = self.ap["victory_clearance"]
        from worlds.metroid_bread import bosses

        mw = self._gen(
            22,
            {
                "game_goal": "all_bosses",
                "required_dna": 0,
                "accessibility": "items",
                "starting_location": "default",
            },
        )
        self.ap["call_all"](mw, "post_fill")
        world = mw.worlds[1]
        self.assertEqual(int(world.options.game_goal.value), 2)
        self.assertEqual(vc.clearance_ratio_for_world(world), 0.9)
        state = vc.collection_state_at_victory(world)
        locked = [
            n
            for n in bosses.missing_bosses_at_state(world, state)
            if n != "Raven Beak"
        ]
        self.assertEqual(locked, [])
        slot = world.fill_slot_data()
        self.assertEqual(slot.get("game_goal"), 2)
        self.assertEqual(slot.get("required_dna"), 0)
        extras = slot.get("patch_extras") or {}
        # Physical Itorash ADAM door: force required_artifacts≥1 even with DNA=0.
        self.assertEqual(extras.get("required_artifacts"), 1)
        self.assertEqual(extras.get("required_dna"), 0)
        self.assertEqual(extras.get("game_goal"), 2)
        # Boss event items are filler and never enter prog_items; completion
        # must still report beatable via node reachability.
        self.assertTrue(mw.can_beat_game())

    def test_all_bosses_with_dna_keeps_real_artifact_count(self):
        """All Bosses + DNA>0: patch artifacts match DNA (not forced to 1)."""
        mw = self._gen(
            23,
            {
                "game_goal": "all_bosses",
                "required_dna": 3,
                "accessibility": "items",
                "starting_location": "default",
            },
        )
        self.ap["call_all"](mw, "post_fill")
        world = mw.worlds[1]
        slot = world.fill_slot_data()
        extras = slot.get("patch_extras") or {}
        self.assertEqual(slot.get("required_dna"), 3)
        self.assertEqual(extras.get("required_artifacts"), 3)
        self.assertEqual(extras.get("required_dna"), 3)

    def test_accessibility_minimal_upgraded_to_items(self):
        mw = self._gen(
            1,
            {
                "required_dna": 0,
                "accessibility": "minimal",
                "starting_location": "default",
            },
        )
        self.assertEqual(mw.worlds[1].options.accessibility.current_key, "items")
        self.ap["call_all"](mw, "post_fill")

    def test_accessibility_full_downgraded_to_items(self):
        mw = self._gen(
            1,
            {
                "required_dna": 0,
                "accessibility": "full",
                "starting_location": "default",
            },
        )
        self.assertEqual(mw.worlds[1].options.accessibility.current_key, "items")
        self.ap["call_all"](mw, "post_fill")

    def test_post_fill_passes_hanubia_dna0(self):
        """Hanubia DNA0 used to produce 2-check softballs under Minimal."""
        vc = self.ap["victory_clearance"]
        for seed in range(1, 8):
            with self.subTest(seed=seed):
                mw = self._gen(
                    seed,
                    {
                        "required_dna": 0,
                        "accessibility": "minimal",
                        "starting_location": "hanubia_navigation_station_save_station",
                    },
                )
                self.ap["call_all"](mw, "post_fill")
                world = mw.worlds[1]
                missing = vc.missing_checks_at_victory(world)
                clearable_n = len(vc.clearable_pickup_names(world))
                self.assertLessEqual(
                    len(missing),
                    vc.allowed_missing_at_victory(clearable_n),
                )

    def test_raw_rb_without_clearance_is_rejected_by_gate(self):
        """Boss node alone must not satisfy the Raven Beak access rule."""
        from BaseClasses import CollectionState

        ap = self.ap
        mw = self._gen(
            5,
            {
                "required_dna": 0,
                "accessibility": "minimal",
                "starting_location": "hanubia_navigation_station_save_station",
            },
        )
        world = mw.worlds[1]
        # Inventory that can touch the boss node from Hanubia DNA0 (start kit
        # already has Morph+Bomb; add Power Bomb for the generator) but not 90%.
        state = CollectionState(mw)
        for name in ("Power Bomb", "Spider Magnet", "Speed Booster", "Spin Boost"):
            state.collect(world.create_item(name), True)

        raw_nodes = world.logic.get_reachable_nodes(
            world.logic.inventory_from_state(state)
        )
        goal = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")
        gated = ap["victory_clearance"].inventory_reaches_victory_and_clearance(
            world, state
        )
        self.assertFalse(
            gated,
            "partial inventory must not satisfy victory-implies-90% gate",
        )
        if goal in raw_nodes:
            victory = mw.get_location("Raven Beak", 1)
            self.assertFalse(victory.can_reach(state))

    def test_one_hundred_percent_post_fill(self):
        """100% goal: Raven Beak must not open with any clearable check locked."""
        vc = self.ap["victory_clearance"]
        mw = self._gen(
            21,
            {
                "game_goal": "one_hundred_percent",
                "required_dna": 0,
                "accessibility": "items",
                "starting_location": "default",
            },
        )
        self.ap["call_all"](mw, "post_fill")
        world = mw.worlds[1]
        self.assertEqual(int(world.options.game_goal.value), 1)
        self.assertEqual(vc.clearance_ratio_for_world(world), 1.0)
        missing = vc.missing_checks_at_victory(world)
        self.assertEqual(missing, [])
        # Slot data exposes the goal for the client.
        slot = world.fill_slot_data()
        self.assertEqual(slot.get("game_goal"), 1)

    def test_dna_and_transport_variants(self):
        vc = self.ap["victory_clearance"]
        cases = [
            {"required_dna": 0, "accessibility": "items"},
            {"required_dna": 6, "accessibility": "full"},
            {"required_dna": 12, "accessibility": "minimal"},
            {
                "required_dna": 0,
                "transport_rando": "randomized",
                "accessibility": "minimal",
            },
            {
                "required_dna": 3,
                "starting_location": "random_save_station",
                "early_morph_ball": True,
                "accessibility": "minimal",
            },
        ]
        for seed, opts in enumerate(cases, start=10):
            with self.subTest(seed=seed, opts=opts):
                mw = self._gen(seed, opts)
                self.ap["call_all"](mw, "post_fill")
                world = mw.worlds[1]
                missing = vc.missing_checks_at_victory(world)
                clearable_n = len(vc.clearable_pickup_names(world))
                self.assertLessEqual(
                    len(missing),
                    vc.allowed_missing_at_victory(clearable_n),
                )

    def test_combat_off_low_ept_raises_base_energy(self):
        """Fuzz 80/207: combat off + tiny EPT made Raven Beak unreachable."""
        mw = self.ap["setup_multiworld"](
            self.ap["world_type"],
            steps=("generate_early",),
            seed=80,
            options={
                "combat_tricks": "disabled",
                "energy_per_tank": 17,
                "energy_tanks": 9,
                "energy_parts": 6,
                "door_lock_rando": "vanilla",
                "transport_rando": "off",
                "starting_location": "default",
                "accessibility": "items",
            },
        )
        world = mw.worlds[1]
        # Gold Chozo-X / Raven Beak Damage gate with Combat tricks disabled.
        self.assertGreaterEqual(int(world.options.energy_per_tank.value) - 1, 799)
        goal = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")
        nodes = world.logic.get_reachable_nodes(
            world.logic.inventory_from_counts(world._full_inventory_counts())
        )
        self.assertIn(goal, nodes)

    def test_combat_off_post_fill_with_zero_etanks(self):
        """Fuzz 19: 0 Energy Tanks + combat off softlocked Gold Chozo."""
        mw = self._gen(
            19,
            {
                "combat_tricks": "disabled",
                "energy_per_tank": 153,
                "energy_tanks": 0,
                "energy_parts": 8,
                "required_dna": 4,
                "game_goal": "one_hundred_percent",
                "door_lock_rando": "vanilla",
                "transport_rando": "off",
                "starting_location": "default",
                "accessibility": "items",
            },
        )
        self.ap["call_all"](mw, "post_fill")
        world = mw.worlds[1]
        self.assertGreaterEqual(int(world.options.energy_per_tank.value) - 1, 799)

    def test_cramped_start_relocates_when_sphere0_dead_end(self):
        """Fuzz 97: Artaria Save East + transport did not expand after early fill."""
        mw = self.ap["setup_multiworld"](
            self.ap["world_type"],
            steps=("generate_early",),
            seed=97,
            options={
                "starting_location": "artaria_save_station_east_save_station",
                "transport_rando": "randomized",
                "door_lock_rando": "vanilla",
                "required_dna": 12,
                "include_boss_pickups": False,
                "dna_placement": "anywhere",
                "accessibility": "items",
            },
        )
        world = mw.worlds[1]
        self.assertTrue(
            world._start_sphere_expands(),
            msg=f"start {world.logic.starting_node} kit={world.start_kit} must expand",
        )

    def test_dna_item_group_for_hints(self):
        """!hint DNA resolves via item_name_groups to Metroid DNA."""
        from worlds.metroid_bread.Items import item_name_groups

        self.assertIn("Metroid DNA", item_name_groups["DNA"])
        self.assertIn("Metroid DNA", item_name_groups["Metroid DNA"])
        world_type = self.ap["world_type"]
        self.assertIn("Metroid DNA", world_type.item_name_groups["DNA"])

    def test_dna_preplace_avoids_stale_artaria_intros(self):
        """Fuzz 168: Ferenia start must not lock DNA onto Artaria tutorials."""
        mw = self.ap["setup_multiworld"](
            self.ap["world_type"],
            steps=("generate_early", "create_regions", "create_items", "set_rules", "pre_fill"),
            seed=168,
            options={
                # Mirror fuzz 168 enough that start stays Ferenia (not relocated).
                "starting_location": "ferenia_navigation_station_save_station",
                "early_morph_ball": True,
                "required_dna": 4,
                "dna_placement": "prefer_emmi",
                "include_boss_pickups": False,
                "door_lock_rando": "vanilla",
                "transport_rando": "off",
                "accessibility": "items",
                "x_starts_released": True,
                "knowledge_tricks": "hard",
                "movement_tricks": "expert",
                "combat_tricks": "advanced",
                "heat_cold_runs": "expert",
            },
        )
        world = mw.worlds[1]
        self.assertEqual(world.logic.starting_node[0], "Ferenia")
        dna_locs = [
            loc.name
            for loc in mw.get_locations(world.player)
            if loc.item and loc.item.name == "Metroid DNA" and loc.item.player == world.player
        ]
        self.assertEqual(len(dna_locs), 4)
        for name in dna_locs:
            self.assertFalse(
                any(
                    s in name
                    for s in (
                        "Charge Tutorial",
                        "Melee Tutorial Room",
                        "EMMI Zone First Entrance",
                    )
                ),
                msg=f"DNA locked on stale Artaria intro: {name}",
            )
            self.assertTrue(
                any(
                    s in name
                    for s in (
                        "Central Unit Access",
                        "Purple EMMI Arena",
                        "Orange EMMI Introduction",
                    )
                ),
                msg=f"prefer_emmi DNA expected on EMMI/CU sink, got {name}",
            )

    def test_dna_preplace_high_prefer_bosses_fills(self):
        """Fuzz 30: DNA=12 prefer_bosses + no boss pickups must still fill."""
        mw = self._gen(
            30,
            {
                "starting_location": "cataris_navigation_station_southeast_save_station",
                "required_dna": 12,
                "dna_placement": "prefer_bosses",
                "include_boss_pickups": False,
                "door_lock_rando": "vanilla",
                "transport_rando": "off",
                "accessibility": "items",
                "combat_tricks": "expert",
                "heat_cold_runs": "ludicrous",
                "movement_tricks": "medium",
                "knowledge_tricks": "intermediate",
                "energy_per_tank": 462,
                "start_with_pulse_radar": True,
            },
        )
        world = mw.worlds[1]
        dna_locs = [
            loc.name
            for loc in mw.get_locations(world.player)
            if loc.item and loc.item.name == "Metroid DNA" and loc.item.player == world.player
        ]
        self.assertEqual(len(dna_locs), 12)
        self.ap["call_all"](mw, "post_fill")

    def test_cramped_sphere0_pins_expand_openers(self):
        """Exactly-2 early checks pin Morph (etc.) into local_early_items."""
        from worlds.metroid_bread import StartKit

        # Artaria Intro: empty kit, two melee/corpius checks — Morph must be early.
        mw = self.ap["setup_multiworld"](
            self.ap["world_type"],
            steps=("generate_early", "create_regions", "create_items"),
            seed=1,
            options={
                "starting_location": "default",
                "door_lock_rando": "vanilla",
                "transport_rando": "off",
                "required_dna": 0,
                "accessibility": "items",
                "early_morph_ball": False,
            },
        )
        world = mw.worlds[1]
        early_n = len(
            world.logic.reachable_pickup_names(StartKit.kit_counts(world.start_kit))
        )
        self.assertEqual(early_n, 2)
        self.assertIn("Morph Ball", world.early_expand_pins)
        self.assertGreaterEqual(
            mw.local_early_items[world.player].get("Morph Ball", 0), 1
        )

    def test_fuzz_434_fill_with_cramped_save_east(self):
        """Fuzz 434: Artaria Save East + doors/transport must complete fill."""
        mw = self._gen(
            264219053,
            {
                "game_goal": "one_hundred_percent",
                "required_dna": 11,
                "dna_placement": "anywhere",
                "door_lock_rando": "individual_doors",
                "doors_to_change": {"Missile Door", "Access Open"},
                "change_doors_to": {"Plasma Beam Door"},
                "transport_rando": "randomized",
                "include_boss_pickups": False,
                "starting_location": "artaria_save_station_east_save_station",
                "early_morph_ball": False,
                "progressive_beams": True,
                "progressive_charge": True,
                "progressive_bombs": False,
                "progressive_suit": True,
                "progressive_spin": False,
                "knowledge_tricks": "expert",
                "movement_tricks": "hard",
                "combat_tricks": "hard",
                "accessibility": "items",
                "x_starts_released": True,
                "energy_tanks": 1,
                "energy_parts": 5,
                "missile_tanks": 17,
                "missile_plus_tanks": 15,
                "power_bomb_tanks": 8,
                "energy_per_tank": 629,
                "pseudo_wave": "beginner",
                "infinite_bomb_jump": "intermediate",
                "water_bomb_jump": "ludicrous",
                "water_space_jump": "ludicrous",
                "single_wall_wall_jump": "advanced",
                "slide_jump": "hard",
                "speedbooster_conservation": "beginner",
                "wall_jump_tricks": "hard",
                "heat_cold_runs": "hard",
                "damage_boost": "ludicrous",
                "stand_on_frozen_enemy": "disabled",
                "grapple_movement": "easy",
                "cross_bomb_skip": "disabled",
                "climb_sloped_tunnels": "expert",
                "short_boost": "hard",
                "diffusion_abuse": "advanced",
                "flash_shift_skip": "intermediate",
                "diagonal_bomb_jump": "hard",
                "ledge_warp": "intermediate",
                "cross_bomb_launch": "ludicrous",
                "floor_clip": "medium",
                "climb_sloped_surfaces": "ludicrous",
            },
        )
        world = mw.worlds[1]
        self.assertEqual(world.logic.starting_node[1], "Save Station East")
        self.assertIn("Bomb", world.early_expand_pins)
        self.ap["call_all"](mw, "post_fill")


if __name__ == "__main__":
    unittest.main()

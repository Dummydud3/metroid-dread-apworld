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


if __name__ == "__main__":
    unittest.main()

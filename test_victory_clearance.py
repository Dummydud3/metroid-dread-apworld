"""
Tests for Metroid Dread victory-implies-90% clearance.
"""

from __future__ import annotations

import unittest
import warnings

warnings.filterwarnings("ignore")


def _bootstrap():
    from worlds.AutoWorld import AutoWorldRegister, call_all
    from Fill import FillError, distribute_items_restrictive
    from test.general import gen_steps, setup_multiworld
    from worlds.metroid_dread import victory_clearance
    import worlds.metroid_dread as md

    return {
        "AutoWorldRegister": AutoWorldRegister,
        "call_all": call_all,
        "FillError": FillError,
        "distribute_items_restrictive": distribute_items_restrictive,
        "gen_steps": gen_steps,
        "setup_multiworld": setup_multiworld,
        "victory_clearance": victory_clearance,
        "md": md,
        "world_type": AutoWorldRegister.world_types["Metroid Dread"],
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

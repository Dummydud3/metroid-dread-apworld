"""Tests for density-biased door softening (adaptive door rando)."""

from __future__ import annotations

import unittest
import warnings

warnings.filterwarnings("ignore")


def _bootstrap():
    from worlds.AutoWorld import AutoWorldRegister, call_all
    from Fill import distribute_items_restrictive
    from test.general import gen_steps, setup_multiworld
    from worlds.metroid_dread import DoorRando

    return {
        "AutoWorldRegister": AutoWorldRegister,
        "call_all": call_all,
        "distribute_items_restrictive": distribute_items_restrictive,
        "gen_steps": gen_steps,
        "setup_multiworld": setup_multiworld,
        "DoorRando": DoorRando,
        "world_type": AutoWorldRegister.world_types["Metroid Dread"],
    }


class TestDoorSoften(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ap = _bootstrap()

    def test_soften_assignments_and_pick(self):
        dr = self.ap["DoorRando"]
        assignments = {
            ("s010_cave", "doorpowerpower_000"): "Plasma Beam Door",
            ("s010_cave", "doorpowerpower_001"): "Wave Beam Door",
            ("s020_magma", "doorpowerpower_002"): "Power Beam Door",
        }
        scored = [
            (5, ("s010_cave", "doorpowerpower_000")),
            (0, ("s010_cave", "doorpowerpower_001")),
            (-1, ("s020_magma", "doorpowerpower_002")),
        ]
        keys = dr.pick_doors_to_soften(scored, top_k=2)
        self.assertEqual(keys, [("s010_cave", "doorpowerpower_000")])
        changed = dr.soften_assignments(assignments, keys)
        self.assertEqual(changed, [("s010_cave", "doorpowerpower_000")])
        self.assertEqual(
            assignments[("s010_cave", "doorpowerpower_000")],
            dr.SOFT_WEAKNESS,
        )

    def test_pick_falls_back_when_all_nonpositive(self):
        dr = self.ap["DoorRando"]
        scored = [
            (0, ("s010_cave", "a")),
            (-2, ("s010_cave", "b")),
            (0, ("s010_cave", "c")),
        ]
        keys = dr.pick_doors_to_soften(scored, top_k=2)
        self.assertEqual(keys, [("s010_cave", "a"), ("s010_cave", "b")])

    def test_door_lock_rando_gens_and_fills(self):
        """Door lock rando seeds should complete fill under victory-90%."""
        ap = self.ap
        for seed in (20, 21, 22):
            with self.subTest(seed=seed):
                mw = ap["setup_multiworld"](
                    ap["world_type"],
                    steps=ap["gen_steps"],
                    seed=seed,
                    options={
                        "door_lock_rando": "individual_doors",
                        "required_dna": 3,
                        "accessibility": "minimal",
                        "starting_location": "default",
                    },
                )
                ap["distribute_items_restrictive"](mw)
                ap["call_all"](mw, "post_fill")
                world = mw.worlds[1]
                # Softening may open some doors; patches should match assignments.
                self.assertEqual(
                    len(world.door_patches),
                    len(world.door_assignments),
                )

    def test_score_doors_runs_on_rolled_graph(self):
        ap = self.ap
        mw = ap["setup_multiworld"](
            ap["world_type"],
            steps=ap["gen_steps"],
            seed=30,
            options={
                "door_lock_rando": "individual_doors",
                "required_dna": 0,
                "starting_location": "default",
            },
        )
        world = mw.worlds[1]
        if not world.door_assignments:
            self.skipTest("seed rolled no door assignments")
        active = set(world.active_location_names())
        scored = ap["DoorRando"].score_doors_by_new_checks(
            world.logic,
            world.door_assignments,
            pickup_nodes={
                n: node
                for n, node in world.logic.pickup_nodes.items()
                if n in active
            },
            active_names=active,
            inventory_counts={name: 1 for name in ("Morph Ball", "Bomb")},
            goal_node=("Itorash", "Raven Beak Arena", "Boss - Raven Beak"),
        )
        self.assertIsInstance(scored, list)
        if scored:
            score, key = scored[0]
            self.assertIsInstance(score, int)
            self.assertEqual(len(key), 2)


if __name__ == "__main__":
    unittest.main()

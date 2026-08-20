"""Tests for light RDV-style Individual Doors assigner."""

from __future__ import annotations

import random
import unittest
import warnings
from collections import defaultdict
from unittest.mock import MagicMock

warnings.filterwarnings("ignore")


class TestDoorRandoDb(unittest.TestCase):
    def test_header_pools_and_proportion(self):
        from worlds.metroid_bread import door_rando_db as db

        self.assertAlmostEqual(db.to_shuffle_proportion(), 0.6)
        self.assertTrue(db.force_change_two_way())
        self.assertEqual(db.unlocked_weakness(), "Power Beam Door")
        self.assertIn("Sensor Lock Door", db.header_change_from())
        self.assertNotIn("Sensor Lock Door", db.header_change_to())
        self.assertNotIn("Sensor Lock Door", db.basic_change_to_weaknesses())
        self.assertNotIn("Phase Shift Door", db.basic_change_to_weaknesses())
        for name in db.basic_change_to_weaknesses():
            dt = db.odr_type_for_weakness(name)
            self.assertIn(dt, db.BASIC_ODR_DOOR_TYPES)
            self.assertNotIn(dt, db.ODR_CANNOT_ADD_DOOR_TYPES)


class TestGrappleIncompatAndEmitGuards(unittest.TestCase):
    def test_grapple_banned_on_incompat_docks(self):
        from worlds.metroid_bread import DoorRando
        from worlds.metroid_bread import DoorRandoAssigner

        key = ("s040_aqua", "doorpowerpower_013")
        groups = {
            key: [
                (
                    ("Burenia", "Main Hub Tower Middle", "Door to Energy Recharge South"),
                    {"incompatible_dock_weaknesses": ["Grapple Beam Door"]},
                ),
                (
                    ("Burenia", "Energy Recharge South", "Door to Main Hub Tower Middle"),
                    {"incompatible_dock_weaknesses": ["Grapple Beam Door"]},
                ),
            ]
        }
        bans = DoorRandoAssigner.incompatible_weaknesses_for_key(groups, key)
        self.assertIn("Grapple Beam Door", bans)
        self.assertEqual(DoorRando.incompatible_weaknesses_for_key(groups, key), bans)

        logic = MagicMock()
        logic.parser._get_dock_weakness_requirement = MagicMock(
            return_value={"type": "trivial"}
        )
        logic.evaluate_requirement = MagicMock(return_value=True)
        pool = [
            "Grapple Beam Door",
            "Missile Door",
            "Power Beam Door",
        ]
        allowed = DoorRandoAssigner.filter_targets_for_door(
            pool,
            key=key,
            groups=groups,
            inventory=frozenset({"Missile", "Grapple Beam"}),
            logic=logic,
            shield_used=defaultdict(int),
        )
        self.assertNotIn("Grapple Beam Door", allowed)
        self.assertIn("Missile Door", allowed)

    def test_assignments_never_emit_phantom_cloak(self):
        from worlds.metroid_bread import DoorRando

        patches = DoorRando.assignments_to_door_patches({
            ("s010_cave", "doorpowerpower_000"): "Sensor Lock Door",
            ("s010_cave", "doorpowerpower_001"): "Phase Shift Door",
            ("s010_cave", "doorpowerpower_002"): "Missile Door",
            ("s020_magma", "doorshutter_001"): "Missile Door",
        })
        types = {p["door_type"] for p in patches}
        actors = {p["actor"]["actor"] for p in patches}
        self.assertNotIn("phantom_cloak", types)
        self.assertNotIn("phase_shift", types)
        self.assertEqual(types, {"missile"})
        self.assertNotIn("doorshutter_001", actors)
        self.assertEqual(actors, {"doorpowerpower_002"})

    def test_shutters_excluded_from_collect_and_emit(self):
        from worlds.metroid_bread import DoorRando
        from worlds.metroid_bread import door_rando_db as db
        from worlds.metroid_bread.logic_parser import RandovaniaLogicParser

        self.assertFalse(
            db.is_odr_patchable_door_actor(
                "doorshutter_001",
                "actordef:actors/props/doorshutter/charclasses/doorshutter.bmsad",
            )
        )
        self.assertFalse(
            db.is_odr_patchable_door_actor(
                "doorheat_004",
                "actordef:actors/props/doorheat/charclasses/doorheat.bmsad",
            )
        )
        self.assertTrue(db.is_odr_patchable_door_actor("doorpowerpower_000"))

        shutter_node = {
            "default_dock_weakness": "Phase Shift Door",
            "extra": {
                "actor_name": "doorshutter_001",
                "actor_def": (
                    "actordef:actors/props/doorshutter/charclasses/doorshutter.bmsad"
                ),
            },
        }
        self.assertIsNone(
            DoorRando.physical_key_for_node("Cataris", shutter_node)
        )

        parser = RandovaniaLogicParser()
        parser.load_database()
        groups = DoorRando.collect_physical_doors(parser)
        shutter_keys = [k for k in groups if "shutter" in k[1].lower()]
        heat_keys = [k for k in groups if "heat" in k[1].lower()]
        self.assertEqual(shutter_keys, [])
        self.assertEqual(heat_keys, [])
        self.assertNotIn(("s020_magma", "doorshutter_001"), groups)

    def test_ap_to_patcher_refuses_phantom_cloak(self):
        import ap_to_patcher as ap

        patcher = {"door_patches": [], "objective": {}, "starting_items": {}}
        with self.assertRaises(ValueError) as ctx:
            ap.apply_dread_patch_extras(
                patcher,
                {
                    "door_patches": [
                        {
                            "actor": {
                                "scenario": "s010_cave",
                                "actor": "doorpowerpower_000",
                            },
                            "door_type": "phantom_cloak",
                        }
                    ]
                },
                our_player="Samus",
            )
        self.assertIn("phantom_cloak", str(ctx.exception))

    def test_ap_to_patcher_drops_shutter_actors(self):
        import ap_to_patcher as ap

        patcher = {"door_patches": [], "objective": {}, "starting_items": {}}
        ap.apply_dread_patch_extras(
            patcher,
            {
                "door_patches": [
                    {
                        "actor": {
                            "scenario": "s020_magma",
                            "actor": "doorshutter_001",
                        },
                        "door_type": "missile",
                    },
                    {
                        "actor": {
                            "scenario": "s010_cave",
                            "actor": "doorpowerpower_000",
                        },
                        "door_type": "missile",
                    },
                ]
            },
            our_player="Samus",
        )
        actors = {p["actor"]["actor"] for p in patcher["door_patches"]}
        self.assertNotIn("doorshutter_001", actors)
        self.assertEqual(actors, {"doorpowerpower_000"})


class TestReachFilterAndProportion(unittest.TestCase):
    def test_reach_filter_rejects_unopenable_lock(self):
        from worlds.metroid_bread import DoorRandoAssigner

        key = ("s010_cave", "doorpowerpower_000")
        groups = {
            key: [
                (
                    ("Artaria", "Area", "Door A"),
                    {"incompatible_dock_weaknesses": []},
                ),
            ]
        }

        def eval_req(req, inventory):
            # Simulate Plasma door needing Plasma Beam.
            if req and req.get("_need") == "Plasma Beam":
                return "Plasma Beam" in inventory
            return True

        logic = MagicMock()
        logic.parser._get_dock_weakness_requirement = MagicMock(
            side_effect=lambda w: (
                {"type": "resource", "_need": "Plasma Beam"}
                if w == "Plasma Beam Door"
                else {"type": "trivial"}
            )
        )
        logic.evaluate_requirement = MagicMock(side_effect=eval_req)

        pool = ["Plasma Beam Door", "Power Beam Door", "Missile Door"]
        without_plasma = DoorRandoAssigner.filter_targets_for_door(
            pool,
            key=key,
            groups=groups,
            inventory=frozenset({"Missile"}),
            logic=logic,
            shield_used=defaultdict(int),
        )
        self.assertNotIn("Plasma Beam Door", without_plasma)
        self.assertIn("Power Beam Door", without_plasma)

        with_plasma = DoorRandoAssigner.filter_targets_for_door(
            pool,
            key=key,
            groups=groups,
            inventory=frozenset({"Missile", "Plasma Beam"}),
            logic=logic,
            shield_used=defaultdict(int),
        )
        self.assertIn("Plasma Beam Door", with_plasma)

    def test_proportion_roughly_honored(self):
        from worlds.metroid_bread import DoorRandoAssigner

        eligible = [(f"s010_cave", f"door_{i}") for i in range(100)]
        rng = random.Random(0)
        shuffled = DoorRandoAssigner.select_shuffled_keys(
            eligible, rng, proportion=0.6
        )
        self.assertEqual(len(shuffled), 60)
        # Distinct subset of eligible.
        self.assertEqual(len(set(shuffled)), 60)
        self.assertTrue(set(shuffled).issubset(set(eligible)))

    def test_pre_fill_unlocks_to_power_beam(self):
        from worlds.metroid_bread import DoorRandoAssigner
        from worlds.metroid_bread import door_rando_db as db

        keys = [("s010_cave", "doorpowerpower_000"), ("s020_magma", "door_x")]
        assignments = DoorRandoAssigner.pre_fill_unlock_assignments(keys)
        unlocked = db.unlocked_weakness()
        self.assertEqual(set(assignments.values()), {unlocked})
        self.assertEqual(len(assignments), 2)


class TestDoorAssignerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from worlds.AutoWorld import AutoWorldRegister, call_all
        from Fill import distribute_items_restrictive
        from test.general import gen_steps, setup_multiworld

        cls.ap = {
            "call_all": call_all,
            "distribute_items_restrictive": distribute_items_restrictive,
            "gen_steps": gen_steps,
            "setup_multiworld": setup_multiworld,
            "world_type": AutoWorldRegister.world_types["Metroid Bread"],
        }

    def test_individual_doors_pre_then_post_fill(self):
        ap = self.ap
        mw = ap["setup_multiworld"](
            ap["world_type"],
            steps=ap["gen_steps"],
            seed=42,
            options={
                "door_lock_rando": "individual_doors",
                "required_dna": 0,
                "accessibility": "minimal",
                "starting_location": "default",
            },
        )
        world = mw.worlds[1]
        if not world.door_shuffled_keys:
            self.skipTest("seed selected no shuffled doors")
        # Pre-fill: shuffled docks are unlocked.
        from worlds.metroid_bread import door_rando_db as db

        unlocked = db.unlocked_weakness()
        for key in world.door_shuffled_keys:
            self.assertEqual(world.door_assignments[key], unlocked)

        eligible_n = len(DoorRandoAssigner_eligible(world))
        # Roughly honor proportion (allow wide band for frontier filtering).
        if eligible_n >= 10:
            ratio = len(world.door_shuffled_keys) / eligible_n
            self.assertGreaterEqual(ratio, 0.4)
            self.assertLessEqual(ratio, 0.8)

        ap["distribute_items_restrictive"](mw)
        ap["call_all"](mw, "post_fill")

        from worlds.metroid_bread import DoorRando
        from worlds.metroid_bread.DoorRando import (
            ODR_CANNOT_ADD_DOOR_TYPES,
            WEAKNESS_DOOR_TYPE,
        )

        for weakness in world.door_assignments.values():
            dt = WEAKNESS_DOOR_TYPE.get(weakness)
            self.assertIsNotNone(dt)
            self.assertNotIn(dt, ODR_CANNOT_ADD_DOOR_TYPES)
        self.assertEqual(len(world.door_patches), len(world.door_assignments))
        for patch in world.door_patches:
            self.assertNotIn(patch["door_type"], ("phantom_cloak", "phase_shift"))
            actor = patch["actor"]["actor"]
            self.assertFalse(
                actor.lower().startswith("doorshutter"),
                f"shutter leaked into door_patches: {patch}",
            )
            self.assertNotEqual(
                (patch["actor"]["scenario"], actor),
                ("s020_magma", "doorshutter_001"),
            )

        from worlds.metroid_bread import DoorRandoAssigner as DRA
        from worlds.metroid_bread import StartKit

        eligible = DRA.eligible_physical_keys(
            world.logic,
            doors_to_change=world.options.doors_to_change.value,
            start_counts=StartKit.kit_counts(world.start_kit),
        )
        self.assertNotIn(("s020_magma", "doorshutter_001"), eligible)
        self.assertFalse(any("shutter" in k[1].lower() for k in eligible))
        collected = DoorRando.collect_physical_doors(world.logic.parser)
        self.assertNotIn(("s020_magma", "doorshutter_001"), collected)


def DoorRandoAssigner_eligible(world):
    from worlds.metroid_bread import DoorRandoAssigner
    from worlds.metroid_bread import StartKit

    return DoorRandoAssigner.eligible_physical_keys(
        world.logic,
        doors_to_change=world.options.doors_to_change.value,
        start_counts=StartKit.kit_counts(world.start_kit),
    )


if __name__ == "__main__":
    unittest.main()

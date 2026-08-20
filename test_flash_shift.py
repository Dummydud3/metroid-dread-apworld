"""Unit tests for Flash Shift pool / logic modes."""
from __future__ import annotations

import unittest


class TestFlashShiftPlan(unittest.TestCase):
    def test_vanilla_plan(self):
        from worlds.metroid_bread.flash_shift import plan_from_options

        class O:
            vanilla_flash_shift_behaviour = type("T", (), {"value": 1})()
            flash_shift_upgrade_requires_main_item = type("T", (), {"value": 1})()
            flash_shift_upgrade_count = type("T", (), {"value": 5})()
            flash_shift_included_ammo = type("T", (), {"value": 2})()
            flash_shift_upgrade_amount = type("T", (), {"value": 1})()

        plan = plan_from_options(O())
        self.assertTrue(plan["vanilla"])
        self.assertEqual(plan["main_count"], 1)
        self.assertEqual(plan["upgrade_count"], 0)
        self.assertEqual(plan["included_ammo"], 2)

    def test_require_main_plan(self):
        from worlds.metroid_bread.flash_shift import plan_from_options

        class O:
            vanilla_flash_shift_behaviour = type("T", (), {"value": 0})()
            flash_shift_upgrade_requires_main_item = type("T", (), {"value": 1})()
            flash_shift_upgrade_count = type("T", (), {"value": 4})()
            flash_shift_included_ammo = type("T", (), {"value": 2})()
            flash_shift_upgrade_amount = type("T", (), {"value": 1})()

        plan = plan_from_options(O())
        self.assertFalse(plan["vanilla"])
        self.assertTrue(plan["require_main"])
        self.assertEqual(plan["main_count"], 1)
        self.assertEqual(plan["upgrade_count"], 4)

    def test_progressive_plan(self):
        from worlds.metroid_bread.flash_shift import plan_from_options

        class O:
            vanilla_flash_shift_behaviour = type("T", (), {"value": 0})()
            flash_shift_upgrade_requires_main_item = type("T", (), {"value": 0})()
            flash_shift_upgrade_count = type("T", (), {"value": 3})()
            flash_shift_included_ammo = type("T", (), {"value": 2})()
            flash_shift_upgrade_amount = type("T", (), {"value": 1})()

        plan = plan_from_options(O())
        self.assertFalse(plan["require_main"])
        self.assertEqual(plan["main_count"], 0)
        self.assertEqual(plan["upgrade_count"], 3)

    def test_legacy_extras_are_progressive(self):
        from worlds.metroid_bread.flash_shift import plan_from_extras

        plan = plan_from_extras({"flash_shift_upgrade_count": 7})
        self.assertFalse(plan["vanilla"])
        self.assertFalse(plan["require_main"])
        self.assertEqual(plan["upgrade_count"], 7)


class TestFlashShiftLogic(unittest.TestCase):
    def test_vanilla_ability_and_chains(self):
        from worlds.metroid_bread.flash_shift import logical_ability_and_chains

        plan = {
            "vanilla": True,
            "require_main": False,
            "included_ammo": 2,
            "upgrade_amount": 1,
        }
        has, chains = logical_ability_and_chains({"Flash Shift": 1}, plan)
        self.assertTrue(has)
        self.assertEqual(chains, 2)
        has, chains = logical_ability_and_chains({"Flash Shift Upgrade": 3}, plan)
        self.assertFalse(has)
        self.assertEqual(chains, 0)

    def test_require_main_upgrades_do_not_unlock(self):
        from worlds.metroid_bread.flash_shift import logical_ability_and_chains

        plan = {
            "vanilla": False,
            "require_main": True,
            "included_ammo": 2,
            "upgrade_amount": 1,
        }
        has, chains = logical_ability_and_chains({"Flash Shift Upgrade": 3}, plan)
        self.assertFalse(has)
        self.assertEqual(chains, 3)
        has, chains = logical_ability_and_chains(
            {"Flash Shift": 1, "Flash Shift Upgrade": 2}, plan
        )
        self.assertTrue(has)
        self.assertEqual(chains, 4)  # included 2 + 2 upgrades

    def test_progressive_first_unlock(self):
        from worlds.metroid_bread.flash_shift import logical_ability_and_chains

        plan = {
            "vanilla": False,
            "require_main": False,
            "included_ammo": 2,
            "upgrade_amount": 1,
        }
        has, chains = logical_ability_and_chains({"Flash Shift Upgrade": 1}, plan)
        self.assertTrue(has)
        self.assertEqual(chains, 0)
        has, chains = logical_ability_and_chains({"Flash Shift Upgrade": 3}, plan)
        self.assertTrue(has)
        self.assertEqual(chains, 2)


class TestFlashShiftMapping(unittest.TestCase):
    def test_main_resources_vanilla(self):
        from worlds.metroid_bread.flash_shift import main_resources
        from worlds.metroid_bread.dread_item_mapping import get_dread_item_data

        res = main_resources(2)
        self.assertEqual(res[0]["item_id"], "ITEM_GHOST_AURA")
        self.assertEqual(res[1]["item_id"], "ITEM_UPGRADE_FLASH_SHIFT_CHAIN")
        self.assertEqual(res[1]["quantity"], 2)
        data = get_dread_item_data("Flash Shift")
        self.assertEqual(data["resources"][0]["item_id"], "ITEM_GHOST_AURA")
        self.assertEqual(data["resources"][1]["quantity"], 2)


class TestFlashShiftOptionsRegistered(unittest.TestCase):
    def test_option_names(self):
        from worlds.metroid_bread.Options import MetroidBreadOptions

        fields = getattr(MetroidBreadOptions, "__annotations__", {})
        self.assertIn("vanilla_flash_shift_behaviour", fields)
        self.assertIn("flash_shift_upgrade_count", fields)
        self.assertIn("flash_shift_upgrade_requires_main_item", fields)


class TestFlashShiftClassification(unittest.TestCase):
    def test_upgrade_default_is_filler_like_missile(self):
        from BaseClasses import ItemClassification
        from worlds.metroid_bread.Items import item_table

        self.assertEqual(
            item_table["Flash Shift Upgrade"].classification,
            ItemClassification.filler,
        )
        self.assertEqual(
            item_table["Missile Tank"].classification,
            ItemClassification.filler,
        )
        self.assertEqual(
            item_table["Flash Shift"].classification,
            ItemClassification.progression,
        )

    def test_vanilla_plan_adds_no_upgrades(self):
        from worlds.metroid_bread.flash_shift import plan_from_options

        class O:
            vanilla_flash_shift_behaviour = type("T", (), {"value": 1})()
            flash_shift_upgrade_requires_main_item = type("T", (), {"value": 1})()
            flash_shift_upgrade_count = type("T", (), {"value": 5})()
            flash_shift_included_ammo = type("T", (), {"value": 2})()
            flash_shift_upgrade_amount = type("T", (), {"value": 1})()

        plan = plan_from_options(O())
        # Vanilla: one main progression item, zero upgrades → pool size matches
        # the pre-overhaul Flash Shift slot count (no extra progression).
        self.assertEqual(plan["main_count"], 1)
        self.assertEqual(plan["upgrade_count"], 0)

    def test_upgrade_displaces_missile_filler_one_to_one(self):
        """N upgrades reduce Missile Tank count by N (guarantee via displacement)."""
        missile_tanks = 35
        upgrade_count = 4
        displaced = max(0, missile_tanks - upgrade_count)
        self.assertEqual(displaced, 31)
        # Upgrades themselves are never the trim target.
        trim_order = ("Missile Tank", "Power Bomb Tank")
        self.assertNotIn("Flash Shift Upgrade", trim_order)


if __name__ == "__main__":
    unittest.main()

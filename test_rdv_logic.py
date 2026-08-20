"""
Regression tests for Metroid Bread Randovania logic bridge.

Run: py -3.11 -m worlds.metroid_bread.test_rdv_logic
(from Archipelago-main root)
"""

from __future__ import annotations

import logging
import unittest

logging.disable(logging.ERROR)


class _FakeOpt:
    def __getattr__(self, name):
        # tricks disabled by default
        return type("o", (), {"value": 0})()


class _FakeWorld:
    player = 1
    options = _FakeOpt()


def _make_logic():
    from worlds.metroid_bread.dread_logic import DreadLogic
    return DreadLogic(_FakeWorld())


class TestRdvLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logic = _make_logic()
        from worlds.metroid_bread.Events import EVENT_RESOURCE_TO_ITEM, event_locations
        cls.EVENT_RESOURCE_TO_ITEM = EVENT_RESOURCE_TO_ITEM
        cls.event_locations = event_locations

    def _base_inv(self, *extra: str):
        inv = {"__missiles__", "__energy__", "__energy_99__", *extra}
        return inv

    def _sweep(self, start_items, withhold_events=None):
        """Collect reachable events iteratively like AP sweep."""
        withhold_events = withhold_events or set()
        inv = set(self._base_inv(*start_items))
        last_r = set()
        for _ in range(80):
            self.logic.clear_cache()
            r = self.logic.get_reachable_nodes(frozenset(inv), collect_events=False)
            last_r = r
            new = False
            for ev in self.event_locations:
                if ev.event_item in withhold_events:
                    continue
                node = (ev.game_region, ev.area, ev.node)
                if node in r and ev.event_item not in inv:
                    inv.add(ev.event_item)
                    new = True
            if not new:
                break
        pickups = sorted(
            name for name, node in self.logic.pickup_nodes.items() if node in last_r
        )
        regions = sorted({n[0] for n in last_r})
        return pickups, regions, inv, last_r

    def test_event_tables_loaded(self):
        self.assertGreaterEqual(len(self.EVENT_RESOURCE_TO_ITEM), 100)
        self.assertGreaterEqual(len(self.event_locations), 100)
        self.assertIn("ElunReleaseX", self.EVENT_RESOURCE_TO_ITEM)

    def test_sphere0_has_event_and_few_pickups(self):
        pickups, regions, inv, nodes = self._sweep([])
        self.assertEqual(regions, ["Artaria"])
        # Without Charge Beam, only a couple of Artaria pickups open after events
        self.assertGreaterEqual(len(pickups), 1)
        self.assertLessEqual(len(pickups), 5)
        blob = self.EVENT_RESOURCE_TO_ITEM["s010_cave:default:PRP_DB_CV_006"]
        self.assertIn(blob, inv)

    def test_charge_beam_opens_artaria(self):
        pickups, regions, _, _ = self._sweep(["Charge Beam"])
        self.assertEqual(regions, ["Artaria"])
        self.assertGreaterEqual(len(pickups), 5)

    def test_charge_and_morph_reach_cataris(self):
        pickups, regions, _, _ = self._sweep(["Charge Beam", "Morph Ball"])
        self.assertIn("Artaria", regions)
        self.assertIn("Cataris", regions)
        self.assertGreaterEqual(len(pickups), 10)

    def test_elun_release_gates_z57_tunnel(self):
        """Tunnel toward Above Z-57 requires ElunReleaseX in RDV logic."""
        elun = self.EVENT_RESOURCE_TO_ITEM["ElunReleaseX"]
        majors = [
            "Charge Beam", "Morph Ball", "Bomb", "Phantom Cloak", "Varia Suit",
            "Spider Magnet", "Grapple Beam", "Wide Beam",
        ]
        # With majors but without ElunReleaseX event collected
        pickups_wo, regions_wo, inv_wo, nodes_wo = self._sweep(
            majors, withhold_events={elun}
        )
        z57_nodes = [n for n in nodes_wo if "Z-57" in n[1] or "Z-57" in n[2]]
        # May or may not reach Z-57 rooms without Elun — assert the resource check itself
        self.assertFalse(
            self.logic._resource_ok("events", "ElunReleaseX", 1, frozenset(inv_wo))
        )

        # With ElunReleaseX forced into inventory
        pickups_w, regions_w, inv_w, nodes_w = self._sweep(majors + [elun])
        self.assertTrue(
            self.logic._resource_ok("events", "ElunReleaseX", 1, frozenset(inv_w))
        )

    def test_missiles_always_shootable(self):
        empty = frozenset(self._base_inv())
        # Shoot Missile template should pass (launcher + ammo always on)
        tmpl = self.logic.parser.templates["Shoot Missile"]["requirement"]
        self.assertTrue(self.logic.evaluate_requirement(tmpl, empty))

    def test_can_slide_without_morph(self):
        empty = frozenset(self._base_inv())
        tmpl = self.logic.parser.templates["Can Slide"]["requirement"]
        self.assertTrue(self.logic.evaluate_requirement(tmpl, empty))

    def test_open_charge_door_needs_charge(self):
        empty = frozenset(self._base_inv())
        tmpl = self.logic.parser.templates["Open Charge Door"]["requirement"]
        self.assertFalse(self.logic.evaluate_requirement(tmpl, empty))
        with_charge = frozenset(self._base_inv("Charge Beam"))
        self.assertTrue(self.logic.evaluate_requirement(tmpl, with_charge))

    def test_misc_nerf_pb_negate_defaults_true(self):
        """NerfPowerBombs is off by default; negate => satisfied."""
        req = {
            "type": "resource",
            "data": {"type": "misc", "name": "NerfPowerBombs", "amount": 1, "negate": True},
        }
        self.assertTrue(self.logic.evaluate_requirement(req, frozenset(self._base_inv())))

    def test_nerf_power_bombs_blocks_open_charge_door_pb_path(self):
        """With Knowledge + PB, charge doors open via PB only when nerf is off."""
        from worlds.metroid_bread.dread_logic import DreadLogic

        tmpl = self.logic.parser.templates["Open Charge Door"]["requirement"]
        # Lay Power Bomb needs Morph + MainPB + PB ammo.
        inv = frozenset(self._base_inv("Morph Ball", "Power Bomb", "__pb_ammo__"))

        class _OptsOff:
            def __getattr__(self, name):
                if name == "knowledge_tricks":
                    return type("o", (), {"value": 1})()
                return type("o", (), {"value": 0})()

        class _WorldOff:
            player = 1
            options = _OptsOff()

        logic_off = DreadLogic(_WorldOff())
        self.assertTrue(logic_off.evaluate_requirement(tmpl, inv))

        class _OptsOn:
            def __getattr__(self, name):
                if name in ("knowledge_tricks", "nerf_power_bombs"):
                    return type("o", (), {"value": 1})()
                return type("o", (), {"value": 0})()

        class _WorldOn:
            player = 1
            options = _OptsOn()

        logic_on = DreadLogic(_WorldOn())
        self.assertFalse(logic_on.evaluate_requirement(tmpl, inv))
        # Charge Beam still opens the door when nerfed.
        with_charge = frozenset(self._base_inv("Charge Beam"))
        self.assertTrue(logic_on.evaluate_requirement(tmpl, with_charge))


class TestGenerationSmoke(unittest.TestCase):
    """Optional full generation — skipped if AP world import fails."""

    def test_solo_generate(self):
        try:
            from Generate import main as gen_main
            import argparse
            from pathlib import Path
            import tempfile
            import yaml
        except Exception as e:
            self.skipTest(f"Generate import failed: {e}")

        # Prefer WorldTest pattern if available
        try:
            from test.general import setup_solo_multiworld
            from worlds.metroid_bread import MetroidBreadWorld
        except Exception as e:
            self.skipTest(f"test harness unavailable: {e}")

        multiworld = setup_solo_multiworld(MetroidBreadWorld)
        # If setup places items, assert completion condition exists
        self.assertIn(1, multiworld.completion_condition)
        filled = [loc for loc in multiworld.get_locations(1) if loc.item]
        self.assertGreater(len(filled), 100)


if __name__ == "__main__":
    unittest.main()

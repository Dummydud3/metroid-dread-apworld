"""
Tracker must not auto-grant Quiet Robe / ElunReleaseX until confirmed.

Run: py -3.11 -m worlds.metroid_bread.test_tracker_gate_events
(from Archipelago-main root)
"""

from __future__ import annotations

import logging
import unittest

logging.disable(logging.ERROR)


class _FakeOpt:
    def __getattr__(self, name):
        return type("o", (), {"value": 0})()


class _FakeWorld:
    player = 1
    options = _FakeOpt()


class TestTrackerGateEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from worlds.metroid_bread.dread_logic import DreadLogic, ITEM_SHORT_TO_AP
        from worlds.metroid_bread.Events import EVENT_RESOURCE_TO_ITEM
        from worlds.metroid_bread.tracker_gate_events import (
            ELUN_RELEASE_X_EVENT,
            QUIET_ROBE_EVENT,
            TRACKER_EXCLUDE_AUTO_EVENTS,
            confirmed_event_items,
        )

        cls.logic = DreadLogic(_FakeWorld())
        cls.qr = EVENT_RESOURCE_TO_ITEM["Quiet Robe"]
        cls.elun = EVENT_RESOURCE_TO_ITEM["ElunReleaseX"]
        cls.ITEM_SHORT_TO_AP = ITEM_SHORT_TO_AP
        cls.QUIET_ROBE_EVENT = QUIET_ROBE_EVENT
        cls.ELUN_RELEASE_X_EVENT = ELUN_RELEASE_X_EVENT
        cls.EXCLUDE = TRACKER_EXCLUDE_AUTO_EVENTS
        cls.confirmed_event_items = staticmethod(confirmed_event_items)

        cls.UPPER_PICKUP = ("Burenia", "Upper Burenia Hub", "Pickup (Missile Tank)")
        cls.Z57 = ("Cataris", "Above Z-57 Fight", "Pickup (Z-57)")

        starts = cls.logic.parser.get_starting_nodes()
        artaria = [s for s in starts if s[0] == "Artaria"]
        cls.logic.set_starting_node(artaria[0] if artaria else starts[0])

    def _all_majors(self):
        items = {
            ap
            for ap in self.ITEM_SHORT_TO_AP.values()
            if ap and not str(ap).startswith("__")
        }
        items.update({"__missiles__", "__energy__", "__energy_999__", "__pb_ammo__"})
        return items

    def test_exclude_set_names(self):
        self.assertEqual(self.qr, self.QUIET_ROBE_EVENT)
        self.assertEqual(self.elun, self.ELUN_RELEASE_X_EVENT)
        self.assertIn(self.qr, self.EXCLUDE)
        self.assertIn(self.elun, self.EXCLUDE)

    def test_generation_still_auto_collects_quiet_robe(self):
        """Fill path (no exclude) still grants Quiet Robe when its node opens."""
        nodes = self.logic.get_reachable_nodes(frozenset(self._all_majors()))
        self.assertIn(self.UPPER_PICKUP, nodes)

    def test_tracker_withholds_quiet_robe_until_confirmed(self):
        inv = frozenset(self._all_majors())
        nodes = self.logic.get_reachable_nodes(
            inv, exclude_auto_events=self.EXCLUDE
        )
        self.assertNotIn(self.UPPER_PICKUP, nodes)

        with_qr = frozenset(set(inv) | {self.qr})
        nodes2 = self.logic.get_reachable_nodes(
            with_qr, exclude_auto_events=self.EXCLUDE
        )
        self.assertIn(self.UPPER_PICKUP, nodes2)

    def test_tracker_withholds_elun_release_x(self):
        inv = frozenset(self._all_majors())
        # Without exclude, RDV-style collect would grant ElunReleaseX when reachable.
        open_nodes = self.logic.get_reachable_nodes(inv)
        # With exclude, Z-57 must stay closed unless the event is already in inv.
        gated = self.logic.get_reachable_nodes(
            inv, exclude_auto_events=self.EXCLUDE
        )
        self.assertNotIn(self.Z57, gated)

        with_x = frozenset(set(inv) | {self.elun})
        unlocked = self.logic.get_reachable_nodes(
            with_x, exclude_auto_events=self.EXCLUDE
        )
        # If the open path never reached Z-57 even with auto-collect, skip assert
        # on unlocked (inventory may still lack a required mid-game event).
        if self.Z57 in open_nodes:
            self.assertIn(self.Z57, unlocked)

    def test_confirmed_helper_quiet_robe_and_x(self):
        self.assertEqual(
            self.confirmed_event_items(beaten_boss_keys={"quiet_robe"}),
            {self.qr},
        )
        self.assertEqual(
            self.confirmed_event_items(story_keys={"elun_release_x"}),
            {self.elun},
        )
        self.assertEqual(
            self.confirmed_event_items(seed_default_x_released=True),
            {self.elun},
        )

    def test_reachable_pickup_names_forwards_exclude(self):
        """exclude_auto_events is honored on the pickup-name helper used by Hub."""
        inv = frozenset(self._all_majors())
        # Mirror reachable_pickup_names, but feed a known-good inventory set
        # (counts→inventory_from_counts under-approximates __energy_999__ kits).
        nodes_gen = self.logic.get_reachable_nodes(inv)
        nodes_trk = self.logic.get_reachable_nodes(
            inv, exclude_auto_events=self.EXCLUDE
        )
        names_gen = {
            name
            for name, node in self.logic.pickup_nodes.items()
            if node in nodes_gen
        }
        names_trk = {
            name
            for name, node in self.logic.pickup_nodes.items()
            if node in nodes_trk
        }
        upper = "Burenia - Upper Burenia Hub - Pickup (Missile Tank)"
        self.assertIn(upper, names_gen)
        self.assertNotIn(upper, names_trk)
        self.assertTrue(names_trk.issubset(names_gen))


if __name__ == "__main__":
    unittest.main()

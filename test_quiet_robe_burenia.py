"""
Quiet Robe gates the locked Upper Burenia Hub section (blue gate).

Run: py -3.11 -m worlds.metroid_bread.test_quiet_robe_burenia
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


class TestQuietRobeUpperBureniaHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from worlds.metroid_bread.dread_logic import DreadLogic, ITEM_SHORT_TO_AP
        from worlds.metroid_bread.Events import EVENT_RESOURCE_TO_ITEM, event_locations

        cls.logic = DreadLogic(_FakeWorld())
        cls.qr = EVENT_RESOURCE_TO_ITEM["Quiet Robe"]
        cls.event_locations = event_locations
        cls.ITEM_SHORT_TO_AP = ITEM_SHORT_TO_AP

        cls.PICKUP = ("Burenia", "Upper Burenia Hub", "Pickup (Missile Tank)")
        cls.MAP_DOOR = ("Burenia", "Upper Burenia Hub", "Door to Map Station")
        cls.TUNNEL = ("Burenia", "Upper Burenia Hub", "Tunnel to Transport to Ghavoran")
        cls.NAV = ("Burenia", "Upper Burenia Hub", "Door to Navigation Station North")
        cls.START = ("Burenia", "Upper Burenia Hub", "Start Point")
        cls.QR_NODE = ("Ferenia", "Quiet Robe Room", "Event - Quiet Robe")

    def _all_majors(self):
        items = {
            ap for ap in self.ITEM_SHORT_TO_AP.values()
            if ap and not str(ap).startswith("__")
        }
        items.update({"__missiles__", "__energy__", "__energy_999__", "__pb_ammo__"})
        return items

    def _sweep(self, start_items, withhold=None):
        withhold = withhold or set()
        inv = set(start_items)
        nodes = set()
        for _ in range(120):
            self.logic.clear_cache()
            nodes = self.logic.get_reachable_nodes(frozenset(inv), collect_events=False)
            gained = False
            for ev in self.event_locations:
                if ev.event_item in withhold:
                    continue
                node = (ev.game_region, ev.area, ev.node)
                if node in nodes and ev.event_item not in inv:
                    inv.add(ev.event_item)
                    gained = True
            if not gained:
                break
        return nodes, inv

    def test_lower_hub_reachable_without_quiet_robe(self):
        """Blue-gate lower side stays open; locked upper nodes stay closed."""
        self.logic.set_starting_node(self.START)
        nodes, _ = self._sweep(
            {"__missiles__", "__energy__", "__energy_99__", "Morph Ball"},
            withhold={self.qr},
        )
        self.assertIn(self.START, nodes)
        self.assertIn(self.NAV, nodes)
        self.assertNotIn(self.MAP_DOOR, nodes)
        self.assertNotIn(self.TUNNEL, nodes)
        self.assertNotIn(self.PICKUP, nodes)

    def test_quiet_robe_opens_locked_upper_hub(self):
        self.logic.set_starting_node(self.START)
        nodes, inv = self._sweep(
            {"__missiles__", "__energy__", "__energy_99__", "Morph Ball", self.qr},
            withhold={self.qr},
        )
        self.assertIn(self.qr, inv)
        self.assertIn(self.MAP_DOOR, nodes)
        self.assertIn(self.TUNNEL, nodes)
        self.assertIn(self.PICKUP, nodes)

    def test_ghavoran_elevator_cannot_skip_quiet_robe(self):
        """Majors without Quiet Robe must not reach Upper Hub pickup via elevator."""
        # Reset start to Artaria intro
        starts = self.logic.parser.get_starting_nodes()
        artaria = [s for s in starts if s[0] == "Artaria"]
        self.logic.set_starting_node(artaria[0] if artaria else starts[0])

        nodes, inv = self._sweep(self._all_majors(), withhold={self.qr})
        self.assertNotIn(self.qr, inv)
        self.assertNotIn(self.PICKUP, nodes)
        self.assertNotIn(self.MAP_DOOR, nodes)
        self.assertNotIn(self.TUNNEL, nodes)

    def test_quiet_robe_reachable_without_upper_hub(self):
        """Softlock safety: Quiet Robe must not require the gated Upper Hub nodes."""
        starts = self.logic.parser.get_starting_nodes()
        artaria = [s for s in starts if s[0] == "Artaria"]
        self.logic.set_starting_node(artaria[0] if artaria else starts[0])

        nodes, _ = self._sweep(self._all_majors(), withhold={self.qr})
        self.assertIn(self.QR_NODE, nodes)
        self.assertNotIn(self.PICKUP, nodes)
        self.assertNotIn(self.TUNNEL, nodes)
        self.assertNotIn(self.MAP_DOOR, nodes)

    def test_with_quiet_robe_event_upper_hub_opens(self):
        starts = self.logic.parser.get_starting_nodes()
        artaria = [s for s in starts if s[0] == "Artaria"]
        self.logic.set_starting_node(artaria[0] if artaria else starts[0])

        nodes, _ = self._sweep(self._all_majors() | {self.qr})
        self.assertIn(self.PICKUP, nodes)
        self.assertIn(self.TUNNEL, nodes)
        self.assertIn(self.MAP_DOOR, nodes)


if __name__ == "__main__":
    unittest.main()

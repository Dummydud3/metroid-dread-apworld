"""Client tracker must apply transport rando to DreadLogic (not vanilla graph)."""

from __future__ import annotations

import contextlib
import io
import unittest
import warnings

warnings.filterwarnings("ignore")


class TestTrackerTransportLogic(unittest.TestCase):
    def test_transport_matching_rewrites_connections(self):
        from worlds.metroid_dread.dread_logic import DreadLogic
        from worlds.metroid_dread import TransportRando

        class _Opt:
            def __getattr__(self, name):
                return type("o", (), {"value": 0})()

        class _World:
            player = 1
            options = _Opt()

        with contextlib.redirect_stdout(io.StringIO()):
            shuffled = DreadLogic(_World())

        transports = TransportRando.collect_transports(shuffled.parser)
        elev = [sid for sid, m in transports.items() if m["type"] == "elevator"]
        elev.sort()
        if len(elev) < 4:
            self.skipTest("not enough elevators to shuffle")

        matching = {
            elev[0]: elev[2],
            elev[2]: elev[0],
            elev[1]: elev[3],
            elev[3]: elev[1],
        }
        src_meta = transports[elev[0]]
        vanilla_dest = (src_meta["node"].get("default_connection") or {}).get("region")
        n = TransportRando.apply_matching_from_slot_data(shuffled.parser, matching)
        self.assertGreater(n, 0)
        shuffled.rebuild_graph()

        dest_region = transports[elev[2]]["node_id"][0]
        conn = src_meta["node"].get("default_connection") or {}
        self.assertEqual(conn.get("region"), dest_region)
        self.assertNotEqual(dest_region, vanilla_dest)

    def test_slot_data_includes_transport_matching(self):
        from Fill import distribute_items_restrictive
        from test.general import gen_steps, setup_multiworld
        from worlds.AutoWorld import AutoWorldRegister

        world_type = AutoWorldRegister.world_types["Metroid Dread"]
        mw = setup_multiworld(
            world_type,
            steps=gen_steps,
            seed=42,
            options={"transport_rando": "randomized", "required_dna": 0},
        )
        distribute_items_restrictive(mw)
        world = mw.worlds[1]
        slot = world.fill_slot_data()
        extras = slot.get("patch_extras") or {}
        matching = extras.get("transport_matching") or {}
        if world.transport_matching:
            self.assertEqual(matching, dict(world.transport_matching))
            self.assertGreater(len(matching), 0)
        self.assertIn("door_assignments", extras)


if __name__ == "__main__":
    unittest.main()

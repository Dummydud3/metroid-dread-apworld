"""Client tracker must apply transport rando to DreadLogic (not vanilla graph)."""

from __future__ import annotations

import contextlib
import io
import unittest
import warnings

warnings.filterwarnings("ignore")


class TestTrackerTransportLogic(unittest.TestCase):
    def test_transport_matching_rewrites_connections(self):
        from worlds.metroid_bread.dread_logic import DreadLogic
        from worlds.metroid_bread import TransportRando

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

    def test_elevators_applied_even_when_door_patches_present(self):
        """Regression: door_patches must not skip elevator graph rewrite."""
        import json
        import re
        from pathlib import Path

        from worlds.metroid_bread.dread_logic import DreadLogic

        spoiler = Path(__file__).resolve().parents[2] / (
            "build/dread_dist/DreadClient_fresh/output/_patcher_extract/"
            "server_23206167140589219116/AP_orangeonionMD_server_Spoiler.txt"
        )
        if not spoiler.is_file():
            spoiler = Path(
                r"C:\Users\dummy\Downloads\Archipelago-main\Archipelago-main"
                r"\build\dread_dist\DreadClient_fresh\output\_patcher_extract"
                r"\server_23206167140589219116\AP_orangeonionMD_server_Spoiler.txt"
            )
        if not spoiler.is_file():
            self.skipTest("sample spoiler with elevators not present")

        text = spoiler.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"DREAD_PATCH_EXTRAS_JSON:[^:]+:(\{.*\})", text)
        self.assertIsNotNone(m)
        extras = json.loads(m.group(1))
        self.assertTrue(extras.get("elevators"))
        self.assertTrue(extras.get("door_patches"))
        self.assertFalse(extras.get("transport_matching"))

        # Mimic client apply order after the fix.
        class _Opt:
            def __getattr__(self, name):
                return type("o", (), {"value": 0})()

        class _World:
            player = 1
            options = _Opt()

        with contextlib.redirect_stdout(io.StringIO()):
            logic = DreadLogic(_World())

        from worlds.metroid_bread import DoorRando, TransportRando

        elev_n = 0
        transports = TransportRando.collect_transports(logic.parser)
        by_teleporter = {
            (m["scenario"], m["actor"]): m for m in transports.values()
        }
        by_arrival = {}
        for meta in transports.values():
            by_arrival[
                (meta["scenario"], meta.get("arrival_spawn") or meta["actor"])
            ] = meta
            by_arrival[(meta["scenario"], meta["actor"])] = meta
        for entry in extras["elevators"]:
            tele = entry.get("teleporter") or {}
            dest = entry.get("destination") or {}
            src = by_teleporter.get((tele.get("scenario"), tele.get("actor")))
            dest_meta = by_arrival.get((dest.get("scenario"), dest.get("actor")))
            if not src or not dest_meta:
                continue
            dr, da, dn = dest_meta["node_id"]
            src["node"]["default_connection"] = {
                "region": dr,
                "area": da,
                "node": dn,
            }
            elev_n += 1
        door_n = DoorRando.apply_assignments_from_slot_data(
            logic.parser, extras["door_patches"]
        )
        logic.rebuild_graph()
        self.assertGreater(elev_n, 0)
        self.assertGreater(door_n, 0)

        start = ("Hanubia", "Navigation Station", "Save Station")
        logic.set_starting_node(start)
        regions = {a[0] for a in logic.reachable_areas(
            {"Morph Ball": 1, "Bomb": 1, "Wave Beam": 1}
        )}
        # With this seed's elevators, Hanubia start reaches Burenia — not Ghavoran.
        self.assertIn("Hanubia", regions)
        self.assertIn("Burenia", regions)
        self.assertNotIn("Ghavoran", regions)

    def test_slot_data_includes_transport_matching(self):
        from Fill import distribute_items_restrictive
        from test.general import gen_steps, setup_multiworld
        from worlds.AutoWorld import AutoWorldRegister

        world_type = AutoWorldRegister.world_types["Metroid Bread"]
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

    def test_tracker_counts_include_starting_items_at_hanubia(self):
        """Start kit from patch_extras must seed tracker logic (not only items_received)."""
        import sys
        import types
        from unittest.mock import patch

        from dread_client_bridge import counts_from_starting_items
        from worlds.metroid_bread.dread_logic import DreadLogic

        # Same ODR ids as AP_23206167140589219116 start kit (Cross Bomb = LINE_BOMB).
        starting_items = {
            "ITEM_MORPH_BALL": 1,
            "ITEM_WEAPON_LINE_BOMB": 1,
            "ITEM_WEAPON_WAVE_BEAM": 1,
        }
        kit_counts = counts_from_starting_items(starting_items)
        self.assertGreaterEqual(kit_counts.get("Morph Ball", 0), 1)
        self.assertGreaterEqual(kit_counts.get("Wave Beam", 0), 1)
        self.assertGreaterEqual(kit_counts.get("Cross Bomb", 0), 1)

        class _Opt:
            def __getattr__(self, name):
                return type("o", (), {"value": 0})()

        class _World:
            player = 1
            options = _Opt()

        with contextlib.redirect_stdout(io.StringIO()):
            logic = DreadLogic(_World())
        logic.set_starting_node(("Hanubia", "Navigation Station", "Save Station"))
        self.assertEqual(logic.reachable_pickup_names({}), [])
        self.assertGreater(len(logic.reachable_pickup_names(kit_counts)), 0)

        # Exercise client merge: empty items_received + starting_items → kit present.
        if "CommonClient" not in sys.modules:
            common = types.ModuleType("CommonClient")

            class CommonContext:
                def __init__(self, *args, **kwargs):
                    pass

            class ClientCommandProcessor:
                pass

            common.CommonContext = CommonContext
            common.ClientCommandProcessor = ClientCommandProcessor
            common.get_base_parser = lambda *a, **k: None
            common.gui_enabled = False
            common.handle_url_arg = lambda *a, **k: None
            common.server_loop = lambda *a, **k: None
            sys.modules["CommonClient"] = common
        if "NetUtils" not in sys.modules:
            net = types.ModuleType("NetUtils")

            class ClientStatus:
                CLIENT_CONNECTED = 0
                CLIENT_PLAYING = 1
                CLIENT_GOAL = 2

            class NetworkItem:
                pass

            class JSONtoTextParser:
                color_codes = {}

                def __init__(self, *args, **kwargs):
                    pass

                def __call__(self, *args, **kwargs):
                    return ""

            net.ClientStatus = ClientStatus
            net.NetworkItem = NetworkItem
            net.JSONtoTextParser = JSONtoTextParser
            net.status_colors = {}
            sys.modules["NetUtils"] = net

        import MetroidBreadClient as mdc

        def _init(self, *args, **kwargs):
            self.items_received = []
            self.item_id_to_name = {}
            self._game_inventory_amounts = None
            self._patch_extras = {"starting_items": dict(starting_items)}
            self._slot_data = {}

        with patch.object(mdc.MetroidBreadContext, "__init__", _init):
            ctx = mdc.MetroidBreadContext.__new__(mdc.MetroidBreadContext)
            _init(ctx)

        counts = ctx._tracker_item_counts()
        self.assertGreaterEqual(counts.get("Morph Ball", 0), 1)
        self.assertGreaterEqual(counts.get("Wave Beam", 0), 1)
        self.assertGreaterEqual(counts.get("Cross Bomb", 0), 1)
        # max() merge: precollected Morph in items_received must not become 2.
        ctx.items_received = [types.SimpleNamespace(item=1)]
        ctx.item_id_to_name = {1: "Morph Ball"}
        counts2 = ctx._tracker_item_counts()
        self.assertEqual(counts2.get("Morph Ball"), 1)

    def test_expert_tricks_from_spoiler_reach_burenia_power_bomb(self):
        """Seed 232061… sphere-1 Burenia PB needs Expert tricks, not Disabled."""
        import json
        import re
        from pathlib import Path

        from dread_client_bridge import counts_from_starting_items
        from worlds.metroid_bread import DoorRando, TransportRando
        from worlds.metroid_bread.dread_logic import DreadLogic
        from worlds.metroid_bread.logic_options import (
            parse_logic_options_from_spoiler_text,
        )

        root = Path(__file__).resolve().parents[2]
        full_spoiler = (
            root / "output" / "AP_23206167140589219116" / "AP_23206167140589219116_Spoiler.txt"
        )
        server_spoiler = (
            root
            / "build"
            / "dread_dist"
            / "DreadClient_fresh"
            / "output"
            / "_patcher_extract"
            / "server_23206167140589219116"
            / "AP_orangeonionMD_server_Spoiler.txt"
        )
        if not full_spoiler.is_file() or not server_spoiler.is_file():
            self.skipTest("seed 232061 spoilers not present")

        logic_opts = parse_logic_options_from_spoiler_text(
            full_spoiler.read_text(encoding="utf-8")
        )
        self.assertEqual(logic_opts.get("knowledge_tricks"), 5)
        self.assertEqual(logic_opts.get("movement_tricks"), 5)

        text = server_spoiler.read_text(encoding="utf-8")
        m = re.search(r"DREAD_PATCH_EXTRAS_JSON:[^:]+:(\{.*\})", text)
        self.assertIsNotNone(m)
        extras = json.loads(m.group(1))
        counts = counts_from_starting_items(extras.get("starting_items") or {})

        class _Opt:
            def __getattr__(self, name):
                if name in logic_opts:
                    return type("o", (), {"value": int(logic_opts[name])})()
                return type("o", (), {"value": 0})()

        class _World:
            player = 1
            options = _Opt()

        with contextlib.redirect_stdout(io.StringIO()):
            logic = DreadLogic(_World())

        transports = TransportRando.collect_transports(logic.parser)
        by_teleporter = {
            (meta["scenario"], meta["actor"]): meta for meta in transports.values()
        }
        by_arrival = {}
        for meta in transports.values():
            by_arrival[(meta["scenario"], meta.get("arrival_spawn") or meta["actor"])] = meta
            by_arrival[(meta["scenario"], meta["actor"])] = meta
        for entry in extras.get("elevators") or []:
            tele = entry.get("teleporter") or {}
            dest = entry.get("destination") or {}
            src = by_teleporter.get((tele.get("scenario"), tele.get("actor")))
            dest_meta = by_arrival.get((dest.get("scenario"), dest.get("actor")))
            if not src or not dest_meta:
                continue
            dr, da, dn = dest_meta["node_id"]
            src["node"]["default_connection"] = {
                "region": dr,
                "area": da,
                "node": dn,
            }
        DoorRando.apply_assignments_from_slot_data(
            logic.parser, extras.get("door_patches")
        )
        logic.rebuild_graph()
        logic.set_starting_node(("Hanubia", "Navigation Station", "Save Station"))

        target = "Burenia - Burenia Hub to Dairon - Pickup (Missile Tank)"
        names = logic.reachable_pickup_names(counts)
        self.assertIn(target, names)

        # Disabled tricks (old tracker default) must NOT see sphere-1 Burenia.
        class _OptZero:
            def __getattr__(self, name):
                return type("o", (), {"value": 0})()

        class _WorldZero:
            player = 1
            options = _OptZero()

        with contextlib.redirect_stdout(io.StringIO()):
            logic0 = DreadLogic(_WorldZero())
        # Re-apply same rando onto a fresh disabled-trick graph.
        transports0 = TransportRando.collect_transports(logic0.parser)
        by_teleporter0 = {
            (meta["scenario"], meta["actor"]): meta for meta in transports0.values()
        }
        by_arrival0 = {}
        for meta in transports0.values():
            by_arrival0[(meta["scenario"], meta.get("arrival_spawn") or meta["actor"])] = meta
            by_arrival0[(meta["scenario"], meta["actor"])] = meta
        for entry in extras.get("elevators") or []:
            tele = entry.get("teleporter") or {}
            dest = entry.get("destination") or {}
            src = by_teleporter0.get((tele.get("scenario"), tele.get("actor")))
            dest_meta = by_arrival0.get((dest.get("scenario"), dest.get("actor")))
            if not src or not dest_meta:
                continue
            dr, da, dn = dest_meta["node_id"]
            src["node"]["default_connection"] = {
                "region": dr,
                "area": da,
                "node": dn,
            }
        DoorRando.apply_assignments_from_slot_data(
            logic0.parser, extras.get("door_patches")
        )
        logic0.rebuild_graph()
        logic0.set_starting_node(("Hanubia", "Navigation Station", "Save Station"))
        self.assertNotIn(target, logic0.reachable_pickup_names(counts))


if __name__ == "__main__":
    unittest.main()

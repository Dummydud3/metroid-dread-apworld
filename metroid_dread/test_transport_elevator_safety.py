"""Regression: transport elevator destinations must be local start points."""
from __future__ import annotations

import unittest

from worlds.metroid_dread import TransportRando
from worlds.metroid_dread.dread_logic import DreadLogic


class _Opt:
    def __getattr__(self, name):
        return type("o", (), {"value": 0})()


class _World:
    player = 1
    options = _Opt()


class TestTransportElevatorSafety(unittest.TestCase):
    def setUp(self):
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.logic = DreadLogic(_World())
        self.transports = TransportRando.collect_transports(self.logic.parser)

    def test_every_transport_has_local_start_point(self):
        for sid, meta in self.transports.items():
            start = meta["arrival_spawn"]
            self.assertTrue(start, sid)
            # Must not equal the vanilla remote target_spawn when a real
            # start_point exists (that was the prior crash).
            node = meta["node"]
            extra = node.get("extra") or {}
            remote = extra.get("target_spawn_point")
            local = extra.get("start_point_actor_name")
            if local:
                self.assertEqual(start, local, sid)
                self.assertNotEqual(start, remote, sid)

    def test_connection_label_strips_periods(self):
        meta = {
            "transporter_name": "Hanubia - E.M.M.I.",
            "node_id": ("Hanubia", "EMMI Zone", "Dock"),
        }
        self.assertEqual(TransportRando._connection_label(meta), "Hanubia - EMMI")

    def test_matching_to_elevators_never_null_dest(self):
        import random

        rng = random.Random(1)
        matching = TransportRando.roll_matching(self.transports, rng, mode="randomized")
        if not matching:
            self.skipTest("no matching rolled")
        elev = TransportRando.matching_to_elevators(matching, self.transports)
        self.assertGreater(len(elev), 0)
        starts_by_scen = {}
        for meta in self.transports.values():
            starts_by_scen.setdefault(meta["scenario"], set()).add(meta["arrival_spawn"])
        for entry in elev:
            dest = entry["destination"]
            self.assertTrue(dest.get("scenario"))
            self.assertTrue(dest.get("actor"))
            self.assertTrue(entry.get("connection_name"))
            self.assertNotIn(".", entry["connection_name"])
            self.assertIn(
                dest["actor"],
                starts_by_scen[dest["scenario"]],
                f"dest {dest} is not a local arrival spawn",
            )

    def test_harden_elevator_rejects_empty_actor(self):
        import ap_to_patcher as ap

        with self.assertRaises(ValueError):
            ap._harden_elevator_entry(
                {
                    "teleporter": {"scenario": "s010_cave", "actor": "e"},
                    "destination": {"scenario": "s020_magma", "actor": ""},
                }
            )

    def test_harden_sanitizes_emmi_name(self):
        import ap_to_patcher as ap

        e = ap._harden_elevator_entry(
            {
                "teleporter": {"scenario": "s040_aqua", "actor": "elev"},
                "destination": {"scenario": "s080_shipyard", "actor": "plat"},
                "connection_name": "Hanubia - E.M.M.I.",
            }
        )
        self.assertEqual(e["connection_name"], "Hanubia - EMMI")


if __name__ == "__main__":
    unittest.main()

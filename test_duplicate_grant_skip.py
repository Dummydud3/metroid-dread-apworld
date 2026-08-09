"""Regression tests for ReceivedItems duplicate-skip / progressive grant logic."""

from __future__ import annotations

import unittest

from worlds.metroid_dread import dread_client_bridge as bridge


class TestShouldSkipLocalInworldGrant(unittest.TestCase):
    def test_solo_skips_own_location(self):
        self.assertTrue(
            bridge.should_skip_local_inworld_grant(1, 84022, 1, True, set())
        )

    def test_multi_skips_only_game_reported(self):
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(1, 84022, 1, False, set())
        )
        self.assertTrue(
            bridge.should_skip_local_inworld_grant(1, 84022, 1, False, {84022})
        )

    def test_multi_skips_server_checked_on_reconnect(self):
        # game_reported cleared on Dread reconnect; locations_checked persists from AP.
        self.assertTrue(
            bridge.should_skip_local_inworld_grant(
                1, 84022, 1, False, set(), {84022}
            )
        )
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(
                1, 84022, 1, False, set(), set()
            )
        )

    def test_foreign_player_never_skipped(self):
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(2, 84022, 1, False, {84022})
        )
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(2, 84022, 1, True, {84022})
        )
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(
                2, 84022, 1, False, set(), {84022}
            )
        )

    def test_start_inventory_never_skipped(self):
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(1, -1, 1, True, set())
        )
        self.assertFalse(
            bridge.should_skip_local_inworld_grant(1, 0, 1, False, {0})
        )

    def test_skip_lua_clears_pending_and_advances(self):
        lua = bridge.format_skip_local_pickup_lua(7)
        self.assertIn("RL.PendingPickup = nil", lua)
        self.assertIn("idx == RL.ReceivedPickups()", lua)
        self.assertNotIn("not RL.PendingPickup and", lua)


class TestInventoryGrantWouldBeNoop(unittest.TestCase):
    def setUp(self):
        # Minimal id list covering progressive gates + stackables used below.
        self.ids = [
            "ITEM_WEAPON_WIDE_BEAM",
            "ITEM_WEAPON_PLASMA_BEAM",
            "ITEM_WEAPON_WAVE_BEAM",
            "ITEM_VARIA_SUIT",
            "ITEM_GRAVITY_SUIT",
            "ITEM_WEAPON_CHARGE_BEAM",
            "ITEM_WEAPON_DIFFUSION_BEAM",
            "ITEM_MORPH_BALL",
            "ITEM_WEAPON_MISSILE_MAX",
            "ITEM_UPGRADE_FLASH_SHIFT_CHAIN",
        ]
        self.idx = {iid: i for i, iid in enumerate(self.ids)}

    def _amounts(self, owned: dict[str, int]) -> list[int]:
        out = [0] * len(self.ids)
        for iid, qty in owned.items():
            out[self.idx[iid]] = qty
        return out

    def test_progressive_second_tier_not_noop(self):
        progressive_suit = [
            [{"item_id": "ITEM_VARIA_SUIT", "quantity": 1}],
            [{"item_id": "ITEM_GRAVITY_SUIT", "quantity": 1}],
        ]
        # Old bug: stage-0 Varia owned → false duplicate. Must still grant Gravity.
        self.assertFalse(
            bridge.inventory_grant_would_be_noop(
                self._amounts({"ITEM_VARIA_SUIT": 1}),
                progressive_suit,
                self.ids,
            )
        )
        self.assertTrue(
            bridge.inventory_grant_would_be_noop(
                self._amounts({"ITEM_VARIA_SUIT": 1, "ITEM_GRAVITY_SUIT": 1}),
                progressive_suit,
                self.ids,
            )
        )

    def test_progressive_beam_mid_stack(self):
        progressive_beam = [
            [{"item_id": "ITEM_WEAPON_WIDE_BEAM", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_PLASMA_BEAM", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_WAVE_BEAM", "quantity": 1}],
        ]
        self.assertFalse(
            bridge.inventory_grant_would_be_noop(
                self._amounts({"ITEM_WEAPON_WIDE_BEAM": 1}),
                progressive_beam,
                self.ids,
            )
        )
        self.assertFalse(
            bridge.inventory_grant_would_be_noop(
                self._amounts(
                    {"ITEM_WEAPON_WIDE_BEAM": 1, "ITEM_WEAPON_PLASMA_BEAM": 1}
                ),
                progressive_beam,
                self.ids,
            )
        )

    def test_unique_single_stage_reconnect_dedup(self):
        morph = [[{"item_id": "ITEM_MORPH_BALL", "quantity": 1}]]
        self.assertTrue(
            bridge.inventory_grant_would_be_noop(
                self._amounts({"ITEM_MORPH_BALL": 1}), morph, self.ids
            )
        )
        self.assertFalse(
            bridge.inventory_grant_would_be_noop(self._amounts({}), morph, self.ids)
        )

    def test_stackables_never_noop(self):
        missile = [[{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 2}]]
        flash = [[{"item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "quantity": 1}]]
        self.assertFalse(
            bridge.inventory_grant_would_be_noop(
                self._amounts({"ITEM_WEAPON_MISSILE_MAX": 40}), missile, self.ids
            )
        )
        self.assertFalse(
            bridge.inventory_grant_would_be_noop(
                self._amounts({"ITEM_UPGRADE_FLASH_SHIFT_CHAIN": 3}), flash, self.ids
            )
        )


if __name__ == "__main__":
    unittest.main()

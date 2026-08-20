"""Regression: Hub ap_core must expose Metroid Bread in the local datapackage."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

WORLD = Path(__file__).resolve().parent
AP_CORE = WORLD / "ap_core"
AP_CORE_WORLDS = AP_CORE / "worlds"


class ApCoreDatapackageTests(unittest.TestCase):
    def test_datapackage_json_named_for_metroid_bread(self) -> None:
        path = AP_CORE_WORLDS / "metroid_bread_datapackage.json"
        self.assertTrue(
            path.is_file(),
            f"missing {path.name} (rename lag from metroid_dread_datapackage.json?)",
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("checksum", data)
        self.assertIn("item_name_to_id", data)
        self.assertIn("location_name_to_id", data)
        self.assertTrue(data["checksum"])

    def test_stub_worlds_registers_metroid_bread(self) -> None:
        # Load ap_core stub as ``worlds`` without polluting the real AP worlds package.
        saved = {
            key: sys.modules.pop(key)
            for key in list(sys.modules)
            if key == "worlds" or key.startswith("worlds.")
        }
        try:
            spec = importlib.util.spec_from_file_location(
                "worlds",
                AP_CORE_WORLDS / "__init__.py",
                submodule_search_locations=[str(AP_CORE_WORLDS)],
            )
            self.assertIsNotNone(spec)
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            sys.modules["worlds"] = mod
            spec.loader.exec_module(mod)
            games = mod.network_data_package.get("games", {})
            self.assertIn("Metroid Bread", games)
            self.assertTrue(games["Metroid Bread"].get("checksum"))
        finally:
            for key in list(sys.modules):
                if key == "worlds" or key.startswith("worlds."):
                    sys.modules.pop(key, None)
            sys.modules.update(saved)

    def test_common_client_init_tolerates_missing_game_package(self) -> None:
        """Hub crash: KeyError when self.game is absent from local network_data_package."""
        fake_worlds = types.ModuleType("worlds")
        fake_worlds.network_data_package = {"games": {}}  # type: ignore[attr-defined]
        fake_worlds.AutoWorldRegister = types.SimpleNamespace(world_types={})  # type: ignore[attr-defined]

        # Bypass ModuleUpdate's Python version gate (test may run on 3.10 CI hosts).
        fake_module_update = types.ModuleType("ModuleUpdate")
        fake_module_update.update = lambda *a, **k: None  # type: ignore[attr-defined]
        fake_module_update.update_ran = True  # type: ignore[attr-defined]

        wipe_keys = (
            "worlds",
            "CommonClient",
            "Utils",
            "NetUtils",
            "Options",
            "settings",
            "ModuleUpdate",
        )
        saved = {
            key: sys.modules.pop(key)
            for key in list(sys.modules)
            if key in wipe_keys or key.startswith("worlds.")
        }
        sys.modules["worlds"] = fake_worlds
        sys.modules["ModuleUpdate"] = fake_module_update
        if str(AP_CORE) not in sys.path:
            sys.path.insert(0, str(AP_CORE))
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with mock.patch.dict(
                    os.environ, {"HOME": tmp, "USERPROFILE": tmp}, clear=False
                ):
                    import CommonClient as cc  # noqa: WPS433

                    class _Ctx(cc.CommonContext):
                        game = "Metroid Bread"

                    async def _construct() -> cc.CommonContext:
                        return _Ctx(None, None)

                    ctx = loop.run_until_complete(_construct())
                    self.assertNotIn("Metroid Bread", ctx.checksums)
                    ctx.keep_alive_task.cancel()
        finally:
            try:
                loop.run_until_complete(asyncio.sleep(0))
            except Exception:
                pass
            loop.close()
            asyncio.set_event_loop(None)
            for key in list(sys.modules):
                if key in wipe_keys or key.startswith("worlds."):
                    sys.modules.pop(key, None)
            sys.modules.update(saved)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

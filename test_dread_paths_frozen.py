"""Tests for frozen Archipelago install path resolution (ap_core)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLD = Path(__file__).resolve().parent
if str(WORLD) not in sys.path:
    sys.path.insert(0, str(WORLD))

import dread_paths as dp  # noqa: E402


class FrozenApRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = {
            key: os.environ.pop(key, None)
            for key in (
                "DREAD_HUB_AP_ROOT",
                "ARCHIPELAGO_ROOT",
                "DREAD_HUB_INSTALL_ROOT",
                "DREAD_HUB_FROZEN_ROOT",
            )
        }

    def tearDown(self) -> None:
        for key, val in self._env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_pure_frozen_uses_bundled_ap_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp) / "Archipelago"
            (frozen / "lib").mkdir(parents=True)
            (frozen / "lib" / "library.zip").write_bytes(b"PK\x03\x04")
            (frozen / "ArchipelagoLauncher.exe").write_bytes(b"MZ")
            world = frozen / "custom_worlds" / "_metroid_dread_runtime"
            src_core = WORLD / "ap_core"
            self.assertTrue((src_core / "CommonClient.py").is_file())
            shutil.copytree(src_core, world / "ap_core")

            imp, inst = dp.resolve_ap_roots(world)
            self.assertEqual(imp, (world / "ap_core").resolve())
            self.assertEqual(inst, frozen.resolve())
            self.assertTrue(dp._is_frozen_ap_install(frozen))
            self.assertFalse(dp._is_source_ap_root(frozen))

    def test_source_checkout_preferred_over_ap_core(self) -> None:
        # This world package lives under a real AP checkout with CommonClient.py.
        if not (ROOT / "CommonClient.py").is_file():
            self.skipTest("not running inside an Archipelago source tree")
        imp, inst = dp.resolve_ap_roots(WORLD)
        self.assertEqual(imp.resolve(), ROOT.resolve())
        self.assertEqual(inst.resolve(), ROOT.resolve())
        self.assertNotEqual(imp.name.lower(), "ap_core")


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

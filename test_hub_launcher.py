"""
Unit tests for Hub launcher helpers (no network required).

Run:
  py -3.12 -m worlds.metroid_dread.test_hub_launcher
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow `python worlds/metroid_dread/test_hub_launcher.py` from repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worlds.metroid_dread import hub_launcher as hl  # noqa: E402


class ElectronHealthTests(unittest.TestCase):
    def test_unhealthy_without_path_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "node_modules" / "electron" / "dist").mkdir(parents=True)
            self.assertFalse(hl.electron_is_healthy(hub))

    def test_healthy_with_path_txt_and_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            pkg = hub / "node_modules" / "electron"
            dist = pkg / "dist"
            dist.mkdir(parents=True)
            rel = hl.electron_relative_binary("win32")
            (dist / rel).write_bytes(b"fake")
            (pkg / "path.txt").write_text(rel, encoding="utf-8")
            self.assertTrue(hl.electron_is_healthy(hub, platform="win32"))

    def test_healthy_fallback_expected_binary_without_matching_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            pkg = hub / "node_modules" / "electron"
            dist = pkg / "dist"
            dist.mkdir(parents=True)
            (pkg / "path.txt").write_text("electron.exe", encoding="utf-8")
            # path points at missing file, but expected linux binary exists
            (dist / "electron").write_bytes(b"fake")
            self.assertTrue(hl.electron_is_healthy(hub, platform="linux"))


class ElectronErrorDetectionTests(unittest.TestCase):
    def test_detects_official_message(self):
        msg = (
            "Error: Electron failed to install correctly, please delete "
            "node_modules/electron and try installing again"
        )
        self.assertTrue(hl.is_electron_reinstall_error(msg))

    def test_ignores_unrelated(self):
        self.assertFalse(hl.is_electron_reinstall_error("npm ERR! code EACCES"))
        self.assertFalse(hl.is_electron_reinstall_error(""))


class ParseArgsTests(unittest.TestCase):
    def test_archipelago_uri(self):
        info = hl.parse_launcher_connect_args(
            ("archipelago://Player%201:secret@archipelago.gg:60784?game=Metroid%20Dread",)
        )
        self.assertEqual(info["server"], "archipelago.gg:60784")
        self.assertEqual(info["slot"], "Player 1")
        self.assertEqual(info["password"], "secret")
        self.assertEqual(info["game"], "Metroid Dread")
        self.assertTrue(info["auto_connect"])

    def test_archipelago_uri_none_password_and_room(self):
        uri = (
            "archipelago://orangeonionMD:None@archipelago.gg:34841"
            "?game=Metroid%20Dread&room=tZ3ljEKLSSC2j3nCdoiyoQ"
        )
        info = hl.parse_launcher_connect_args((uri,))
        self.assertEqual(info["server"], "archipelago.gg:34841")
        self.assertEqual(info["slot"], "orangeonionMD")
        self.assertEqual(info["password"], "")  # literal None → empty
        self.assertEqual(info["game"], "Metroid Dread")
        self.assertEqual(info["room"], "tZ3ljEKLSSC2j3nCdoiyoQ")
        self.assertTrue(info["auto_connect"])

    def test_normalize_uri_password(self):
        self.assertEqual(hl.normalize_uri_password("None"), "")
        self.assertEqual(hl.normalize_uri_password("null"), "")
        self.assertEqual(hl.normalize_uri_password("secret"), "secret")
        self.assertIsNone(hl.normalize_uri_password(None))

    def test_flag_args(self):
        info = hl.parse_launcher_connect_args(
            ("--connect", "127.0.0.1:38281", "--name", "Samus", "--password", "x", "--dread-ip", "10.0.0.2")
        )
        self.assertEqual(info["server"], "127.0.0.1:38281")
        self.assertEqual(info["slot"], "Samus")
        self.assertEqual(info["password"], "x")
        self.assertEqual(info["dread_ip"], "10.0.0.2")

    def test_apply_prefills_sets_auto_connect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = hl.apply_connect_prefills(
                root,
                {
                    "server": "archipelago.gg:34841",
                    "slot": "orangeonionMD",
                    "password": "",
                    "room": "abc",
                    "url": "archipelago://orangeonionMD:None@archipelago.gg:34841?game=Metroid%20Dread",
                    "auto_connect": True,
                },
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["password"], "")
            self.assertEqual(data["room_id"], "abc")
            self.assertTrue(data["auto_connect_ap"])
            self.assertEqual(data["hub_stage"], "connect")


class PrefillAndFindTests(unittest.TestCase):
    def test_apply_connect_prefills_writes_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = hl.apply_connect_prefills(
                root,
                {"server": "host:1", "slot": "A", "password": "p", "dread_ip": "1.2.3.4"},
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["server"], "host:1")
            self.assertEqual(data["slot"], "A")
            self.assertEqual(data["password"], "p")
            self.assertEqual(data["dread_ip"], "1.2.3.4")

    def test_find_hub_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hub = root / "dread-client-app"
            hub.mkdir()
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / "main.js").write_text("//", encoding="utf-8")
            found = hl.find_hub_dir(extra_roots=[root])
            self.assertEqual(found, hub.resolve())

    def test_find_hub_dir_prefers_world_package(self):
        """Canonical Hub is beside hub_launcher.py under worlds/metroid_dread."""
        world = hl.world_package_dir()
        hub = world / "dread-client-app"
        if (hub / "package.json").is_file() and (hub / "main.js").is_file():
            found = hl.find_hub_dir()
            self.assertEqual(found, hub.resolve())
            self.assertEqual(hl.find_world_dir_for_hub(found), world.resolve())

    def test_remove_electron_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            pkg = hub / "node_modules" / "electron" / "dist"
            pkg.mkdir(parents=True)
            (pkg / "electron.exe").write_bytes(b"x")
            hl.remove_electron_package(hub)
            self.assertFalse((hub / "node_modules" / "electron").exists())

    def test_materialize_hub_from_apworld(self):
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apw = root / "metroid_dread.apworld"
            with zipfile.ZipFile(apw, "w") as zf:
                zf.writestr("metroid_dread/dread-client-app/package.json", "{}")
                zf.writestr("metroid_dread/dread-client-app/main.js", "// hub")
                zf.writestr("metroid_dread/dread-client-app/room_info_gate.js", "// gate")
                zf.writestr("metroid_dread/dread-client-app/renderer/app.js", "//")
                zf.writestr(
                    "metroid_dread/dread-client-app/node_modules/electron/index.js",
                    "// must not extract",
                )
                zf.writestr("metroid_dread/MetroidDreadClient.py", "# client\n")
                zf.writestr("metroid_dread/dread_direct_patch.py", "# patcher\n")
                zf.writestr("metroid_dread/dread_client_ui_config.json", "{}")
            dest = root / "runtime"
            hub = hl.materialize_hub_from_apworld(apw, dest)
            self.assertTrue((hub / "package.json").is_file())
            self.assertTrue((hub / "main.js").is_file())
            self.assertTrue((hub / "room_info_gate.js").is_file())
            self.assertTrue((dest / hl.CLIENT_SCRIPT_NAME).is_file())
            self.assertTrue((dest / "dread_direct_patch.py").is_file())
            self.assertTrue((dest / hl.CONFIG_NAME).is_file())
            self.assertFalse((hub / "node_modules").exists())
            self.assertTrue(hl.runtime_tree_ready(dest))
            # second call is a no-op when stamp matches
            hub2 = hl.materialize_hub_from_apworld(apw, dest)
            self.assertEqual(hub.resolve(), hub2.resolve())

    def test_materialize_refreshes_when_client_missing(self):
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apw = root / "metroid_dread.apworld"
            with zipfile.ZipFile(apw, "w") as zf:
                zf.writestr("metroid_dread/dread-client-app/package.json", "{}")
                zf.writestr("metroid_dread/dread-client-app/main.js", "// hub")
                zf.writestr("metroid_dread/dread-client-app/room_info_gate.js", "// gate")
                zf.writestr("metroid_dread/MetroidDreadClient.py", "# client\n")
            dest = root / "runtime"
            hub = dest / "dread-client-app"
            hub.mkdir(parents=True)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / "main.js").write_text("//", encoding="utf-8")
            (hub / "room_info_gate.js").write_text("//", encoding="utf-8")
            # Old hub-only stamp (no layout marker / no client) must refresh.
            (dest / hl.APWORLD_STAMP_NAME).write_text("stale", encoding="utf-8")
            out = hl.materialize_hub_from_apworld(apw, dest)
            self.assertTrue((dest / hl.CLIENT_SCRIPT_NAME).is_file())
            self.assertEqual(out.resolve(), hub.resolve())

    def test_find_containing_apworld(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apw = root / "game.apworld"
            apw.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # minimal empty zip EOCD
            fake_file = apw / "metroid_dread" / "hub_launcher.py"
            # Path under zip is virtual; find_containing_apworld walks parents of a Path
            virtual = Path(str(apw)) / "metroid_dread" / "hub_launcher.py"
            found = hl.find_containing_apworld(virtual)
            self.assertEqual(found, apw.resolve())


class ProbeAndRelativeBinaryTests(unittest.TestCase):
    def test_relative_binary_per_platform(self):
        self.assertEqual(hl.electron_relative_binary("win32"), "electron.exe")
        self.assertEqual(hl.electron_relative_binary("linux"), "electron")
        self.assertEqual(hl.electron_relative_binary("darwin"), "Electron.app/Contents/MacOS/Electron")

    def test_probe_success_and_reinstall_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            with mock.patch.object(hl, "find_node", return_value="node"):
                with mock.patch.object(hl.subprocess, "run") as run:
                    run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                    ok, _ = hl.probe_electron_load(hub)
                    self.assertTrue(ok)

                    run.return_value = mock.Mock(
                        returncode=1,
                        stdout="",
                        stderr=(
                            "Electron failed to install correctly, please delete "
                            "node_modules/electron and try installing again"
                        ),
                    )
                    ok, out = hl.probe_electron_load(hub)
                    self.assertFalse(ok)
                    self.assertTrue(hl.is_electron_reinstall_error(out))


class EnsurePackagesDryRunTests(unittest.TestCase):
    def test_ensure_skips_when_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / "node_modules" / "adm-zip").mkdir(parents=True)
            pkg = hub / "node_modules" / "electron"
            dist = pkg / "dist"
            dist.mkdir(parents=True)
            rel = "electron.exe"
            (dist / rel).write_bytes(b"fake")
            (pkg / "path.txt").write_text(rel, encoding="utf-8")

            with mock.patch.object(hl, "run_npm") as run_npm:
                changed = hl.ensure_hub_packages(hub)
            self.assertFalse(changed)
            run_npm.assert_not_called()

    def test_ensure_repairs_unhealthy_electron(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / "node_modules").mkdir()
            broken = hub / "node_modules" / "electron"
            broken.mkdir()
            # no path.txt / binary

            def fake_npm(_hub, args, env=None):
                # Simulate successful npm install by writing a healthy electron tree.
                pkg = hub / "node_modules" / "electron"
                dist = pkg / "dist"
                dist.mkdir(parents=True, exist_ok=True)
                (dist / "electron.exe").write_bytes(b"ok")
                (pkg / "path.txt").write_text("electron.exe", encoding="utf-8")
                (hub / "node_modules" / "adm-zip").mkdir(exist_ok=True)
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(hl, "run_npm", side_effect=fake_npm):
                with mock.patch.object(hl, "find_npm", return_value="npm"):
                    changed = hl.ensure_hub_packages(hub, force_reinstall_electron=True)
            self.assertTrue(changed)
            self.assertTrue(hl.electron_is_healthy(hub, platform="win32"))


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

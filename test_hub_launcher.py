"""
Unit tests for Hub launcher helpers (no network required).

Run:
  py -3.12 -m worlds.metroid_bread.test_hub_launcher
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow `python worlds/metroid_bread/test_hub_launcher.py` from repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worlds.metroid_bread import hub_launcher as hl  # noqa: E402


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


class NodeElectronCompatTests(unittest.TestCase):
    def test_accepts_lts_majors(self):
        self.assertIsNone(hl.node_electron_compat_message(None))
        self.assertIsNone(hl.node_electron_compat_message(18))
        self.assertIsNone(hl.node_electron_compat_message(20))
        self.assertIsNone(hl.node_electron_compat_message(22))
        self.assertIsNone(hl.node_electron_compat_message(24))

    def test_rejects_node_25_plus(self):
        msg = hl.node_electron_compat_message(26)
        self.assertIsNotNone(msg)
        self.assertIn("Node.js 26", msg)
        self.assertIn("Node.js 24", msg)
        self.assertIsNotNone(hl.node_electron_compat_message(25))

    def test_ensure_raises_on_unsupported(self):
        with mock.patch.object(hl, "node_major_version", return_value=26):
            with self.assertRaises(RuntimeError) as ctx:
                hl.ensure_node_supports_electron()
            self.assertIn("26", str(ctx.exception))

    def test_ensure_ok_on_supported(self):
        with mock.patch.object(hl, "node_major_version", return_value=20):
            hl.ensure_node_supports_electron()


class ParseArgsTests(unittest.TestCase):
    def test_archipelago_uri(self):
        info = hl.parse_launcher_connect_args(
            ("archipelago://Player%201:secret@archipelago.gg:60784?game=Metroid%20Bread",)
        )
        self.assertEqual(info["server"], "archipelago.gg:60784")
        self.assertEqual(info["slot"], "Player 1")
        self.assertEqual(info["password"], "secret")
        self.assertEqual(info["game"], "Metroid Bread")
        self.assertTrue(info["auto_connect"])

    def test_archipelago_uri_none_password_and_room(self):
        uri = (
            "archipelago://orangeonionMD:None@archipelago.gg:34841"
            "?game=Metroid%20Bread&room=tZ3ljEKLSSC2j3nCdoiyoQ"
        )
        info = hl.parse_launcher_connect_args((uri,))
        self.assertEqual(info["server"], "archipelago.gg:34841")
        self.assertEqual(info["slot"], "orangeonionMD")
        self.assertEqual(info["password"], "")  # literal None → empty
        self.assertEqual(info["game"], "Metroid Bread")
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
                    "url": "archipelago://orangeonionMD:None@archipelago.gg:34841?game=Metroid%20Bread",
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
        """Canonical Hub is beside hub_launcher.py under worlds/metroid_bread."""
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
            apw = root / "metroid_bread.apworld"
            with zipfile.ZipFile(apw, "w") as zf:
                zf.writestr("metroid_bread/dread-client-app/package.json", "{}")
                zf.writestr("metroid_bread/dread-client-app/main.js", "// hub")
                zf.writestr("metroid_bread/dread-client-app/room_info_gate.js", "// gate")
                zf.writestr("metroid_bread/dread-client-app/renderer/app.js", "//")
                zf.writestr(
                    "metroid_bread/dread-client-app/node_modules/electron/index.js",
                    "// must not extract",
                )
                zf.writestr("metroid_bread/MetroidBreadClient.py", "# client\n")
                zf.writestr("metroid_bread/dread_direct_patch.py", "# patcher\n")
                zf.writestr("metroid_bread/dread_client_ui_config.json", "{}")
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
            apw = root / "metroid_bread.apworld"
            with zipfile.ZipFile(apw, "w") as zf:
                zf.writestr("metroid_bread/dread-client-app/package.json", "{}")
                zf.writestr("metroid_bread/dread-client-app/main.js", "// hub")
                zf.writestr("metroid_bread/dread-client-app/room_info_gate.js", "// gate")
                zf.writestr("metroid_bread/MetroidBreadClient.py", "# client\n")
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
            fake_file = apw / "metroid_bread" / "hub_launcher.py"
            # Path under zip is virtual; find_containing_apworld walks parents of a Path
            virtual = Path(str(apw)) / "metroid_bread" / "hub_launcher.py"
            found = hl.find_containing_apworld(virtual)
            self.assertEqual(found, apw.resolve())

    def test_ensure_filesystem_world_dir_extracts_apworld(self):
        """Linux frozen fallback: Python client must not read Items.py from zip path."""
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apw = root / "metroid_bread.apworld"
            with zipfile.ZipFile(apw, "w") as zf:
                zf.writestr("metroid_bread/dread-client-app/package.json", "{}")
                zf.writestr("metroid_bread/dread-client-app/main.js", "// hub")
                zf.writestr("metroid_bread/dread-client-app/room_info_gate.js", "// gate")
                zf.writestr("metroid_bread/MetroidBreadClient.py", "# client\n")
                zf.writestr("metroid_bread/Items.py", 'base_id = 84000\nitem_table = {"Missile": ItemData(base_id + 0)}\n')
            dest = root / "runtime"
            with mock.patch.object(hl, "find_containing_apworld", return_value=apw):
                with mock.patch.object(hl, "world_package_dir", return_value=apw / "metroid_bread"):
                    with mock.patch.object(hl, "runtime_world_dir", return_value=dest):
                        out = hl.ensure_filesystem_world_dir()
            self.assertEqual(out.resolve(), dest.resolve())
            self.assertTrue((dest / "Items.py").is_file())
            self.assertTrue((dest / hl.CLIENT_SCRIPT_NAME).is_file())


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


class FindNpmTests(unittest.TestCase):
    def test_windows_prefers_npm_cmd_and_skips_ps1(self):
        def fake_which(name):
            mapping = {
                "npm": r"C:\Program Files\nodejs\npm.ps1",
                "npm.cmd": r"C:\Program Files\nodejs\npm.cmd",
                "npm.exe": None,
            }
            return mapping.get(name)

        with mock.patch.object(hl.os, "name", "nt"):
            with mock.patch.object(hl.shutil, "which", side_effect=fake_which):
                self.assertEqual(
                    hl.find_npm(),
                    r"C:\Program Files\nodejs\npm.cmd",
                )

    def test_windows_skips_ps1_when_only_bare_npm(self):
        def fake_which(name):
            if name == "npm":
                return r"C:\Program Files\nodejs\npm.ps1"
            return None

        with mock.patch.object(hl.os, "name", "nt"):
            with mock.patch.object(hl.shutil, "which", side_effect=fake_which):
                self.assertIsNone(hl.find_npm())


class EnsurePackagesDryRunTests(unittest.TestCase):
    def test_ensure_skips_when_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / ".npmrc").write_text(
                "ignore-scripts=false\ndangerously-allow-all-scripts=true\n",
                encoding="utf-8",
            )
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

    def test_ensure_writes_npmrc_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / "node_modules" / "adm-zip").mkdir(parents=True)
            pkg = hub / "node_modules" / "electron"
            dist = pkg / "dist"
            dist.mkdir(parents=True)
            (dist / "electron.exe").write_bytes(b"fake")
            (pkg / "path.txt").write_text("electron.exe", encoding="utf-8")

            with mock.patch.object(hl, "run_npm") as run_npm:
                changed = hl.ensure_hub_packages(hub)
            self.assertTrue(changed)
            run_npm.assert_not_called()
            npmrc = (hub / ".npmrc").read_text(encoding="utf-8")
            self.assertIn("ignore-scripts=false", npmrc.replace(" ", ""))

    def test_ensure_appends_dangerously_allow_when_partial_npmrc(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / ".npmrc").write_text("ignore-scripts=false\n", encoding="utf-8")
            (hub / "node_modules" / "adm-zip").mkdir(parents=True)
            pkg = hub / "node_modules" / "electron"
            dist = pkg / "dist"
            dist.mkdir(parents=True)
            (dist / "electron.exe").write_bytes(b"fake")
            (pkg / "path.txt").write_text("electron.exe", encoding="utf-8")

            with mock.patch.object(hl, "run_npm") as run_npm:
                changed = hl.ensure_hub_packages(hub)
            self.assertTrue(changed)
            run_npm.assert_not_called()
            npmrc = (hub / ".npmrc").read_text(encoding="utf-8").lower().replace(" ", "")
            self.assertIn("ignore-scripts=false", npmrc)
            self.assertIn("dangerously-allow-all-scripts=true", npmrc)

    def test_ensure_rewrites_npmrc_when_ignore_scripts_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / ".npmrc").write_text("ignore-scripts=true\n", encoding="utf-8")
            (hub / "node_modules" / "adm-zip").mkdir(parents=True)
            pkg = hub / "node_modules" / "electron"
            dist = pkg / "dist"
            dist.mkdir(parents=True)
            (dist / "electron.exe").write_bytes(b"fake")
            (pkg / "path.txt").write_text("electron.exe", encoding="utf-8")

            with mock.patch.object(hl, "run_npm") as run_npm:
                changed = hl.ensure_hub_packages(hub)
            self.assertTrue(changed)
            run_npm.assert_not_called()
            npmrc = (hub / ".npmrc").read_text(encoding="utf-8").lower().replace(" ", "")
            self.assertIn("ignore-scripts=false", npmrc)
            self.assertNotIn("ignore-scripts=true", npmrc)

    def test_ensure_repairs_unhealthy_electron(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            (hub / "package.json").write_text("{}", encoding="utf-8")
            (hub / ".npmrc").write_text("ignore-scripts=false\n", encoding="utf-8")
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

    def test_run_electron_install_js_restores_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            pkg = hub / "node_modules" / "electron"
            pkg.mkdir(parents=True)
            (pkg / "install.js").write_text("// stub", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                dist = pkg / "dist"
                dist.mkdir(parents=True, exist_ok=True)
                (dist / "electron.exe").write_bytes(b"ok")
                (pkg / "path.txt").write_text("electron.exe", encoding="utf-8")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(hl, "find_node", return_value="node"):
                with mock.patch.object(hl.subprocess, "run", side_effect=fake_run):
                    ok, _ = hl.run_electron_install_js(hub)
            self.assertTrue(ok)
            self.assertTrue(hl.electron_is_healthy(hub, platform="win32"))

    def test_npm_install_args_disable_ignore_scripts(self):
        self.assertEqual(hl.npm_install_args(), ["install", "--no-ignore-scripts"])
        self.assertEqual(
            hl.npm_install_args(["electron", "--save-dev"]),
            ["install", "--no-ignore-scripts", "electron", "--save-dev"],
        )


class LoadClientModuleTests(unittest.TestCase):
    def test_load_registers_sys_modules_for_dataclass(self):
        """Hub file-load must register sys.modules before exec (PEP 563 dataclasses)."""
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            client = world / "MetroidBreadClient.py"
            client.write_text(
                "from __future__ import annotations\n"
                "from dataclasses import dataclass\n"
                "@dataclass\n"
                "class DreadSocketHolder:\n"
                "    x: int\n",
                encoding="utf-8",
            )
            # Clear any prior stub so we exercise the register-before-exec path.
            sys.modules.pop("metroid_bread_client_impl", None)
            with mock.patch.object(hl, "runtime_world_dir", return_value=world):
                with mock.patch.object(hl, "world_package_dir", return_value=world):
                    with mock.patch.object(hl, "find_containing_apworld", return_value=None):
                        mod = hl._load_metroid_bread_client_module(world)
            self.assertIs(sys.modules.get("metroid_bread_client_impl"), mod)
            self.assertTrue(hasattr(mod, "DreadSocketHolder"))
            self.assertEqual(mod.DreadSocketHolder(1).x, 1)


class ManagedNodeFindTests(unittest.TestCase):
    def test_find_node_prefers_managed_when_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp) / "tools" / "node-v24"
            tools.mkdir(parents=True)
            node_exe = tools / ("node.exe" if sys.platform == "win32" else "node")
            if sys.platform != "win32":
                (tools / "bin").mkdir(parents=True, exist_ok=True)
                node_exe = tools / "bin" / "node"
            node_exe.write_bytes(b"fake")
            managed = str(node_exe)

            with mock.patch.object(hl, "managed_node_executable", return_value=Path(managed)):
                with mock.patch.object(hl, "node_major_version", return_value=24):
                    with mock.patch.object(hl.shutil, "which", return_value=r"C:\system\node.exe"):
                        self.assertEqual(hl.find_node(), managed)

    def test_find_node_prefers_managed_when_system_too_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            managed = Path(tmp) / "node.exe"
            managed.write_bytes(b"fake")

            def fake_major(node=None):
                if node and "system" in str(node).replace("\\", "/"):
                    return 26
                if node and str(managed) in str(node):
                    return 24
                return 26

            with mock.patch.object(hl, "managed_node_executable", return_value=managed):
                with mock.patch.object(hl, "node_major_version", side_effect=fake_major):
                    with mock.patch.object(
                        hl.shutil, "which", return_value=r"C:\system\node.exe"
                    ):
                        # managed major 24 → preferred in first branch
                        self.assertEqual(hl.find_node(), str(managed))


class LaunchFallbackWizardTests(unittest.TestCase):
    def test_missing_prereqs_opens_wizard_not_silent_kivy(self):
        with mock.patch.object(hl, "parse_launcher_connect_args", return_value={}):
            with mock.patch.object(hl, "find_hub_dir", return_value=None):
                with mock.patch.object(hl, "find_node", return_value=None):
                    with mock.patch.object(hl, "find_npm", return_value=None):
                        with mock.patch.object(
                            hl, "_run_setup_wizard_or_python", return_value="python"
                        ) as wiz:
                            with mock.patch.object(hl, "launch_python_client") as kivy:
                                out = hl.launch_hub_or_fallback(())
        self.assertEqual(out, "python")
        wiz.assert_called_once()
        reason = wiz.call_args.kwargs.get("reason") or (
            wiz.call_args[1].get("reason") if len(wiz.call_args) > 1 else ""
        )
        if not reason and wiz.call_args.args:
            # reason is keyword-only
            reason = wiz.call_args.kwargs.get("reason", "")
        self.assertIn("node not found", reason)
        kivy.assert_not_called()

    def test_hub_launch_failure_opens_wizard(self):
        hub = Path("/tmp/fake-hub")
        with mock.patch.object(hl, "parse_launcher_connect_args", return_value={}):
            with mock.patch.object(hl, "find_hub_dir", return_value=hub):
                with mock.patch.object(hl, "find_node", return_value="node"):
                    with mock.patch.object(hl, "find_npm", return_value="npm"):
                        with mock.patch.object(
                            hl, "find_world_dir_for_hub", return_value=hub.parent
                        ):
                            with mock.patch.object(hl, "apply_connect_prefills"):
                                with mock.patch.object(
                                    hl, "hub_env_from_connect", return_value={}
                                ):
                                    with mock.patch.object(
                                        hl, "ensure_system_client_python_deps"
                                    ):
                                        with mock.patch.object(
                                            hl,
                                            "launch_hub_with_repair",
                                            side_effect=RuntimeError("boom"),
                                        ):
                                            with mock.patch.object(
                                                hl,
                                                "_run_setup_wizard_or_python",
                                                return_value="hub",
                                            ) as wiz:
                                                out = hl.launch_hub_or_fallback(())
        self.assertEqual(out, "hub")
        wiz.assert_called_once()
        self.assertIn("boom", wiz.call_args.kwargs["reason"])

    def test_wizard_missing_falls_back_to_python(self):
        with mock.patch.object(hl, "launch_python_client") as kivy:
            # Force ImportError for wizard module path used by helper.
            import builtins

            real_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name in ("hub_setup_wizard", "worlds.metroid_bread.hub_setup_wizard"):
                    raise ImportError("no wizard")
                return real_import(name, *args, **kwargs)

            with mock.patch.object(builtins, "__import__", side_effect=fake_import):
                out = hl._run_setup_wizard_or_python((), reason="test")
        self.assertEqual(out, "python")
        kivy.assert_called_once()

    def test_wizard_python_choice_launches_kivy(self):
        fake_wizard = mock.Mock(return_value="python")
        import types

        mod = types.ModuleType("hub_setup_wizard")
        mod.run_setup_wizard = fake_wizard
        with mock.patch.dict(sys.modules, {"hub_setup_wizard": mod}):
            with mock.patch.object(hl, "launch_python_client") as kivy:
                out = hl._run_setup_wizard_or_python((), reason="x")
        self.assertEqual(out, "python")
        kivy.assert_called_once()
        fake_wizard.assert_called_once()

    def test_wizard_hub_choice_skips_kivy(self):
        fake_wizard = mock.Mock(return_value="hub")
        import types

        mod = types.ModuleType("hub_setup_wizard")
        mod.run_setup_wizard = fake_wizard
        with mock.patch.dict(sys.modules, {"hub_setup_wizard": mod}):
            with mock.patch.object(hl, "launch_python_client") as kivy:
                out = hl._run_setup_wizard_or_python((), reason="ok")
        self.assertEqual(out, "hub")
        kivy.assert_not_called()


class PortableNodeHelperTests(unittest.TestCase):
    def test_archive_suffix_win_x64(self):
        from worlds.metroid_bread import ensure_portable_node as epn

        self.assertEqual(epn.node_archive_suffix("win32", "AMD64"), "win-x64.zip")
        self.assertEqual(epn.node_archive_suffix("linux", "x86_64"), "linux-x64.tar.xz")
        self.assertEqual(epn.node_archive_suffix("darwin", "arm64"), "darwin-arm64.tar.gz")

    def test_resolve_node_url_parses_shasums(self):
        from worlds.metroid_bread import ensure_portable_node as epn
        from io import BytesIO

        body = (
            "abc node-v24.19.0-win-x64.zip\n"
            "def node-v24.19.0-linux-x64.tar.xz\n"
        ).encode()

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        def fake_open(url, timeout=60):
            self.assertIn("SHASUMS256.txt", url)
            return FakeResp()

        url, name = epn.resolve_node24_archive_url(
            plat="win32", machine="AMD64", opener=fake_open
        )
        self.assertTrue(url.endswith("node-v24.19.0-win-x64.zip"))
        self.assertEqual(name, "node-v24.19.0-win-x64.zip")


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

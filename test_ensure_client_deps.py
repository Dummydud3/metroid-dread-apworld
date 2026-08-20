"""
Unit tests for ensure_client_deps (no network / no real pip install).

Run:
  py -3.12 -m worlds.metroid_bread.test_ensure_client_deps
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worlds.metroid_bread import ensure_client_deps as ecd  # noqa: E402


class MessageTests(unittest.TestCase):
    def test_python_missing_mentions_path_and_py_install(self):
        msg = ecd.python_missing_message()
        self.assertIn("3.11–3.13", msg)
        self.assertIn("python.org", msg)
        self.assertIn("Add python.exe to PATH", msg)
        self.assertIn("py install 3.12", msg)
        self.assertIn("local venv", msg)

    def test_pip_failure_includes_manual_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            req = world / "requirements-client.txt"
            req.write_text("websockets>=13\n", encoding="utf-8")
            msg = ecd.pip_failure_message(["py", "-3.12"], req_path=req, detail="boom")
            self.assertIn("py -3.12 -m pip install -r", msg)
            self.assertIn("requirements-client.txt", msg)
            self.assertIn("python.org", msg)
            self.assertIn("ensurepip", msg)
            self.assertIn("boom", msg)

    def test_pip_missing_detail_shows_ensurepip_hints(self):
        msg = ecd.pip_failure_message(
            ["py", "-3.12"],
            detail="No module named pip",
        )
        self.assertIn("ensurepip --upgrade", msg)
        self.assertIn("No module named pip", msg)
        # pip-missing path should not bury the user in "reinstall Python" first.
        self.assertTrue(
            msg.index("ensurepip") < msg.index("pip output:"),
            msg,
        )


class EnsureLogicTests(unittest.TestCase):
    def test_ok_when_nothing_missing(self):
        with mock.patch.object(ecd, "resolve_install_python", return_value=(["py", "-3.12"], "", ecd.EXIT_OK)):
            with mock.patch.object(ecd, "missing_imports", return_value=[]):
                with mock.patch.object(ecd, "_install_packages") as install:
                    ok, msg, code = ecd.ensure_client_deps(log=lambda _m: None)
        self.assertTrue(ok)
        self.assertEqual(code, ecd.EXIT_OK)
        install.assert_not_called()
        self.assertIn("OK", msg)

    def test_installs_when_missing(self):
        with mock.patch.object(ecd, "resolve_install_python", return_value=(["py", "-3.12"], "", ecd.EXIT_OK)):
            with mock.patch.object(
                ecd, "missing_imports", side_effect=[["websockets"], []]
            ):
                with mock.patch.object(
                    ecd, "_install_packages", return_value=(True, "installed")
                ) as install:
                    ok, msg, code = ecd.ensure_client_deps(log=lambda _m: None)
        self.assertTrue(ok)
        self.assertEqual(code, ecd.EXIT_OK)
        install.assert_called_once()
        self.assertIn("websockets", msg)

    def test_ensure_pip_skipped_when_available(self):
        with mock.patch.object(ecd, "pip_available", return_value=True):
            with mock.patch.object(ecd, "subprocess") as sp:
                ok, detail = ecd.ensure_pip(["py", "-3.12"], log=lambda _m: None)
        self.assertTrue(ok)
        self.assertEqual(detail, "")
        sp.run.assert_not_called()

    def test_install_packages_bootstraps_pip(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            (world / "requirements-client.txt").write_text("websockets>=13\n", encoding="utf-8")
            fake_proc = mock.Mock(returncode=0, stdout="ok", stderr="")
            with mock.patch.object(ecd, "pip_available", return_value=False):
                with mock.patch.object(
                    ecd, "ensure_pip", return_value=(True, "bootstrapped")
                ) as boot:
                    with mock.patch.object(
                        ecd.subprocess, "run", return_value=fake_proc
                    ) as run:
                        ok, _detail = ecd._install_packages(
                            ["py", "-3.12"], world=world, log=lambda _m: None
                        )
            self.assertTrue(ok)
            boot.assert_called_once()
            run.assert_called_once()
            self.assertIn("pip", run.call_args[0][0])

    def test_python_missing_exit_code(self):
        with mock.patch.object(
            ecd,
            "resolve_install_python",
            return_value=(None, ecd.python_missing_message(), ecd.EXIT_PYTHON_MISSING),
        ):
            ok, msg, code = ecd.ensure_client_deps(log=lambda _m: None)
        self.assertFalse(ok)
        self.assertEqual(code, ecd.EXIT_PYTHON_MISSING)
        self.assertIn("python.org", msg)

    def test_pip_failure_exit_code(self):
        with mock.patch.object(ecd, "resolve_install_python", return_value=(["py", "-3.12"], "", ecd.EXIT_OK)):
            with mock.patch.object(ecd, "missing_imports", return_value=["websockets"]):
                with mock.patch.object(
                    ecd,
                    "_install_packages",
                    return_value=(False, "Failed to install…\npython.org"),
                ):
                    ok, msg, code = ecd.ensure_client_deps(log=lambda _m: None)
        self.assertFalse(ok)
        self.assertEqual(code, ecd.EXIT_PIP_FAILED)
        self.assertIn("python.org", msg)

    def test_requirements_file_exists_in_world(self):
        req = ecd.requirements_file()
        self.assertTrue(req.is_file(), req)
        text = req.read_text(encoding="utf-8")
        self.assertIn("websockets", text)
        self.assertIn("colorama", text)
        self.assertIn("PyYAML", text)
        self.assertIn("open-dread-rando", text)

    def test_client_imports_includes_odr(self):
        names = [name for name, _ in ecd.CLIENT_IMPORTS]
        self.assertIn("open_dread_rando", names)
        reqs = dict(ecd.CLIENT_IMPORTS)
        self.assertTrue(reqs["open_dread_rando"].startswith("open-dread-rando"))

    def test_linux_resolve_uses_venv_not_system_pip(self):
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            vpy = world / ecd.VENV_DIRNAME / "bin" / "python"
            with mock.patch.object(ecd, "uses_linux_venv", return_value=True):
                with mock.patch.object(
                    ecd,
                    "ensure_linux_venv",
                    return_value=([str(vpy)], ""),
                ) as make_venv:
                    with mock.patch.object(ecd, "_probe", return_value=True):
                        cmd, err, code = ecd.resolve_install_python(
                            ["python3"],
                            world=world,
                            log=logs.append,
                        )
        self.assertEqual(code, ecd.EXIT_OK)
        self.assertEqual(err, "")
        self.assertEqual(cmd, [str(vpy)])
        make_venv.assert_called_once()
        self.assertTrue(str(vpy).endswith(f"{ecd.VENV_DIRNAME}/bin/python") or ecd.VENV_DIRNAME in str(vpy))

    def test_linux_pip_failure_mentions_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            with mock.patch.object(ecd, "uses_linux_venv", return_value=True):
                msg = ecd.pip_failure_message(
                    [str(world / ecd.VENV_DIRNAME / "bin" / "python")],
                    world=world,
                    detail="nope",
                )
        self.assertIn(ecd.VENV_DIRNAME, msg)
        self.assertIn("not systemwide", msg)
        self.assertIn("nope", msg)


class ManagedPythonTests(unittest.TestCase):
    def test_find_base_python_prefers_dread_hub_python_env(self):
        with mock.patch.dict(os.environ, {"DREAD_HUB_PYTHON": r"C:\managed\python.exe"}):
            with mock.patch.object(ecd, "_probe", return_value=True) as probe:
                with mock.patch.object(
                    ecd, "_managed_python_cmd", wraps=ecd._managed_python_cmd
                ):
                    # Force env path through _managed_python_cmd
                    cmd = ecd._managed_python_cmd()
        self.assertEqual(cmd, [r"C:\managed\python.exe"])
        probe.assert_called()

    def test_find_client_python_uses_managed_on_windows(self):
        with mock.patch.object(ecd, "uses_linux_venv", return_value=False):
            with mock.patch.object(
                ecd, "_managed_python_cmd", return_value=[r"C:\tools\python-3.12\python.exe"]
            ):
                with mock.patch.object(ecd, "find_base_python") as base:
                    out = ecd.find_client_python()
        self.assertEqual(out, [r"C:\tools\python-3.12\python.exe"])
        base.assert_not_called()


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

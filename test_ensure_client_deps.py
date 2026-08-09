"""
Unit tests for ensure_client_deps (no network / no real pip install).

Run:
  py -3.12 -m worlds.metroid_dread.test_ensure_client_deps
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worlds.metroid_dread import ensure_client_deps as ecd  # noqa: E402


class MessageTests(unittest.TestCase):
    def test_python_missing_mentions_path_and_py_install(self):
        msg = ecd.python_missing_message()
        self.assertIn("3.11–3.13", msg)
        self.assertIn("python.org", msg)
        self.assertIn("Add python.exe to PATH", msg)
        self.assertIn("py install 3.12", msg)

    def test_pip_failure_includes_manual_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            req = world / "requirements-client.txt"
            req.write_text("websockets>=13\n", encoding="utf-8")
            msg = ecd.pip_failure_message(["py", "-3.12"], req_path=req, detail="boom")
            self.assertIn("py -3.12 -m pip install -r", msg)
            self.assertIn("requirements-client.txt", msg)
            self.assertIn("python.org", msg)
            self.assertIn("boom", msg)


class EnsureLogicTests(unittest.TestCase):
    def test_ok_when_nothing_missing(self):
        with mock.patch.object(ecd, "find_client_python", return_value=["py", "-3.12"]):
            with mock.patch.object(ecd, "missing_imports", return_value=[]):
                with mock.patch.object(ecd, "_install_packages") as install:
                    ok, msg, code = ecd.ensure_client_deps(log=lambda _m: None)
        self.assertTrue(ok)
        self.assertEqual(code, ecd.EXIT_OK)
        install.assert_not_called()
        self.assertIn("OK", msg)

    def test_installs_when_missing(self):
        with mock.patch.object(ecd, "find_client_python", return_value=["py", "-3.12"]):
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

    def test_python_missing_exit_code(self):
        with mock.patch.object(ecd, "find_client_python", return_value=None):
            ok, msg, code = ecd.ensure_client_deps(log=lambda _m: None)
        self.assertFalse(ok)
        self.assertEqual(code, ecd.EXIT_PYTHON_MISSING)
        self.assertIn("python.org", msg)

    def test_pip_failure_exit_code(self):
        with mock.patch.object(ecd, "find_client_python", return_value=["py", "-3.12"]):
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


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

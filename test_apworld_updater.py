"""
Unit tests for apworld_updater (mocked network; no real GitHub calls).

Run:
  py -3.12 -m worlds.metroid_bread.test_apworld_updater
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worlds.metroid_bread import apworld_updater as au  # noqa: E402


def _make_apworld(path: Path, version: str) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        manifest = json.dumps(
            {"game": "Metroid Bread", "world_version": version},
            indent=4,
        )
        zf.writestr("metroid_bread/archipelago.json", manifest)
        zf.writestr("metroid_bread/dummy.txt", "ok")
    path.write_bytes(buf.getvalue())


class SemverTests(unittest.TestCase):
    def test_normalize_strips_v(self):
        self.assertEqual(au.normalize_version("v1.2.3"), "1.2.3")
        self.assertEqual(au.normalize_version("1.2.3"), "1.2.3")

    def test_compare(self):
        self.assertEqual(au.compare_versions("1.6.6", "1.6.6"), 0)
        self.assertEqual(au.compare_versions("1.7.0", "1.6.9"), 1)
        self.assertEqual(au.compare_versions("1.6.0", "1.7.0"), -1)
        self.assertEqual(au.compare_versions("v2.0.0", "1.9.9"), 1)


class CheckForUpdateTests(unittest.TestCase):
    def test_no_install_when_remote_older_or_equal(self):
        release = {
            "tag_name": "1.6.0",
            "prerelease": False,
            "draft": False,
            "html_url": "https://example.test/releases/1.6.0",
            "assets": [
                {
                    "name": "metroid_bread.apworld",
                    "browser_download_url": "https://example.test/a.apworld",
                }
            ],
        }
        with mock.patch.object(au, "fetch_latest_release", return_value=release):
            result = au.check_for_update(local_version="1.7.0")
        self.assertTrue(result.ok)
        self.assertFalse(result.update_available)
        self.assertEqual(result.remote_version, "1.6.0")

    def test_update_when_remote_newer(self):
        release = {
            "tag_name": "v1.8.0",
            "prerelease": False,
            "draft": False,
            "html_url": "https://example.test/releases/1.8.0",
            "assets": [
                {
                    "name": "metroid_bread.apworld",
                    "browser_download_url": "https://example.test/a.apworld",
                }
            ],
        }
        with mock.patch.object(au, "fetch_latest_release", return_value=release):
            result = au.check_for_update(local_version="1.7.0")
        self.assertTrue(result.ok)
        self.assertTrue(result.update_available)
        self.assertEqual(result.remote_version, "1.8.0")
        self.assertTrue(result.download_url.endswith("a.apworld"))

    def test_soft_fail_network(self):
        with mock.patch.object(au, "fetch_latest_release", return_value=None):
            result = au.check_for_update(local_version="1.0.0")
        self.assertFalse(result.ok)
        self.assertFalse(result.update_available)
        self.assertEqual(result.error, "network_or_prerelease")

    def test_ignores_prerelease_via_fetch(self):
        # fetch_latest_release itself returns None for prerelease
        with mock.patch.object(au, "fetch_latest_release", return_value=None):
            result = au.check_for_update(local_version="0.0.1")
        self.assertFalse(result.update_available)


class InstallTests(unittest.TestCase):
    def test_backup_and_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            existing = dest_dir / au.ASSET_NAME
            _make_apworld(existing, "1.0.0")
            new_bytes = io.BytesIO()
            with zipfile.ZipFile(new_bytes, "w") as zf:
                zf.writestr(
                    "metroid_bread/archipelago.json",
                    json.dumps({"game": "Metroid Bread", "world_version": "1.2.0"}),
                )
            payload = new_bytes.getvalue()

            class FakeResp:
                headers = {"Content-Length": str(len(payload))}

                def read(self, n=-1):
                    if not hasattr(self, "_data"):
                        self._data = payload
                    chunk, self._data = self._data[:n], self._data[n:]
                    return chunk

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            with mock.patch.object(au.urllib.request, "urlopen", return_value=FakeResp()):
                with mock.patch.object(au, "invalidate_hub_runtime_stamp"):
                    ok, msg = au.download_and_install(
                        "https://example.test/new.apworld",
                        expected_version="1.2.0",
                        dest_dir=dest_dir,
                    )
            self.assertTrue(ok, msg)
            self.assertTrue((dest_dir / f"{au.ASSET_NAME}.bak").is_file())
            self.assertEqual(
                au.read_world_version_from_apworld(dest_dir / au.ASSET_NAME),
                "1.2.0",
            )
            self.assertFalse((dest_dir / f"{au.ASSET_NAME}.partial").exists())

    def test_reject_bad_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)

            class FakeResp:
                headers = {}

                def read(self, n=-1):
                    if not hasattr(self, "_sent"):
                        self._sent = True
                        return b"not a zip"
                    return b""

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            with mock.patch.object(au.urllib.request, "urlopen", return_value=FakeResp()):
                ok, msg = au.download_and_install(
                    "https://example.test/bad.apworld",
                    dest_dir=dest_dir,
                )
            self.assertFalse(ok)
            self.assertIn("valid zip", msg.lower())
            self.assertFalse((dest_dir / au.ASSET_NAME).exists())


class LocalVersionTests(unittest.TestCase):
    def test_reads_folder_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            (world / "archipelago.json").write_text(
                json.dumps({"game": "Metroid Bread", "world_version": "9.9.9"}),
                encoding="utf-8",
            )
            self.assertEqual(au.read_local_world_version(world), "9.9.9")


if __name__ == "__main__":
    unittest.main()

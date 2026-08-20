#!/usr/bin/env python3
"""
Check GitHub Releases for a newer metroid_bread.apworld and install it.

Source: Dummydud3/metroid-dread-apworld releases/latest (asset metroid_bread.apworld).
Prompts before download; soft-fails on network errors; ignores prereleases.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

logger = logging.getLogger("MetroidBread.ApworldUpdater")

GITHUB_OWNER = "Dummydud3"
GITHUB_REPO = "metroid-dread-apworld"
# Installed filename is always metroid_bread.apworld (coexists with other dread worlds).
ASSET_NAME = "metroid_bread.apworld"
# Prefer new GitHub asset; fall back to legacy name if a release only ships the old file.
LEGACY_ASSET_NAME = "metroid_dread.apworld"
ASSET_CANDIDATES = (ASSET_NAME, LEGACY_ASSET_NAME)
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
API_LATEST_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
USER_AGENT = "MetroidBread-ApworldUpdater/1.0"
HTTP_TIMEOUT_SEC = 15
DOWNLOAD_TIMEOUT_SEC = 120
WORLD_DIR = Path(__file__).resolve().parent
MANIFEST_IN_ZIP = "metroid_bread/archipelago.json"
LEGACY_MANIFEST_IN_ZIP = "metroid_dread/archipelago.json"
MANIFEST_CANDIDATES = (MANIFEST_IN_ZIP, LEGACY_MANIFEST_IN_ZIP, "archipelago.json")
BACKUP_SUFFIX = ".bak"
PARTIAL_SUFFIX = ".partial"

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, Optional[int]], None]


@dataclass
class UpdateCheckResult:
    ok: bool
    update_available: bool
    local_version: str
    remote_version: str
    download_url: str
    releases_url: str
    message: str
    error: str = ""
    prerelease: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_version(version: str) -> str:
    text = (version or "").strip()
    if text.lower().startswith("v") and len(text) > 1 and text[1].isdigit():
        text = text[1:]
    return text.strip()


def parse_semver(version: str) -> Tuple[int, ...]:
    """Parse major.minor.build… into ints; non-numeric tails become 0."""
    text = normalize_version(version)
    if not text:
        return (0, 0, 0)
    parts = []
    for piece in text.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def compare_versions(left: str, right: str) -> int:
    """Return -1 / 0 / 1 for left < / == / > right (semver-ish)."""
    a = parse_semver(left)
    b = parse_semver(right)
    # Pad to equal length
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def custom_worlds_dir() -> Path:
    """Writable Archipelago custom_worlds folder (user_path / local_path / cwd)."""
    try:
        from Utils import user_path

        return Path(user_path("custom_worlds"))
    except Exception:
        pass
    try:
        from Utils import local_path

        return Path(local_path()) / "custom_worlds"
    except Exception:
        return Path.cwd() / "custom_worlds"


def installed_apworld_path(dest_dir: Optional[Path] = None) -> Path:
    return (dest_dir or custom_worlds_dir()) / ASSET_NAME


def read_world_version_from_json(path: Path) -> Optional[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    ver = data.get("world_version")
    if isinstance(ver, str) and ver.strip():
        return normalize_version(ver)
    return None


def read_world_version_from_apworld(apworld: Path) -> Optional[str]:
    if not apworld.is_file():
        return None
    try:
        with zipfile.ZipFile(apworld, "r") as zf:
            # Prefer packaged path; also accept bare archipelago.json.
            for member in MANIFEST_CANDIDATES:
                try:
                    raw = zf.read(member)
                except KeyError:
                    continue
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    ver = data.get("world_version")
                    if isinstance(ver, str) and ver.strip():
                        return normalize_version(ver)
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def read_local_world_version(
    world_dir: Optional[Path] = None,
    *,
    apworld: Optional[Path] = None,
) -> str:
    """
    Local world_version: folder archipelago.json, else installed/containing apworld.
    """
    base = Path(world_dir) if world_dir is not None else WORLD_DIR
    folder_ver = read_world_version_from_json(base / "archipelago.json")
    if folder_ver:
        return folder_ver

    candidates = []
    if apworld is not None:
        candidates.append(Path(apworld))
    candidates.append(installed_apworld_path())
    try:
        from hub_launcher import find_containing_apworld
    except ImportError:
        try:
            from worlds.metroid_bread.hub_launcher import find_containing_apworld
        except ImportError:
            find_containing_apworld = None  # type: ignore
    if find_containing_apworld is not None:
        found = find_containing_apworld(base)
        if found is not None:
            candidates.append(found)

    for path in candidates:
        ver = read_world_version_from_apworld(path)
        if ver:
            return ver
    return "0.0.0"


def _http_get_json(url: str, *, timeout: float = HTTP_TIMEOUT_SEC) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8"))


def fetch_latest_release() -> Optional[Dict[str, Any]]:
    """
    Return parsed GitHub releases/latest JSON, or None on soft failure / prerelease.
    """
    try:
        data = _http_get_json(API_LATEST_URL)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.info("GitHub release check failed (soft): %s", exc)
        return None
    except (json.JSONDecodeError, UnicodeError, TypeError, ValueError) as exc:
        logger.info("GitHub release JSON invalid (soft): %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    if data.get("prerelease") is True or data.get("draft") is True:
        logger.info("Ignoring prerelease/draft latest release")
        return None
    return data


def _asset_download_url(release: Dict[str, Any]) -> Optional[str]:
    """Prefer metroid_bread.apworld; fall back to legacy metroid_dread.apworld."""
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    by_name: Dict[str, str] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url")
        if isinstance(url, str) and url.strip() and name:
            by_name[name.lower()] = url.strip()
    for candidate in ASSET_CANDIDATES:
        url = by_name.get(candidate.lower())
        if url:
            return url
    return None


def check_for_update(
    *,
    world_dir: Optional[Path] = None,
    local_version: Optional[str] = None,
) -> UpdateCheckResult:
    """Compare local world_version to GitHub latest tag_name."""
    local = normalize_version(local_version or read_local_world_version(world_dir))
    releases_url = RELEASES_PAGE_URL
    release = fetch_latest_release()
    if release is None:
        return UpdateCheckResult(
            ok=False,
            update_available=False,
            local_version=local,
            remote_version="",
            download_url="",
            releases_url=releases_url,
            message="Could not reach GitHub Releases (network or no stable latest).",
            error="network_or_prerelease",
        )

    remote = normalize_version(str(release.get("tag_name") or ""))
    html_url = release.get("html_url")
    if isinstance(html_url, str) and html_url.strip():
        releases_url = html_url.strip()
    download_url = _asset_download_url(release) or ""

    if not remote:
        return UpdateCheckResult(
            ok=False,
            update_available=False,
            local_version=local,
            remote_version="",
            download_url=download_url,
            releases_url=releases_url,
            message="Latest release has no tag_name.",
            error="missing_tag",
        )
    if not download_url:
        return UpdateCheckResult(
            ok=False,
            update_available=False,
            local_version=local,
            remote_version=remote,
            download_url="",
            releases_url=releases_url,
            message=f"Release {remote} has no {ASSET_NAME} (or {LEGACY_ASSET_NAME}) asset.",
            error="missing_asset",
        )

    newer = compare_versions(remote, local) > 0
    if newer:
        msg = f"Update available: {local} → {remote}."
    else:
        msg = f"Up to date (local {local}, latest {remote})."
    return UpdateCheckResult(
        ok=True,
        update_available=newer,
        local_version=local,
        remote_version=remote,
        download_url=download_url,
        releases_url=releases_url,
        message=msg,
    )


def verify_apworld_zip(
    path: Path,
    *,
    min_version: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Open path as zip; require archipelago.json. Returns (ok, message, version).
    """
    try:
        with zipfile.ZipFile(path, "r") as zf:
            member = None
            for name in MANIFEST_CANDIDATES:
                if name in zf.namelist():
                    member = name
                    break
            if member is None:
                # Case-insensitive / nested fallback
                for name in zf.namelist():
                    norm = name.replace("\\", "/")
                    if norm.endswith("archipelago.json"):
                        member = name
                        break
            if member is None:
                return False, "Downloaded file is missing archipelago.json", ""
            raw = zf.read(member)
            data = json.loads(raw.decode("utf-8"))
    except zipfile.BadZipFile:
        return False, "Downloaded file is not a valid zip/apworld", ""
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        return False, f"Could not verify apworld: {exc}", ""

    if not isinstance(data, dict):
        return False, "archipelago.json is not an object", ""
    ver = data.get("world_version")
    if not isinstance(ver, str) or not ver.strip():
        return False, "archipelago.json missing world_version", ""
    ver = normalize_version(ver)
    if min_version and compare_versions(ver, min_version) < 0:
        return (
            False,
            f"Downloaded world_version {ver} is older than expected {min_version}",
            ver,
        )
    return True, f"Verified apworld world_version={ver}", ver


def invalidate_hub_runtime_stamp() -> None:
    """Force Hub re-extract from apworld on next launch (stamp mismatch path)."""
    try:
        try:
            from hub_launcher import APWORLD_STAMP_NAME, runtime_world_dir
        except ImportError:
            from worlds.metroid_bread.hub_launcher import (
                APWORLD_STAMP_NAME,
                runtime_world_dir,
            )
        stamp = runtime_world_dir() / APWORLD_STAMP_NAME
        if stamp.is_file():
            stamp.unlink()
            logger.info("Removed Hub runtime stamp %s", stamp)
    except Exception as exc:
        logger.debug("Could not invalidate Hub runtime stamp: %s", exc)


def download_and_install(
    download_url: str,
    *,
    expected_version: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    progress_cb: Optional[ProgressFn] = None,
    log: Optional[LogFn] = None,
) -> Tuple[bool, str]:
    """
    Download to *.partial → verify zip → backup existing → replace → invalidate stamp.
    """
    def _log(msg: str) -> None:
        logger.info("%s", msg)
        if log:
            log(msg)

    url = (download_url or "").strip()
    if not url:
        return False, "No download URL"

    target_dir = Path(dest_dir) if dest_dir is not None else custom_worlds_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / ASSET_NAME
    partial = target_dir / f"{ASSET_NAME}{PARTIAL_SUFFIX}"
    backup = target_dir / f"{ASSET_NAME}{BACKUP_SUFFIX}"

    if partial.exists():
        try:
            partial.unlink()
        except OSError:
            pass

    _log(f"Downloading {ASSET_NAME}…")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            total_hdr = resp.headers.get("Content-Length")
            total = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
            written = 0
            with open(partial, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    if progress_cb:
                        progress_cb(written, total)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass
        return False, f"Download failed: {exc}"

    ok, verify_msg, got_ver = verify_apworld_zip(
        partial, min_version=expected_version
    )
    if not ok:
        try:
            partial.unlink()
        except OSError:
            pass
        return False, verify_msg
    _log(verify_msg)

    if dest.is_file():
        try:
            if backup.exists():
                backup.unlink()
        except OSError:
            pass
        try:
            shutil.copy2(dest, backup)
            _log(f"Backed up existing apworld → {backup.name}")
        except OSError as exc:
            try:
                partial.unlink()
            except OSError:
                pass
            return False, f"Could not backup existing apworld: {exc}"

    try:
        # Replace: remove dest then move partial into place (Windows-friendly).
        if dest.exists():
            dest.unlink()
        partial.replace(dest)
    except OSError as exc:
        # Try restore from backup
        if backup.is_file() and not dest.exists():
            try:
                shutil.copy2(backup, dest)
            except OSError:
                pass
        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass
        return False, f"Could not install apworld: {exc}"

    invalidate_hub_runtime_stamp()
    ver_note = f" ({got_ver})" if got_ver else ""
    return (
        True,
        f"Installed {ASSET_NAME}{ver_note}. Fully quit and relaunch Metroid Bread Client "
        f"(and Archipelago if open) so the new apworld loads.",
    )


def prompt_and_maybe_update(
    *,
    world_dir: Optional[Path] = None,
    log: Optional[LogFn] = None,
    parent: Any = None,
) -> UpdateCheckResult:
    """
    Check for update; if available, ask Yes / Not now / Open releases via tkinter.
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            logger.info("%s", msg)

    result = check_for_update(world_dir=world_dir)
    _log(result.message)
    if not result.ok or not result.update_available:
        return result

    try:
        from tkinter import messagebox
    except ImportError:
        _log("tkinter unavailable — skipping update prompt")
        return result

    # messagebox: Yes / No / Cancel mapped to Yes / Not now / Open releases
    choice = messagebox.askyesnocancel(
        "Metroid Bread apworld update",
        f"{result.message}\n\nDownload and install {ASSET_NAME}?\n\n"
        f"Yes = download\nNo = not now\nCancel = open releases page",
        parent=parent,
    )
    if choice is True:
        ok, msg = download_and_install(
            result.download_url,
            expected_version=result.remote_version,
            log=_log,
        )
        _log(msg)
        if ok:
            messagebox.showinfo(
                "Update installed",
                msg,
                parent=parent,
            )
        else:
            messagebox.showerror("Update failed", msg, parent=parent)
    elif choice is None:
        # Cancel → open releases
        try:
            import webbrowser

            webbrowser.open(result.releases_url or RELEASES_PAGE_URL)
        except Exception as exc:
            _log(f"Could not open browser: {exc}")
    # False = Not now
    return result


def _cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Metroid Bread apworld updater")
    parser.add_argument(
        "action",
        choices=("check", "install", "prompt"),
        help="check | install | prompt",
    )
    parser.add_argument("--url", default="", help="Asset download URL (install)")
    parser.add_argument("--expected-version", default="", help="Min version in zip")
    parser.add_argument(
        "--world-dir",
        default=str(WORLD_DIR),
        help="World package directory for local version",
    )
    parser.add_argument(
        "--dest-dir",
        default="",
        help="custom_worlds directory (default: resolve via Utils)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args(list(argv) if argv is not None else None)

    world_dir = Path(args.world_dir)
    dest_dir = Path(args.dest_dir) if args.dest_dir else None

    if args.action == "check":
        result = check_for_update(world_dir=world_dir)
        if args.json:
            print(json.dumps(result.to_dict()))
        else:
            print(result.message)
        return 0 if result.ok else 2

    if args.action == "prompt":
        result = prompt_and_maybe_update(world_dir=world_dir)
        if args.json:
            print(json.dumps(result.to_dict()))
        return 0 if result.ok else 2

    # install
    url = args.url.strip()
    if not url:
        check = check_for_update(world_dir=world_dir)
        if not check.ok or not check.update_available:
            payload = {
                "ok": False,
                "message": check.message,
                "error": check.error or "no_update",
            }
            print(json.dumps(payload) if args.json else check.message)
            return 1
        url = check.download_url
        expected = check.remote_version
    else:
        expected = args.expected_version.strip() or None

    ok, msg = download_and_install(
        url,
        expected_version=expected,
        dest_dir=dest_dir,
    )
    payload = {"ok": ok, "message": msg}
    print(json.dumps(payload) if args.json else msg)
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(_cli())

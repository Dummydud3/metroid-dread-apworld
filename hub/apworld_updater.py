#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import shutil
import ssl
import sys
import urllib.error
import urllib.request
import zipfile
from contextlib import suppress
from dataclasses import asdict, dataclass
from itertools import takewhile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dread_paths
dread_paths.ensure_import_paths()

logger = logging.getLogger("MetroidBread.ApworldUpdater")
GITHUB_OWNER = "Dummydud3"
GITHUB_REPO = "metroid-dread-apworld"
ASSET_NAME = "metroid_bread.apworld"
LEGACY_ASSET_NAME = "metroid_dread.apworld"
ASSET_CANDIDATES = (ASSET_NAME, LEGACY_ASSET_NAME)
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
API_LATEST_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
API_RELEASES_LIST_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=15"
USER_AGENT = "MetroidBread-ApworldUpdater/1.0"
HTTP_TIMEOUT_SEC = 15
DOWNLOAD_TIMEOUT_SEC = 120
WORLD_DIR = Path(__file__).resolve().parents[1]
MANIFEST_IN_ZIP = "metroid_bread/archipelago.json"
LEGACY_MANIFEST_IN_ZIP = "metroid_dread/archipelago.json"
MANIFEST_CANDIDATES = (MANIFEST_IN_ZIP, LEGACY_MANIFEST_IN_ZIP, "archipelago.json")
BACKUP_SUFFIX = ".bak"
PARTIAL_SUFFIX = ".partial"
LogFn = Callable[[str], None]
ProgressFn = Callable[[int, Optional[int]], None]


@dataclass
class UpdateCheckResult:
    ok: bool = False
    update_available: bool = False
    local_version: str = ""
    remote_version: str = ""
    download_url: str = ""
    releases_url: str = RELEASES_PAGE_URL
    message: str = ""
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
    parts = [int("".join(takewhile(str.isdigit, piece)) or "0")
             for piece in normalize_version(version).split(".")]
    return tuple(parts + [0] * max(0, 3 - len(parts)))


def compare_versions(left: str, right: str) -> int:
    a, b = parse_semver(left), parse_semver(right)
    length = max(len(a), len(b))
    a, b = a + (0,) * (length - len(a)), b + (0,) * (length - len(b))
    return (a > b) - (a < b)


def custom_worlds_dir() -> Path:
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


def _manifest_version(raw: bytes) -> str:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("archipelago.json is not an object")
    version = data.get("world_version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("archipelago.json missing world_version")
    return normalize_version(version)


def read_world_version_from_json(path: Path) -> Optional[str]:
    with suppress(OSError, ValueError, UnicodeError):
        return _manifest_version(path.read_bytes())
    return None


def _archive_version(path: Path, *, strict: bool) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        members = [name for name in MANIFEST_CANDIDATES if name in names]
        if strict and not members:
            members = [name for name in names if name.replace("\\", "/").endswith("archipelago.json")]
        for member in members:
            if strict:
                return _manifest_version(archive.read(member))
            with suppress(ValueError, UnicodeError):
                return _manifest_version(archive.read(member))
    raise ValueError("Downloaded file is missing archipelago.json")


def read_world_version_from_apworld(apworld: Path) -> Optional[str]:
    with suppress(OSError, zipfile.BadZipFile, ValueError, UnicodeError):
        return _archive_version(apworld, strict=False)
    return None


def read_local_world_version(world_dir: Optional[Path] = None, *, apworld: Optional[Path] = None) -> str:
    base = Path(world_dir) if world_dir is not None else WORLD_DIR
    folder_version = read_world_version_from_json(base / "archipelago.json")
    if folder_version:
        return folder_version
    candidates = ([Path(apworld)] if apworld is not None else []) + [installed_apworld_path()]
    try:
        from worlds.metroid_bread.hub.hub_launcher import find_containing_apworld
    except ImportError:
        pass
    else:
        found = find_containing_apworld(base)
        if found is not None:
            candidates.append(found)
    for path in candidates:
        version = read_world_version_from_apworld(path)
        if version:
            return version
    return "0.0.0"


def _ssl_context() -> ssl.SSLContext:
    with suppress(Exception):
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _http_get_json(url: str, *, timeout: float = HTTP_TIMEOUT_SEC) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_error_detail(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = ""
        with suppress(Exception):
            body = (exc.read() or b"")[:200].decode("utf-8", errors="replace").strip()
        extra = f" — {body}" if body else ""
        return f"HTTP {exc.code} {exc.reason}{extra}"
    if isinstance(exc, urllib.error.URLError):
        return f"URL error: {getattr(exc, 'reason', exc)}"
    return f"{type(exc).__name__}: {exc}"


def _pick_stable_release(data: Any) -> Optional[Dict[str, Any]]:
    releases = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
    return next((item for item in releases if isinstance(item, dict)
                 and item.get("prerelease") is not True and item.get("draft") is not True), None)


def fetch_latest_release() -> Tuple[Optional[Dict[str, Any]], str]:
    last_error = ""
    for url in (API_LATEST_URL, API_RELEASES_LIST_URL):
        try:
            release = _pick_stable_release(_http_get_json(url))
            if release is not None:
                return release, ""
            if url == API_LATEST_URL:
                last_error = "latest release is draft/prerelease"
                continue
            return None, f"{last_error}; release list has no non-prerelease builds. See {RELEASES_PAGE_URL}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            detail = _http_error_detail(exc)
        except (UnicodeError, TypeError, ValueError) as exc:
            detail = f"invalid JSON: {exc}"
            if url == API_LATEST_URL:
                logger.info("GitHub release JSON invalid (soft): %s", exc)
                return None, detail
        logger.info("GitHub %s failed (soft): %s", url, detail)
        if url == API_RELEASES_LIST_URL:
            return None, f"{last_error}; list fallback: {detail}" if last_error else detail
        last_error = detail
    return None, last_error


def _asset_download_url(release: Dict[str, Any]) -> Optional[str]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    by_name = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name, url = str(asset.get("name") or ""), asset.get("browser_download_url")
        if name and isinstance(url, str) and url.strip():
            by_name[name.lower()] = url.strip()
    return next((by_name[name.lower()] for name in ASSET_CANDIDATES if name.lower() in by_name), None)


def check_for_update(*, world_dir: Optional[Path] = None, local_version: Optional[str] = None) -> UpdateCheckResult:
    result = UpdateCheckResult(local_version=normalize_version(local_version or read_local_world_version(world_dir)))
    release, fetch_error = fetch_latest_release()
    if release is None:
        detail = (fetch_error or "unknown error").strip()
        result.error = detail or "network_or_prerelease"
        if "CERTIFICATE" in detail.upper() or "SSL" in detail.upper():
            result.message = ("SSL/certificate error talking to api.github.com. "
                              "Install/update certifi for this Python, or open Releases in a browser.")
        elif "403" in detail or "rate limit" in detail.lower():
            result.message = ("GitHub API rate-limited or blocked this request. "
                              "Try again later, or open Releases in a browser.")
        elif "no stable" in detail.lower() or "prerelease" in detail.lower():
            result.message = f"No stable (non-prerelease) GitHub Release found. See {RELEASES_PAGE_URL}"
        else:
            result.message = f"Could not reach GitHub Releases. Detail: {detail[:240]}"
        return result
    result.remote_version = normalize_version(str(release.get("tag_name") or ""))
    html_url = release.get("html_url")
    if isinstance(html_url, str) and html_url.strip():
        result.releases_url = html_url.strip()
    result.download_url = _asset_download_url(release) or ""
    if not result.remote_version:
        result.message, result.error = "Latest release has no tag_name.", "missing_tag"
    elif not result.download_url:
        result.message = f"Release {result.remote_version} has no {ASSET_NAME} (or {LEGACY_ASSET_NAME}) asset."
        result.error = "missing_asset"
    else:
        result.ok = True
        result.update_available = compare_versions(result.remote_version, result.local_version) > 0
        result.message = (f"Update available: {result.local_version} → {result.remote_version}." if result.update_available
                          else f"Up to date (local {result.local_version}, latest {result.remote_version}).")
    return result


def verify_apworld_zip(path: Path, *, min_version: Optional[str] = None) -> Tuple[bool, str, str]:
    try:
        version = _archive_version(path, strict=True)
    except zipfile.BadZipFile:
        return False, "Downloaded file is not a valid zip/apworld", ""
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        return False, f"Could not verify apworld: {exc}", ""
    except ValueError as exc:
        return False, str(exc), ""
    if min_version and compare_versions(version, min_version) < 0:
        return False, f"Downloaded world_version {version} is older than expected {min_version}", version
    return True, f"Verified apworld world_version={version}", version


def invalidate_hub_runtime_stamp() -> None:
    try:
        from worlds.metroid_bread.hub.hub_launcher import APWORLD_STAMP_NAME, runtime_world_dir
        stamp = runtime_world_dir() / APWORLD_STAMP_NAME
        if stamp.is_file():
            stamp.unlink()
            logger.info("Removed Hub runtime stamp %s", stamp)
    except Exception as exc:
        logger.debug("Could not invalidate Hub runtime stamp: %s", exc)


def download_and_install(download_url: str, *, expected_version: Optional[str] = None,
                         dest_dir: Optional[Path] = None, progress_cb: Optional[ProgressFn] = None,
                         log: Optional[LogFn] = None) -> Tuple[bool, str]:
    def report(message: str) -> None:
        logger.info("%s", message)
        if log:
            log(message)

    url = (download_url or "").strip()
    if not url:
        return False, "No download URL"
    target_dir = Path(dest_dir) if dest_dir is not None else custom_worlds_dir()
    dest = target_dir / ASSET_NAME
    partial, backup = dest.with_name(dest.name + PARTIAL_SUFFIX), dest.with_name(dest.name + BACKUP_SUFFIX)
    failure = "Download failed"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            partial.unlink()
        report(f"Downloading {ASSET_NAME}…")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SEC, context=_ssl_context()) as response:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            written = 0
            with partial.open("wb") as output:
                while chunk := response.read(1024 * 256):
                    output.write(chunk)
                    written += len(chunk)
                    if progress_cb:
                        progress_cb(written, total)
        ok, message, version = verify_apworld_zip(partial, min_version=expected_version)
        if not ok:
            return False, message
        report(message)
        failure = "Could not backup existing apworld"
        if dest.is_file():
            with suppress(OSError):
                backup.unlink()
            shutil.copy2(dest, backup)
            report(f"Backed up existing apworld → {backup.name}")
        failure = "Could not install apworld"
        partial.replace(dest)
        invalidate_hub_runtime_stamp()
        ver_note = f" ({version})" if version else ""
        return True, (f"Installed {ASSET_NAME}{ver_note}. Fully quit and relaunch Metroid Bread Client "
                      "(and Archipelago if open) so the new apworld loads.")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if failure == "Could not install apworld" and backup.is_file() and not dest.exists():
            with suppress(OSError):
                shutil.copy2(backup, dest)
        return False, f"{failure}: {exc}"
    finally:
        with suppress(OSError):
            partial.unlink()


def prompt_and_maybe_update(*, world_dir: Optional[Path] = None, log: Optional[LogFn] = None,
                            parent: Any = None) -> UpdateCheckResult:
    report = log or (lambda message: logger.info("%s", message))
    result = check_for_update(world_dir=world_dir)
    report(result.message)
    if not result.ok or not result.update_available:
        return result
    try:
        from tkinter import messagebox
    except ImportError:
        report("tkinter unavailable — skipping update prompt")
        return result
    choice = messagebox.askyesnocancel(
        "Metroid Bread apworld update",
        f"{result.message}\n\nDownload and install {ASSET_NAME}?\n\n"
        "Yes = download\nNo = not now\nCancel = open releases page", parent=parent)
    if choice is True:
        ok, message = download_and_install(result.download_url, expected_version=result.remote_version, log=report)
        report(message)
        show = messagebox.showinfo if ok else messagebox.showerror
        show("Update installed" if ok else "Update failed", message, parent=parent)
    elif choice is None:
        try:
            import webbrowser
            webbrowser.open(result.releases_url or RELEASES_PAGE_URL)
        except Exception as exc:
            report(f"Could not open browser: {exc}")
    return result


def _cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Metroid Bread apworld updater")
    parser.add_argument("action", choices=("check", "install", "prompt"), help="check | install | prompt")
    parser.add_argument("--url", default="", help="Asset download URL (install)")
    parser.add_argument("--expected-version", default="", help="Min version in zip")
    parser.add_argument("--world-dir", default=str(WORLD_DIR), help="World package directory for local version")
    parser.add_argument("--dest-dir", default="", help="custom_worlds directory (default: resolve via Utils)")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args(list(argv) if argv is not None else None)
    world_dir = Path(args.world_dir)
    if args.action in ("check", "prompt"):
        action = check_for_update if args.action == "check" else prompt_and_maybe_update
        result = action(world_dir=world_dir)
        if args.json or args.action == "check":
            print(json.dumps(result.to_dict()) if args.json else result.message)
        return 0 if result.ok else 2
    url, expected = args.url.strip(), args.expected_version.strip() or None
    if not url:
        check = check_for_update(world_dir=world_dir)
        if not check.ok or not check.update_available:
            payload = {"ok": False, "message": check.message, "error": check.error or "no_update"}
            print(json.dumps(payload) if args.json else check.message)
            return 1
        url, expected = check.download_url, check.remote_version
    ok, message = download_and_install(url, expected_version=expected,
                                      dest_dir=Path(args.dest_dir) if args.dest_dir else None)
    print(json.dumps({"ok": ok, "message": message}) if args.json else message)
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(_cli())

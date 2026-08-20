#!/usr/bin/env python3
"""
Download a portable Node.js 24 toolchain into the Metroid Bread runtime tools dir.

Used by the Hub Setup Wizard and hub_launcher.find_node / find_npm preference.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple

NODE_DIST_LATEST_V24 = "https://nodejs.org/dist/latest-v24.x/"
NODE_BROWSER_FALLBACK = NODE_DIST_LATEST_V24
WINGET_NODE_IDS = ("OpenJS.NodeJS.24", "OpenJS.NodeJS")

LogFn = Callable[[str], None]


def _log(log: Optional[LogFn], msg: str) -> None:
    if log:
        log(msg)
    else:
        print(msg, flush=True)


def node_archive_suffix(plat: Optional[str] = None, machine: Optional[str] = None) -> str:
    """Archive suffix under nodejs.org/dist (e.g. win-x64.zip)."""
    plat = plat or sys.platform
    machine = (machine or platform.machine()).lower()
    arm = machine in ("arm64", "aarch64")
    if plat in ("win32", "cygwin", "msys"):
        return "win-arm64.zip" if arm else "win-x64.zip"
    if plat == "darwin":
        return "darwin-arm64.tar.gz" if arm else "darwin-x64.tar.gz"
    return "linux-arm64.tar.xz" if arm else "linux-x64.tar.xz"


def resolve_node24_archive_url(
    *,
    plat: Optional[str] = None,
    machine: Optional[str] = None,
    opener=None,
) -> Tuple[str, str]:
    """
    Return (url, filename) for the latest Node 24 archive for this platform.

    Parses SHASUMS256.txt under latest-v24.x (no hard-coded patch version).
    """
    suffix = node_archive_suffix(plat, machine)
    shasums_url = NODE_DIST_LATEST_V24 + "SHASUMS256.txt"
    fetch = opener or urllib.request.urlopen
    with fetch(shasums_url, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    pattern = re.compile(rf"\b(node-v24\.\d+\.\d+-{re.escape(suffix)})\b")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            name = match.group(1)
            return NODE_DIST_LATEST_V24 + name, name
    raise RuntimeError(
        f"Could not find Node 24 archive ending in {suffix} under {NODE_DIST_LATEST_V24}"
    )


def _download_file(url: str, dest: Path, *, log: Optional[LogFn] = None) -> None:
    _log(log, f"Downloading {url} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "MetroidBread-HubSetup/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        read = 0
        last_pct = -1
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            read += len(chunk)
            if total > 0:
                pct = int(read * 100 / total)
                if pct >= last_pct + 10 or pct == 100:
                    _log(log, f"  … {pct}% ({read // (1024 * 1024)} MiB)")
                    last_pct = pct
    _log(log, f"Saved {dest.name} ({dest.stat().st_size // (1024 * 1024)} MiB)")


def _extract_archive(archive: Path, dest_dir: Path, *, log: Optional[LogFn] = None) -> None:
    _log(log, f"Extracting {archive.name} → {dest_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest_dir)
    elif name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest_dir)
    elif name.endswith(".tar.xz"):
        with tarfile.open(archive, "r:xz") as tf:
            tf.extractall(dest_dir)
    else:
        raise RuntimeError(f"Unsupported Node archive type: {archive.name}")


def _flatten_extracted_node(extract_root: Path, dest: Path) -> Path:
    """
    Node zips extract to node-v24.x.x-<plat>/ containing node.exe / bin/node.
    Move that tree to dest (replace existing).
    """
    candidates = []
    if (extract_root / "node.exe").is_file() or (extract_root / "bin" / "node").is_file():
        candidates.append(extract_root)
    for child in sorted(extract_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "node.exe").is_file() or (child / "bin" / "node").is_file():
            candidates.append(child)
    if not candidates:
        raise RuntimeError(f"No node binary found after extract under {extract_root}")
    src = candidates[0]
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src == extract_root:
        # Already flat enough — copy tree
        shutil.copytree(src, dest)
    else:
        shutil.move(str(src), str(dest))
    return dest


def find_node_in_dir(root: Path) -> Optional[Path]:
    if not root.is_dir():
        return None
    if os.name == "nt":
        for rel in ("node.exe",):
            p = root / rel
            if p.is_file():
                return p
    else:
        for rel in ("bin/node", "node"):
            p = root / rel
            if p.is_file():
                return p
    # Nested leftover
    pattern = "node.exe" if os.name == "nt" else "node"
    for p in root.rglob(pattern):
        if p.is_file() and p.name == pattern:
            return p
    return None


def find_npm_in_dir(root: Path) -> Optional[Path]:
    if not root.is_dir():
        return None
    if os.name == "nt":
        for name in ("npm.cmd", "npm.exe"):
            p = root / name
            if p.is_file():
                return p
    else:
        for rel in ("bin/npm", "npm"):
            p = root / rel
            if p.is_file():
                return p
    return None


def open_node_download_page() -> None:
    import webbrowser

    webbrowser.open(NODE_BROWSER_FALLBACK)


def try_winget_install_node(*, log: Optional[LogFn] = None) -> bool:
    if os.name != "nt":
        return False
    winget = shutil.which("winget")
    if not winget:
        _log(log, "winget not found; skipping winget Node install.")
        return False
    for pkg_id in WINGET_NODE_IDS:
        _log(log, f"Trying winget install -e --id {pkg_id} ...")
        try:
            proc = subprocess.run(
                [
                    winget,
                    "install",
                    "-e",
                    "--id",
                    pkg_id,
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                capture_output=True,
                text=True,
                timeout=600,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            _log(log, f"winget failed: {exc}")
            continue
        combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
        if proc.returncode == 0:
            _log(log, f"winget installed {pkg_id}.")
            return True
        _log(log, f"winget {pkg_id} exit {proc.returncode}: {combined[-800:]}")
    return False


def install_portable_node24(
    dest: Path,
    *,
    log: Optional[LogFn] = None,
    allow_winget_fallback: bool = True,
    allow_browser_fallback: bool = True,
) -> Tuple[bool, str]:
    """
    Download and extract Node 24 into dest.

    Returns (ok, message). On failure may open browser / try winget.
    """
    dest = Path(dest)
    existing = find_node_in_dir(dest)
    if existing is not None:
        _log(log, f"Managed Node already present: {existing}")
        return True, f"Managed Node already at {existing}"

    try:
        url, filename = resolve_node24_archive_url()
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        _log(log, f"Could not resolve Node 24 download URL: {exc}")
        if allow_winget_fallback and try_winget_install_node(log=log):
            return True, "Installed Node via winget (system PATH)."
        if allow_browser_fallback:
            _log(log, f"Opening browser: {NODE_BROWSER_FALLBACK}")
            open_node_download_page()
        return False, f"Could not resolve Node 24 download URL:\n{exc}"

    with tempfile.TemporaryDirectory(prefix="dread_node24_") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / filename
        extract_root = tmp_path / "extract"
        extract_root.mkdir()
        try:
            _download_file(url, archive, log=log)
            _extract_archive(archive, extract_root, log=log)
            _flatten_extracted_node(extract_root, dest)
        except (OSError, urllib.error.URLError, RuntimeError, tarfile.TarError, zipfile.BadZipFile) as exc:
            _log(log, f"Portable Node install failed: {exc}")
            if allow_winget_fallback and try_winget_install_node(log=log):
                return True, "Installed Node via winget (system PATH)."
            if allow_browser_fallback:
                _log(log, f"Opening browser: {NODE_BROWSER_FALLBACK}")
                open_node_download_page()
            return False, f"Portable Node 24 install failed:\n{exc}"

    node = find_node_in_dir(dest)
    if not node:
        return False, f"Extract finished but node binary missing under {dest}"
    _log(log, f"Portable Node 24 ready: {node}")
    return True, f"Installed portable Node 24 at {node}"


if __name__ == "__main__":
    # Dev helper: python ensure_portable_node.py [dest]
    dest_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools") / "node-v24"
    ok, msg = install_portable_node24(dest_arg)
    print(msg)
    raise SystemExit(0 if ok else 1)

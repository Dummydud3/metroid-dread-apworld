#!/usr/bin/env python3
"""
Download a managed CPython 3.12 (python-build-standalone install_only) into the
Metroid Bread runtime tools dir for Hub client use.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Pinned Astral python-build-standalone release (install_only). Bump when needed.
PBS_TAG = "20251209"
PBS_CPYTHON = "3.12.12"
PBS_DOWNLOAD_BASE = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    + PBS_TAG
    + "/"
)
PYTHON_ORG_312 = "https://www.python.org/downloads/release/python-31210/"
WINGET_PYTHON_ID = "Python.Python.3.12"

LogFn = Callable[[str], None]


def _log(log: Optional[LogFn], msg: str) -> None:
    if log:
        log(msg)
    else:
        print(msg, flush=True)


def pbs_target_triple(plat: Optional[str] = None, machine: Optional[str] = None) -> str:
    plat = plat or sys.platform
    machine = (machine or platform.machine()).lower()
    arm = machine in ("arm64", "aarch64")
    if plat in ("win32", "cygwin", "msys"):
        arch = "aarch64" if arm else "x86_64"
        return f"{arch}-pc-windows-msvc"
    if plat == "darwin":
        arch = "aarch64" if arm else "x86_64"
        return f"{arch}-apple-darwin"
    arch = "aarch64" if arm else "x86_64"
    return f"{arch}-unknown-linux-gnu"


def pbs_asset_name(plat: Optional[str] = None, machine: Optional[str] = None) -> str:
    triple = pbs_target_triple(plat, machine)
    return f"cpython-{PBS_CPYTHON}+{PBS_TAG}-{triple}-install_only.tar.gz"


def resolve_portable_python_url(
    *,
    plat: Optional[str] = None,
    machine: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (url, filename) for the install_only CPython 3.12 archive."""
    name = pbs_asset_name(plat, machine)
    # Prefer constructed URL (no API rate limits); verify via HEAD when possible.
    return PBS_DOWNLOAD_BASE + name, name


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


def find_python_in_dir(root: Path) -> Optional[Path]:
    if not root.is_dir():
        return None
    if os.name == "nt":
        for name in ("python.exe", "python3.exe"):
            p = root / name
            if p.is_file():
                return p
        # Nested python/ from install_only
        for name in ("python.exe", "python3.exe"):
            p = root / "python" / name
            if p.is_file():
                return p
    else:
        for rel in (
            "bin/python3.12",
            "bin/python3",
            "bin/python",
            "python/bin/python3.12",
            "python/bin/python3",
            "python/bin/python",
        ):
            p = root / rel
            if p.is_file():
                return p
    return None


def _flatten_extracted_python(extract_root: Path, dest: Path) -> Path:
    """
    install_only archives contain a top-level ``python/`` directory.
    Move that to dest (replace existing).
    """
    src = extract_root / "python"
    if not src.is_dir():
        # Already flat or unexpected layout — use extract_root if it has a binary
        if find_python_in_dir(extract_root):
            src = extract_root
        else:
            raise RuntimeError(f"No python/ tree in extract under {extract_root}")
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src == extract_root:
        shutil.copytree(src, dest)
    else:
        shutil.move(str(src), str(dest))
    return dest


def open_python_download_page() -> None:
    import webbrowser

    webbrowser.open(PYTHON_ORG_312)


def try_winget_install_python(*, log: Optional[LogFn] = None) -> bool:
    if os.name != "nt":
        return False
    winget = shutil.which("winget")
    if not winget:
        _log(log, "winget not found; skipping winget Python install.")
        return False
    _log(log, f"Trying winget install -e --id {WINGET_PYTHON_ID} ...")
    try:
        proc = subprocess.run(
            [
                winget,
                "install",
                "-e",
                "--id",
                WINGET_PYTHON_ID,
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
        return False
    if proc.returncode == 0:
        _log(log, f"winget installed {WINGET_PYTHON_ID}.")
        return True
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
    _log(log, f"winget exit {proc.returncode}: {combined[-800:]}")
    return False


def try_windows_official_silent_install(
    dest: Path,
    *,
    log: Optional[LogFn] = None,
) -> bool:
    """
    Alternate Windows path: official amd64 installer with TargetDir under tools/.
    May trigger UAC; best-effort only.
    """
    if os.name != "nt":
        return False
    # Prefer a recent 3.12.x installer URL (stable CDN).
    installer_url = (
        "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    )
    with tempfile.TemporaryDirectory(prefix="dread_py_msi_") as tmp:
        exe = Path(tmp) / "python-3.12.10-amd64.exe"
        try:
            _download_file(installer_url, exe, log=log)
            dest.mkdir(parents=True, exist_ok=True)
            _log(log, f"Running silent Python installer → {dest}")
            proc = subprocess.run(
                [
                    str(exe),
                    "/quiet",
                    f"TargetDir={dest}",
                    "InstallAllUsers=0",
                    "PrependPath=0",
                    "Include_pip=1",
                    "Include_tcltk=0",
                    "Include_test=0",
                ],
                capture_output=True,
                text=True,
                timeout=900,
                shell=False,
            )
        except (OSError, urllib.error.URLError, subprocess.TimeoutExpired) as exc:
            _log(log, f"Official silent installer failed: {exc}")
            return False
        if proc.returncode != 0:
            _log(log, f"Installer exit {proc.returncode}")
            return False
    return find_python_in_dir(dest) is not None


def install_portable_python312(
    dest: Path,
    *,
    log: Optional[LogFn] = None,
    allow_winget_fallback: bool = True,
    allow_browser_fallback: bool = True,
    allow_official_silent: bool = True,
) -> Tuple[bool, str]:
    """
    Download/extract managed CPython 3.12 into dest.

    Returns (ok, message).
    """
    dest = Path(dest)
    existing = find_python_in_dir(dest)
    if existing is not None:
        _log(log, f"Managed Python already present: {existing}")
        return True, f"Managed Python already at {existing}"

    url, filename = resolve_portable_python_url()
    with tempfile.TemporaryDirectory(prefix="dread_py312_") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / filename
        extract_root = tmp_path / "extract"
        extract_root.mkdir()
        try:
            _download_file(url, archive, log=log)
            _log(log, f"Extracting {filename} ...")
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(extract_root)
            _flatten_extracted_python(extract_root, dest)
        except (OSError, urllib.error.URLError, RuntimeError, tarfile.TarError) as exc:
            _log(log, f"python-build-standalone install failed: {exc}")
            if allow_official_silent and try_windows_official_silent_install(dest, log=log):
                py = find_python_in_dir(dest)
                return True, f"Installed Python 3.12 via official installer at {py}"
            if allow_winget_fallback and try_winget_install_python(log=log):
                return True, "Installed Python 3.12 via winget (system PATH)."
            if allow_browser_fallback:
                _log(log, f"Opening browser: {PYTHON_ORG_312}")
                open_python_download_page()
                if sys.platform.startswith("linux"):
                    _log(
                        log,
                        "Linux tip: install python 3.12 from your distro or deadsnakes, "
                        "then re-run Fix / Launch Hub.",
                    )
            return False, f"Portable Python 3.12 install failed:\n{exc}"

    py = find_python_in_dir(dest)
    if not py:
        return False, f"Extract finished but python binary missing under {dest}"
    _log(log, f"Portable Python 3.12 ready: {py}")
    return True, f"Installed portable Python 3.12 at {py}"


def managed_python_cmd_from_dir(root: Path) -> Optional[List[str]]:
    py = find_python_in_dir(root)
    if py is None:
        return None
    return [str(py)]


if __name__ == "__main__":
    dest_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools") / "python-3.12"
    ok, msg = install_portable_python312(dest_arg)
    print(msg)
    raise SystemExit(0 if ok else 1)

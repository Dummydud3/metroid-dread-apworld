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
from typing import Callable, Dict, List, Optional, Tuple

try:
    from win_subprocess import run_hidden
except ImportError:
    from worlds.metroid_bread.win_subprocess import run_hidden

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


def _python_prefix(python_exe: Path) -> Path:
    """Install prefix for a python binary (handles Windows flat layout and Unix bin/)."""
    python_exe = Path(python_exe)
    parent = python_exe.parent
    if parent.name.lower() in ("bin", "scripts"):
        return parent.parent
    return parent


def find_tcl_tk_library_dirs(python_exe: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Locate ``tcl8.x`` / ``tk8.x`` dirs under a managed/official Python prefix.

    PBS Windows: ``<prefix>/tcl/tcl8.6`` and ``<prefix>/tcl/tk8.6``
    PBS Unix: ``<prefix>/lib/tcl8.6`` and ``<prefix>/lib/tk8.6``
    Official Windows: same as PBS Windows under TargetDir.
    """
    prefix = _python_prefix(Path(python_exe))
    search_roots = (
        prefix / "tcl",
        prefix / "lib",
        prefix / "Library" / "lib",  # conda-style
    )
    tcl_dir: Optional[Path] = None
    tk_dir: Optional[Path] = None
    for root in search_roots:
        if not root.is_dir():
            continue
        if tcl_dir is None:
            for child in sorted(root.iterdir(), reverse=True):
                if child.is_dir() and child.name.lower().startswith("tcl8"):
                    if (child / "init.tcl").is_file() or any(child.glob("*.tcl")):
                        tcl_dir = child
                        break
        if tk_dir is None:
            for child in sorted(root.iterdir(), reverse=True):
                if child.is_dir() and child.name.lower().startswith("tk8"):
                    tk_dir = child
                    break
    return tcl_dir, tk_dir


def tcl_tk_environ_for_python(
    python_exe: Path,
    base_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Env dict with TCL_LIBRARY / TK_LIBRARY set when support files are found.

    Must be applied before ``import tkinter`` in the target interpreter.
    """
    env = dict(base_env if base_env is not None else os.environ)
    tcl_dir, tk_dir = find_tcl_tk_library_dirs(python_exe)
    if tcl_dir is not None:
        env["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir is not None:
        env["TK_LIBRARY"] = str(tk_dir)
    return env


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
        proc = run_hidden(
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
    include_tcltk: bool = False,
) -> bool:
    """
    Alternate Windows path: official amd64 installer with TargetDir under tools/.
    May trigger UAC; best-effort only.

    Set ``include_tcltk=True`` when a caller explicitly needs Tcl/Tk (rare;
    the Hub Setup Wizard is an HTML page and does not require it).
    """
    if os.name != "nt":
        return False
    # Prefer a recent 3.12.x installer URL (stable CDN).
    installer_url = (
        "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    )
    tcl_flag = "Include_tcltk=1" if include_tcltk else "Include_tcltk=0"
    with tempfile.TemporaryDirectory(prefix="dread_py_msi_") as tmp:
        exe = Path(tmp) / "python-3.12.10-amd64.exe"
        try:
            _download_file(installer_url, exe, log=log)
            dest.mkdir(parents=True, exist_ok=True)
            _log(log, f"Running silent Python installer → {dest} ({tcl_flag})")
            proc = run_hidden(
                [
                    str(exe),
                    "/quiet",
                    f"TargetDir={dest}",
                    "InstallAllUsers=0",
                    "PrependPath=0",
                    "Include_pip=1",
                    tcl_flag,
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


def managed_python_cmd_from_dir(root: Path) -> Optional[List[str]]:
    py = find_python_in_dir(root)
    if py is None:
        return None
    return [str(py)]


def python_cmd_tkinter_probe(
    cmd: List[str],
    *,
    timeout: float = 45.0,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """
    Probe whether ``cmd`` can create a tkinter root.

    Sets TCL_LIBRARY/TK_LIBRARY from the target prefix when possible.
    Returns ``(ok, detail)`` — detail is empty on success, else stderr/stdout.
    """
    if not cmd:
        return False, "empty python command"
    py = Path(cmd[0])
    merged = tcl_tk_environ_for_python(py, env if env is not None else os.environ)
    # Avoid parent PYTHONPATH shadowing stdlib tkinter with a broken copy.
    merged.pop("PYTHONPATH", None)
    probe = (
        "import os, sys\n"
        "print('exe=', sys.executable)\n"
        "print('prefix=', sys.prefix)\n"
        "print('TCL_LIBRARY=', os.environ.get('TCL_LIBRARY', ''))\n"
        "print('TK_LIBRARY=', os.environ.get('TK_LIBRARY', ''))\n"
        "import tkinter as tk\n"
        "r = tk.Tk(); r.withdraw(); r.destroy()\n"
        "print('tkinter_ok')\n"
    )
    try:
        proc = run_hidden(
            list(cmd) + ["-c", probe],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=merged,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0 and "tkinter_ok" in (proc.stdout or ""):
        return True, ""
    detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
    return False, detail[-1200:]


def python_cmd_has_tkinter(
    cmd: List[str],
    *,
    timeout: float = 45.0,
    env: Optional[Dict[str, str]] = None,
) -> bool:
    """True when ``cmd`` can create a tkinter root (Tcl/Tk present and usable)."""
    ok, _ = python_cmd_tkinter_probe(cmd, timeout=timeout, env=env)
    return ok


def _install_pbs_into(dest: Path, *, log: Optional[LogFn] = None) -> None:
    url, filename = resolve_portable_python_url()
    with tempfile.TemporaryDirectory(prefix="dread_py312_") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / filename
        extract_root = tmp_path / "extract"
        extract_root.mkdir()
        _download_file(url, archive, log=log)
        _log(log, f"Extracting {filename} ...")
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(extract_root)
        _flatten_extracted_python(extract_root, dest)


def install_portable_python312(
    dest: Path,
    *,
    log: Optional[LogFn] = None,
    allow_winget_fallback: bool = True,
    allow_browser_fallback: bool = True,
    allow_official_silent: bool = True,
    require_tkinter: bool = False,
) -> Tuple[bool, str]:
    """
    Download/extract managed CPython 3.12 into dest.

    When ``require_tkinter`` is True, an existing install without Tcl/Tk is
    removed and reinstalled. The Hub Setup Wizard no longer needs this (HTML UI).
    Probes always
    set TCL_LIBRARY/TK_LIBRARY from the install tree. On Windows, if PBS lacks
    a working Tk, falls back to the official installer with Include_tcltk=1.

    Returns (ok, message).
    """
    dest = Path(dest)
    existing = find_python_in_dir(dest)
    if existing is not None:
        if not require_tkinter:
            _log(log, f"Managed Python already present: {existing}")
            return True, f"Managed Python already at {existing}"
        ok, probe_detail = python_cmd_tkinter_probe([str(existing)])
        if ok:
            _log(log, f"Managed Python already present (tkinter ok): {existing}")
            return True, f"Managed Python already at {existing}"
        _log(
            log,
            f"Managed Python at {existing} lacks working tkinter; reinstalling …\n"
            f"Probe: {probe_detail}",
        )
        shutil.rmtree(dest, ignore_errors=True)

    last_error = ""
    url, filename = resolve_portable_python_url()

    # 1) python-build-standalone install_only (includes tcl/ under prefix on Windows).
    try:
        _install_pbs_into(dest, log=log)
        py = find_python_in_dir(dest)
        if not py:
            raise RuntimeError(f"Extract finished but python binary missing under {dest}")
        if not require_tkinter:
            _log(log, f"Portable Python 3.12 ready: {py}")
            return True, f"Installed portable Python 3.12 at {py}"
        ok, probe_detail = python_cmd_tkinter_probe([str(py)])
        if ok:
            _log(log, f"Portable Python 3.12 ready (tkinter ok): {py}")
            return True, f"Installed portable Python 3.12 at {py}"
        last_error = (
            f"PBS {filename} extracted to {py} but tkinter probe failed:\n{probe_detail}"
        )
        _log(log, last_error)
        shutil.rmtree(dest, ignore_errors=True)
    except (OSError, urllib.error.URLError, RuntimeError, tarfile.TarError) as exc:
        last_error = f"python-build-standalone install failed: {exc}"
        _log(log, last_error)
        shutil.rmtree(dest, ignore_errors=True)

    # 2) Official Windows installer with Tcl/Tk (most reliable wizard UI on Windows).
    if require_tkinter and allow_official_silent and os.name == "nt":
        _log(log, "Trying official Python 3.12 installer with Include_tcltk=1 …")
        if try_windows_official_silent_install(dest, log=log, include_tcltk=True):
            py = find_python_in_dir(dest)
            if py:
                ok, probe_detail = python_cmd_tkinter_probe([str(py)])
                if ok:
                    return True, f"Installed Python 3.12 via official installer at {py}"
                last_error = (
                    f"Official installer at {py} still failed tkinter probe:\n{probe_detail}"
                )
                _log(log, last_error)
                shutil.rmtree(dest, ignore_errors=True)
        else:
            last_error = last_error or "Official silent installer failed."

    # 3) Non-tk path: keep previous official/winget fallbacks for client Python only.
    if not require_tkinter:
        if allow_official_silent and try_windows_official_silent_install(
            dest, log=log, include_tcltk=False
        ):
            py = find_python_in_dir(dest)
            if py:
                return True, f"Installed Python 3.12 via official installer at {py}"
        if allow_winget_fallback and try_winget_install_python(log=log):
            return True, "Installed Python 3.12 via winget (system PATH)."

    if allow_winget_fallback and require_tkinter and try_winget_install_python(log=log):
        # Only succeed if we can locate a *working* python with Tk (never trust winget alone).
        for candidate in (
            shutil.which("python3.12"),
            shutil.which("python"),
            shutil.which("py"),
        ):
            if not candidate:
                continue
            # `py` launcher needs -3.12; skip bare py.
            if Path(candidate).stem.lower() == "py":
                continue
            ok, _ = python_cmd_tkinter_probe([candidate])
            if ok:
                return True, f"Installed Python 3.12 via winget; using {candidate}"
        last_error = (
            (last_error + "\n") if last_error else ""
        ) + "winget reported success but no python with working tkinter was found on PATH."

    if allow_browser_fallback:
        _log(log, f"Opening browser: {PYTHON_ORG_312}")
        open_python_download_page()
        if sys.platform.startswith("linux"):
            _log(
                log,
                "Linux tip: the client tried to auto-download Python 3.12 with Tcl/Tk. "
                "If that failed, install python3.12 from your distro/deadsnakes and retry.",
            )

    return (
        False,
        "Auto-install of managed Python 3.12 with Tcl/Tk failed.\n"
        f"Tried: {url}\n"
        f"Detail:\n{last_error or 'unknown error'}",
    )


if __name__ == "__main__":
    dest_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools") / "python-3.12"
    ok, msg = install_portable_python312(dest_arg, require_tkinter="--tk" in sys.argv)
    print(msg)
    raise SystemExit(0 if ok else 1)

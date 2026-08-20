#!/usr/bin/env python3
"""
Ensure Metroid Bread Hub client Python packages are installed.

On Linux, packages are installed into a local virtualenv under the world
directory (``_metroid_bread_venv``) — never systemwide / ``pip install --user``.
Windows keeps the previous behavior (install into the selected system Python).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

try:
    from win_subprocess import run_hidden
except ImportError:
    from worlds.metroid_bread.win_subprocess import run_hidden

# Import name → pip requirement (used when requirements-client.txt is missing).
# open_dread_rando: patcher engine (Connect/ensure so Patch finds it on Hub's interpreter).
# Prefer >=2.19 (DNA HUD / upgrade-row schema); portable dist may ship unpinned.
CLIENT_IMPORTS: Tuple[Tuple[str, str], ...] = (
    ("websockets", "websockets>=13.0.1,<14"),
    ("colorama", "colorama>=0.4.6"),
    ("yaml", "PyYAML>=6.0.3"),
    ("pathspec", "pathspec>=0.12.1"),
    ("certifi", "certifi>=2025.11.12"),
    ("platformdirs", "platformdirs>=4.5.0"),
    ("jellyfish", "jellyfish>=1.2.1"),
    ("typing_extensions", "typing_extensions>=4.15.0"),
    ("schema", "schema>=0.7.8"),
    ("open_dread_rando", "open-dread-rando>=2.19"),
)

EXIT_OK = 0
EXIT_PYTHON_MISSING = 2
EXIT_PIP_FAILED = 3

VENV_DIRNAME = "_metroid_bread_venv"

VERSION_OK_CODE = (
    "import sys; raise SystemExit("
    "0 if (3, 11, 9) <= sys.version_info < (3, 14) else 1)"
)
VERSION_PRINT_CODE = "import sys; print('%d.%d.%d' % sys.version_info[:3])"

# Inclusive lower / exclusive upper bounds for Hub client CPython.
CLIENT_PYTHON_MIN = (3, 11, 9)
CLIENT_PYTHON_MAX_EXCLUSIVE = (3, 14)

PYTHON_MISSING_MESSAGE = (
    "No usable Python 3.11–3.13 found for the Hub client.\n"
    "Archipelago Text Client uses its own bundled Python — Hub needs a system install.\n\n"
    "Fix:\n"
    "  1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/\n"
    '     (check "Add python.exe to PATH")\n'
    "  2. Or with the new Python install manager:  py install 3.12\n"
    "  3. Confirm with:  py -0\n"
    "  4. Restart the Hub and Connect again.\n\n"
    "Linux (Arch/etc.): install a 3.11–3.13 python package, then re-run the launcher.\n"
    "Client deps install into a local venv (never systemwide)."
)


def world_dir() -> Path:
    return Path(__file__).resolve().parent


def requirements_file(world: Optional[Path] = None) -> Path:
    return (world or world_dir()) / "requirements-client.txt"


def uses_linux_venv() -> bool:
    return sys.platform.startswith("linux")


def venv_dir(world: Optional[Path] = None) -> Path:
    return (world or world_dir()) / VENV_DIRNAME


def venv_python_path(world: Optional[Path] = None) -> Path:
    return venv_dir(world) / "bin" / "python"


def python_missing_message() -> str:
    return PYTHON_MISSING_MESSAGE


def format_cmd(cmd: Sequence[str]) -> str:
    return " ".join(str(c) for c in cmd if c)


def is_supported_client_python_version(
    version_info: Optional[Tuple[int, ...]] = None,
) -> bool:
    """True when version is Hub-compatible CPython 3.11.9–3.13.x."""
    info = version_info if version_info is not None else sys.version_info
    major = int(info[0])
    minor = int(info[1])
    micro = int(info[2]) if len(info) > 2 else 0
    tup = (major, minor, micro)
    return CLIENT_PYTHON_MIN <= tup < CLIENT_PYTHON_MAX_EXCLUSIVE


def _probe(cmd: Sequence[str], code: str, *, timeout: float = 30.0) -> bool:
    try:
        proc = run_hidden(
            list(cmd) + ["-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _probe_version_string(cmd: Sequence[str], *, timeout: float = 30.0) -> Optional[str]:
    try:
        proc = run_hidden(
            list(cmd) + ["-c", VERSION_PRINT_CODE],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    return line[-1].strip() if line else None


def describe_missing_client_python() -> str:
    """
    Short checklist / wizard detail when no usable 3.11–3.13 interpreter exists.

    Mentions a present-but-unsupported Python (e.g. 3.14) when found.
    """
    for candidate in _base_python_candidates():
        ver = _probe_version_string(candidate)
        if not ver:
            continue
        parts = ver.split(".")
        try:
            tup = tuple(int(p) for p in parts[:3])
        except ValueError:
            continue
        if not is_supported_client_python_version(tup):
            return (
                f"{format_cmd(candidate)} is Python {ver} "
                "(need 3.11–3.13) — Install Python 3.12"
            )
    return "no usable 3.11–3.13 — Install Python 3.12"


def _is_venv_python_cmd(python_cmd: Sequence[str], world: Optional[Path] = None) -> bool:
    if not python_cmd:
        return False
    try:
        resolved = Path(str(python_cmd[0])).resolve()
        return resolved == venv_python_path(world).resolve()
    except OSError:
        return False


def _base_python_candidates() -> List[List[str]]:
    if sys.platform == "win32":
        return [
            ["py", "-3.11"],
            ["py", "-3.12"],
            ["py", "-3.13"],
            ["python"],
        ]
    return [
        ["python3.12"],
        ["python3.11"],
        ["python3.13"],
        ["python3"],
        ["python"],
    ]


def _managed_python_cmd() -> Optional[List[str]]:
    """Prefer DREAD_HUB_PYTHON env, then portable tools/python-3.12."""
    env_py = (os.environ.get("DREAD_HUB_PYTHON") or "").strip()
    if env_py:
        cmd = [env_py]
        if _probe(cmd, VERSION_OK_CODE):
            return cmd
    try:
        try:
            from hub_launcher import managed_python_cmd
        except ImportError:
            from worlds.metroid_bread.hub_launcher import managed_python_cmd
        cmd = managed_python_cmd()
        if cmd and _probe(cmd, VERSION_OK_CODE):
            return list(cmd)
        # Accept managed binary even if version probe is slow/odd when file exists.
        if cmd and Path(cmd[0]).is_file():
            return list(cmd)
    except Exception:
        pass
    return None


def find_base_python() -> Optional[List[str]]:
    """Locate a system / host Python 3.11–3.13 (prefer managed, then open-dread-rando)."""
    managed = _managed_python_cmd()
    if managed:
        return managed
    has_odr = "import open_dread_rando"
    for cmd in _base_python_candidates():
        if _probe(cmd, has_odr):
            return cmd
    for cmd in _base_python_candidates():
        if _probe(cmd, VERSION_OK_CODE):
            return cmd
    return None


def find_client_python(world: Optional[Path] = None) -> Optional[List[str]]:
    """
    Interpreter used for Hub client deps / launch.

    On Linux, prefer an existing local venv (deps live there). Otherwise prefer
    managed portable CPython / DREAD_HUB_PYTHON, then host discovery.
    """
    if uses_linux_venv():
        vpy = venv_python_path(world)
        if vpy.is_file() and _probe([str(vpy)], VERSION_OK_CODE):
            return [str(vpy)]
    managed = _managed_python_cmd()
    if managed:
        return managed
    return find_base_python()


def ensure_linux_venv(
    base_cmd: Sequence[str],
    *,
    world: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[Optional[List[str]], str]:
    """
    Create or reuse ``_metroid_bread_venv`` next to the world package.

    Uses ``--system-site-packages`` so a host open-dread-rando install remains
    importable; new client packages still land only in the venv.
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    vdir = venv_dir(world)
    vpy = venv_python_path(world)
    if vpy.is_file() and _probe([str(vpy)], VERSION_OK_CODE):
        _log(f"Using venv Python: {vpy}")
        return [str(vpy)], ""

    _log(
        f"Creating local venv at {vdir} "
        f"(from {format_cmd(base_cmd)}; deps will not be installed systemwide)..."
    )
    try:
        proc = run_hidden(
            list(base_cmd)
            + ["-m", "venv", "--system-site-packages", str(vdir)],
            capture_output=True,
            text=True,
            timeout=180,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = (
            f"Failed to create venv with {format_cmd(base_cmd)} -m venv:\n{exc}\n\n"
            "On Arch Linux, ensure the python package is installed "
            "(provides python -m venv)."
        )
        return None, detail

    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
    if proc.returncode != 0 or not vpy.is_file():
        detail = (
            f"Failed to create venv at {vdir} with {format_cmd(base_cmd)}.\n"
            "On Arch Linux: pacman -S python  (stdlib venv module).\n"
            "Then re-run the launcher.\n"
        )
        if combined:
            detail += f"\nvenv output:\n{combined[-4000:]}"
        return None, detail

    _log(f"Using venv Python: {vpy}")
    return [str(vpy)], ""


def resolve_install_python(
    python_cmd: Optional[Sequence[str]] = None,
    *,
    world: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[Optional[List[str]], str, int]:
    """
    Pick the interpreter that should receive pip installs / run the client.

    Linux → always a local venv. Windows/macOS → passed or discovered host Python.
    """
    if uses_linux_venv():
        if python_cmd and _is_venv_python_cmd(python_cmd, world):
            if _probe(list(python_cmd), VERSION_OK_CODE):
                if log:
                    log(f"Using venv Python: {format_cmd(python_cmd)}")
                return list(python_cmd), "", EXIT_OK
        base = list(python_cmd) if python_cmd else find_base_python()
        if not base:
            return None, python_missing_message(), EXIT_PYTHON_MISSING
        if not _probe(base, VERSION_OK_CODE):
            # Hub may pass a python that has ODR but odd version; still try
            # version-ok base discovery when the passed interpreter is wrong.
            discovered = find_base_python()
            if not discovered:
                return None, python_missing_message(), EXIT_PYTHON_MISSING
            base = discovered
        vcmd, err = ensure_linux_venv(base, world=world, log=log)
        if not vcmd:
            return None, err or python_missing_message(), EXIT_PIP_FAILED
        return vcmd, "", EXIT_OK

    cmd = list(python_cmd) if python_cmd else find_client_python(world)
    if not cmd:
        return None, python_missing_message(), EXIT_PYTHON_MISSING
    return cmd, "", EXIT_OK


def missing_imports(python_cmd: Sequence[str]) -> List[str]:
    """Return import names that fail under python_cmd."""
    names = [name for name, _ in CLIENT_IMPORTS]
    # One subprocess: print comma-separated missing modules.
    code = (
        "import importlib.util\n"
        f"names = {names!r}\n"
        "miss = [n for n in names if importlib.util.find_spec(n) is None]\n"
        "print(','.join(miss))\n"
    )
    try:
        proc = run_hidden(
            list(python_cmd) + ["-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"Could not probe Python packages with {format_cmd(python_cmd)}: {exc}"
        ) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"Could not probe Python packages with {format_cmd(python_cmd)}"
            + (f":\n{err}" if err else ".")
        )
    line = (proc.stdout or "").strip().splitlines()
    blob = line[-1] if line else ""
    return [p for p in blob.split(",") if p]


def _looks_like_pip_missing(detail: str) -> bool:
    blob = (detail or "").lower()
    return (
        "no module named pip" in blob
        or "no module named 'pip'" in blob
        or "pip is not installed" in blob
        or "/usr/bin/pip: not found" in blob
        or "failed to find pip" in blob
    )


def pip_install_hint_lines(python_cmd: Sequence[str]) -> List[str]:
    """OS-specific steps to get pip when ``python -m pip`` is unavailable."""
    py = format_cmd(python_cmd)
    lines = [
        "If pip is missing, bootstrap it then retry Connect:",
        f"  {py} -m ensurepip --upgrade",
        f"  {py} -m pip --version",
        "",
    ]
    if sys.platform == "win32":
        lines.extend(
            [
                "Windows (if ensurepip fails):",
                "  • Re-run the Python installer → Modify → enable pip",
                "  • Or install from https://www.python.org/downloads/ (Add to PATH)",
                "  • Or:  py install 3.12   then   py -3.12 -m ensurepip --upgrade",
            ]
        )
    elif sys.platform.startswith("linux"):
        lines.extend(
            [
                "Linux / Manjaro / Arch:",
                "  sudo pacman -S python-pip",
                "Debian / Ubuntu (ensurepip often stripped):",
                "  sudo apt install python3-pip   # or: sudo apt install python3-venv",
                "Fedora:",
                "  sudo dnf install python3-pip",
            ]
        )
        if uses_linux_venv():
            lines.extend(
                [
                    "",
                    "Use the Hub venv python above after fixing pip;",
                    "do not pip install --user or as root into system Python.",
                ]
            )
    else:
        lines.extend(
            [
                "macOS / other:",
                f"  {py} -m ensurepip --upgrade",
                "  or:  brew install python   (Homebrew Python includes pip)",
            ]
        )
    return lines


def pip_failure_message(
    python_cmd: Sequence[str],
    *,
    req_path: Optional[Path] = None,
    detail: str = "",
    world: Optional[Path] = None,
) -> str:
    py = format_cmd(python_cmd)
    req = req_path or requirements_file(world)
    if req.is_file():
        install_line = f'{py} -m pip install -r "{req}"'
    else:
        pkgs = " ".join(req for _, req in CLIENT_IMPORTS)
        install_line = f"{py} -m pip install {pkgs}"
    parts = [
        "Failed to install Metroid Bread client Python packages.",
        "",
        f"Interpreter: {py}",
    ]
    if uses_linux_venv():
        parts.extend(
            [
                f"Expected local venv: {venv_dir(world)}",
                "Packages are installed into this venv only (not systemwide).",
            ]
        )
    parts.extend(
        [
            "Try manually:",
            f"  {install_line}",
            "",
        ]
    )
    parts.extend(pip_install_hint_lines(python_cmd))
    if not _looks_like_pip_missing(detail):
        parts.extend(
            [
                "",
                "If Python itself is missing or not on PATH:",
                "  1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/",
                '     (check "Add python.exe to PATH")',
                "  2. Or:  py install 3.12",
                "  3. Confirm with:  py -0",
                "  4. Restart the Hub and Connect again.",
            ]
        )
    if detail.strip():
        parts.extend(["", "pip output:", detail.strip()[-4000:]])
    return "\n".join(parts)


def pip_available(python_cmd: Sequence[str]) -> bool:
    """True when ``python -m pip`` runs successfully on python_cmd."""
    return _probe(python_cmd, "import pip; raise SystemExit(0)")


def ensure_pip(
    python_cmd: Sequence[str],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """
    Best-effort bootstrap of pip via ``python -m ensurepip --upgrade``.

    Safe to call when pip is already present (ensurepip is a no-op / upgrades).
    Returns (ok, detail). ok means pip is importable afterward.
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    if pip_available(python_cmd):
        return True, ""

    _log(f"pip missing for {format_cmd(python_cmd)}; trying ensurepip...")
    try:
        proc = run_hidden(
            list(python_cmd) + ["-m", "ensurepip", "--upgrade"],
            capture_output=True,
            text=True,
            timeout=180,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"ensurepip failed: {exc}"

    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
    if pip_available(python_cmd):
        _log("pip available after ensurepip.")
        return True, combined
    detail = combined or f"ensurepip exited {proc.returncode}"
    return False, detail


def _install_packages(
    python_cmd: Sequence[str],
    world: Optional[Path] = None,
    *,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    req = requirements_file(world)
    if not pip_available(python_cmd):
        ok_pip, pip_detail = ensure_pip(python_cmd, log=log)
        if not ok_pip:
            return False, pip_failure_message(
                python_cmd,
                req_path=req,
                detail=pip_detail or "No module named pip",
                world=world,
            )

    # Never pass --user; target interpreter should already be a venv on Linux.
    if req.is_file():
        cmd = list(python_cmd) + ["-m", "pip", "install", "-r", str(req)]
    else:
        cmd = list(python_cmd) + ["-m", "pip", "install", *[r for _, r in CLIENT_IMPORTS]]
    try:
        proc = run_hidden(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, pip_failure_message(python_cmd, req_path=req, detail=str(exc), world=world)
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
    if proc.returncode != 0:
        # One more ensurepip attempt if the failure looks like missing pip
        # (e.g. race / broken venv) then retry once.
        if _looks_like_pip_missing(combined):
            ok_pip, _ = ensure_pip(python_cmd, log=log)
            if ok_pip:
                try:
                    proc = run_hidden(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=600,
                        shell=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    return False, pip_failure_message(
                        python_cmd, req_path=req, detail=str(exc), world=world
                    )
                combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
                if proc.returncode == 0:
                    return True, combined
        return False, pip_failure_message(python_cmd, req_path=req, detail=combined, world=world)
    return True, combined


def ensure_client_deps(
    python_cmd: Optional[Sequence[str]] = None,
    *,
    world: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str, int]:
    """
    Ensure client packages exist in the target interpreter.

    On Linux the target is always ``<world>/_metroid_bread_venv``.

    Returns (ok, message, exit_code).
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    cmd, err, code = resolve_install_python(python_cmd, world=world, log=_log)
    if not cmd:
        return False, err, code

    try:
        missing = missing_imports(cmd)
    except RuntimeError as exc:
        return False, str(exc) + "\n\n" + python_missing_message(), EXIT_PYTHON_MISSING

    if not missing:
        _log(f"Python client packages OK ({format_cmd(cmd)}).")
        return True, f"Python client packages OK ({format_cmd(cmd)}).", EXIT_OK

    where = "into local venv" if uses_linux_venv() else "for Hub client"
    _log(
        f"Installing missing Python packages {where} ({format_cmd(cmd)}): "
        + ", ".join(missing)
    )
    ok, detail = _install_packages(cmd, world=world, log=_log)
    if not ok:
        return False, detail, EXIT_PIP_FAILED

    try:
        still = missing_imports(cmd)
    except RuntimeError as exc:
        return False, str(exc), EXIT_PIP_FAILED
    if still:
        return (
            False,
            pip_failure_message(
                cmd,
                req_path=requirements_file(world),
                detail=f"Still missing after pip install: {', '.join(still)}\n{detail}",
                world=world,
            ),
            EXIT_PIP_FAILED,
        )

    msg = f"Installed Python client packages ({format_cmd(cmd)}): " + ", ".join(missing)
    _log(msg)
    return True, msg, EXIT_OK


def ensure_client_deps_or_raise(
    python_cmd: Optional[Sequence[str]] = None,
    *,
    world: Optional[Path] = None,
) -> str:
    """Like ensure_client_deps but raises RuntimeError on failure. Returns status message."""
    ok, msg, _code = ensure_client_deps(python_cmd, world=world)
    if not ok:
        raise RuntimeError(msg)
    return msg


def local_modules_present() -> List[str]:
    """Missing imports in *this* interpreter (for in-process fallback checks)."""
    missing = []
    for name, _req in CLIENT_IMPORTS:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    return missing


def main(argv: Optional[Iterable[str]] = None) -> int:
    # Keep SKIP so accidental ModuleUpdate from imported AP code does not fire.
    os.environ.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")
    args = list(sys.argv[1:] if argv is None else argv)
    world: Optional[Path] = None
    if args and args[0] in ("-w", "--world"):
        if len(args) < 2:
            print("Usage: ensure_client_deps.py [--world DIR]", file=sys.stderr)
            return 1
        world = Path(args[1])
    ok, msg, code = ensure_client_deps(world=world)
    if not ok:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

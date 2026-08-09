#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

# Import name → pip requirement (used when requirements-client.txt is missing).
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
)

EXIT_OK = 0
EXIT_PYTHON_MISSING = 2
EXIT_PIP_FAILED = 3

PYTHON_MISSING_MESSAGE = (
    "No usable Python 3.11–3.13 found for the Hub client.\n"
    "Archipelago Text Client uses its own bundled Python — Hub needs a system install.\n\n"
    "Fix:\n"
    "  1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/\n"
    '     (check "Add python.exe to PATH")\n'
    "  2. Or with the new Python install manager:  py install 3.12\n"
    "  3. Confirm with:  py -0\n"
    "  4. Restart the Hub and Connect again."
)


def world_dir() -> Path:
    return Path(__file__).resolve().parent


def requirements_file(world: Optional[Path] = None) -> Path:
    return (world or world_dir()) / "requirements-client.txt"


def python_missing_message() -> str:
    return PYTHON_MISSING_MESSAGE


def format_cmd(cmd: Sequence[str]) -> str:
    return " ".join(str(c) for c in cmd if c)


def _probe(cmd: Sequence[str], code: str, *, timeout: float = 30.0) -> bool:
    try:
        proc = subprocess.run(
            list(cmd) + ["-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_client_python() -> Optional[List[str]]:
    if sys.platform == "win32":
        candidates: List[List[str]] = [
            ["py", "-3.11"],
            ["py", "-3.12"],
            ["py", "-3.13"],
            ["python"],
        ]
    else:
        candidates = [
            ["python3.12"],
            ["python3.11"],
            ["python3.13"],
            ["python3"],
            ["python"],
        ]

    version_ok = (
        "import sys; raise SystemExit("
        "0 if (3, 11, 9) <= sys.version_info < (3, 14) else 1)"
    )
    has_odr = "import open_dread_rando"

    for cmd in candidates:
        if _probe(cmd, has_odr):
            return cmd
    for cmd in candidates:
        if _probe(cmd, version_ok):
            return cmd
    return None


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
        proc = subprocess.run(
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


def pip_failure_message(
    python_cmd: Sequence[str],
    *,
    req_path: Optional[Path] = None,
    detail: str = "",
) -> str:
    py = format_cmd(python_cmd)
    req = req_path or requirements_file()
    if req.is_file():
        install_line = f'{py} -m pip install -r "{req}"'
    else:
        pkgs = " ".join(req for _, req in CLIENT_IMPORTS)
        install_line = f"{py} -m pip install {pkgs}"
    parts = [
        "Failed to install Metroid Dread client Python packages.",
        "",
        f"Interpreter: {py}",
        "Try manually:",
        f"  {install_line}",
        "",
        "If pip is missing or Python is not on PATH:",
        "  1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/",
        '     (check "Add python.exe to PATH")',
        "  2. Or:  py install 3.12",
        "  3. Confirm with:  py -0",
        "  4. Restart the Hub and Connect again.",
    ]
    if detail.strip():
        parts.extend(["", "pip output:", detail.strip()[-4000:]])
    return "\n".join(parts)


def _install_packages(python_cmd: Sequence[str], world: Optional[Path] = None) -> Tuple[bool, str]:
    req = requirements_file(world)
    if req.is_file():
        cmd = list(python_cmd) + ["-m", "pip", "install", "-r", str(req)]
    else:
        cmd = list(python_cmd) + ["-m", "pip", "install", *[r for _, r in CLIENT_IMPORTS]]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, pip_failure_message(python_cmd, req_path=req, detail=str(exc))
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
    if proc.returncode != 0:
        return False, pip_failure_message(python_cmd, req_path=req, detail=combined)
    return True, combined


def ensure_client_deps(
    python_cmd: Optional[Sequence[str]] = None,
    *,
    world: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str, int]:
    """
    Ensure client packages exist in the target interpreter.

    Returns (ok, message, exit_code).
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    cmd = list(python_cmd) if python_cmd else find_client_python()
    if not cmd:
        return False, python_missing_message(), EXIT_PYTHON_MISSING

    try:
        missing = missing_imports(cmd)
    except RuntimeError as exc:
        return False, str(exc) + "\n\n" + python_missing_message(), EXIT_PYTHON_MISSING

    if not missing:
        _log(f"Python client packages OK ({format_cmd(cmd)}).")
        return True, f"Python client packages OK ({format_cmd(cmd)}).", EXIT_OK

    _log(
        f"Installing missing Python packages for Hub client ({format_cmd(cmd)}): "
        + ", ".join(missing)
    )
    ok, detail = _install_packages(cmd, world=world)
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

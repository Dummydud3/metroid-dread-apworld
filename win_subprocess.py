#!/usr/bin/env python3
"""
Windows-friendly subprocess helpers.

Console ``.exe`` children (node, python, npm.cmd, winget, …) flash a terminal
window under Archipelago's GUI launcher unless CREATE_NO_WINDOW is set.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

# Win32: CREATE_NO_WINDOW — available on Python 3.7+ as subprocess.CREATE_NO_WINDOW
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def hidden_subprocess_kwargs(
    *,
    extra_creationflags: int = 0,
) -> dict:
    """
    Kwargs for subprocess.run / Popen that hide the console on Windows.

    Safe no-op on non-Windows. Callers may still pass capture_output=True.
    """
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": _CREATE_NO_WINDOW | int(extra_creationflags),
    }


def merge_run_kwargs(user: Optional[Mapping[str, Any]] = None) -> dict:
    """Merge caller kwargs with hidden-console defaults (user wins on conflicts)."""
    merged: dict = dict(hidden_subprocess_kwargs())
    if user:
        # OR creationflags if both sides set them.
        if "creationflags" in user and "creationflags" in merged:
            merged["creationflags"] = int(merged["creationflags"]) | int(
                user["creationflags"]
            )
            rest = {k: v for k, v in user.items() if k != "creationflags"}
            merged.update(rest)
        else:
            merged.update(user)
    return merged


def run_hidden(
    args: Union[Sequence[str], str],
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """subprocess.run with console hidden on Windows."""
    return subprocess.run(args, **merge_run_kwargs(kwargs))


def popen_hidden(
    args: Union[Sequence[str], str],
    **kwargs: Any,
) -> subprocess.Popen:
    """subprocess.Popen with console hidden on Windows."""
    return subprocess.Popen(args, **merge_run_kwargs(kwargs))

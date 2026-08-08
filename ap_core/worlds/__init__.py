"""
Minimal ``worlds`` package for Hub / MetroidDreadClient under frozen Archipelago installs.

Frozen ProgramData builds only ship ``CommonClient`` as Python 3.13 ``.pyc`` inside
``lib/library.zip``, which system Python cannot import. The Hub therefore runs against
``ap_core/`` (loose ``.py`` sources) and this stub instead of loading every AP world.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class AutoWorldRegister:
    """Placeholder matching the attribute CommonClient imports from ``worlds``."""

    world_types: Dict[str, Any] = {}


def _load_dread_datapackage() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "metroid_dread_datapackage.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_dread = _load_dread_datapackage()
network_data_package: Dict[str, Any] = {
    "games": {"Metroid Dread": _dread} if _dread else {},
}

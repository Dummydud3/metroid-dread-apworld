"""
Minimal ``worlds`` package for Hub / MetroidBreadClient under frozen Archipelago installs.

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


_DATAPACKAGE_CANDIDATES = (
    "metroid_bread_datapackage.json",
    # Pre-rename fallback (Metroid Dread → Metroid Bread).
    "metroid_dread_datapackage.json",
)


def _load_dread_datapackage() -> Dict[str, Any]:
    parent = Path(__file__).resolve().parent
    for name in _DATAPACKAGE_CANDIDATES:
        path = parent / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data:
            return data
    return {}


_dread = _load_dread_datapackage()
network_data_package: Dict[str, Any] = {
    "games": {"Metroid Bread": _dread} if _dread else {},
}

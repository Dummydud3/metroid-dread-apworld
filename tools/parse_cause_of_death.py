#!/usr/bin/env python3
"""CLI for CauseOfDeath Ryujinx-log parsing. See cause_of_death.py / CAUSE_OF_DEATH_MATRIX.md."""

from __future__ import annotations

import sys
from pathlib import Path

_WORLD = Path(__file__).resolve().parents[1]
if str(_WORLD) not in sys.path:
    sys.path.insert(0, str(_WORLD))

from cause_of_death import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

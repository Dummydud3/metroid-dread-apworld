"""
ODR text_patches experiment: rewrite AP context-4 tip carousel (TIP_000–TIP_004).

With OdrTip 0.3.0+, ExeFS duplicate-registers these five keys into tip context
class 4 (via 0xddcf14 after retail fill) and forces getter 0xddbbb8 → 4.
Vanilla GENERAL copies of the same keys stay at context 0. Patching BTXT
(TITLE||BODY, retail {c6}/{c7}/{c0} style) makes the pool-4 hijack obvious.

OdrTip 0.5.2 seeds Metroid Bread defaults into the same five keys via GetLocalized
(slot 0 = CONNECT CLIENT; default gTipCount=1) and controls carousel order/count
via PoolBuild trampoline (`OdrTip.SetTipOrder` / `SetTipCount` / `/tip_order` /
`/tip_count`; default order hardcoded sequential 0,1,2,3,4).
(OdrTip.SetTipText / client /tip_set overwrite; ClearTipText restores defaults).
RomFS patches remain a belt-and-suspenders fallback if the override hook is off.

Enable (default ON for this experiment):
  - leave as-is, or METROID_BREAD_CAROUSEL_TIP_PATCHES=1

Disable later:
  - set METROID_BREAD_CAROUSEL_TIP_PATCHES=0 (or false/off/no)
  - or set CAROUSEL_TIP_TEXT_PATCHES_ENABLED = False below
  - then re-patch (or re-run apply_carousel_tip_text_patches_to_romfs on the mod)

Coexist with PHASE2 mode:
  - rebuild OdrTip with kTipContextForceMode = EmmiPhase2 (force getter=2)
  - point CAROUSEL_TIP_KEYS at TIP_050–052 and retitle if desired
  - Off mode uses retail Orig() for the getter (no force)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Mapping, Optional

# Flip to False to permanently opt out without an env var.
CAROUSEL_TIP_TEXT_PATCHES_ENABLED = True

_ENV_FLAG = "METROID_BREAD_CAROUSEL_TIP_PATCHES"

# Exact retail BTXT keys (us_english.txt) duplicate-registered into context 4.
CAROUSEL_TIP_KEYS = (
    "TIP_000_GENERAL_PARKOUR_000",
    "TIP_001_GENERAL_WALL_JUMP_000",
    "TIP_002_GENERAL_POWER_GRIP_000",
    "TIP_003_GENERAL_MELEE_COUNTER_000",
    "TIP_004_GENERAL_DASH_MELEE_000",
)

# Same localization set ODR's apply_text_patches walks.
_ALL_TEXT_FILES = (
    "eu_dutch.txt",
    "eu_french.txt",
    "eu_german.txt",
    "eu_italian.txt",
    "eu_spanish.txt",
    "japanese.txt",
    "korean.txt",
    "russian.txt",
    "simplified_chinese.txt",
    "traditional_chinese.txt",
    "us_english.txt",
    "us_french.txt",
    "us_spanish.txt",
)


def carousel_tip_text_patches_enabled(
    *,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Default ON; METROID_BREAD_CAROUSEL_TIP_PATCHES=0/false/off/no disables."""
    if not CAROUSEL_TIP_TEXT_PATCHES_ENABLED:
        return False
    raw = (env if env is not None else os.environ).get(_ENV_FLAG, "").strip().lower()
    if not raw:
        return True
    return raw not in ("0", "false", "off", "no", "disable", "disabled")


def format_carousel_tip(index: int) -> str:
    """Retail TITLE||BODY shape with unmistakable AP POOL4 marker titles."""
    if index < 0 or index >= len(CAROUSEL_TIP_KEYS):
        raise ValueError(f"carousel tip index out of range: {index}")
    title = f"{{c6}}AP POOL4 {index}{{c7}}"
    body = (
        f"Bread context-4 tip {index} - custom pool works.{{c0}}"
    )
    return f"{title}||{body}"


def build_carousel_tip_text_patches() -> Dict[str, str]:
    """Five ODR text_patches entries for the forced context-4 tip carousel."""
    return {
        key: format_carousel_tip(i) for i, key in enumerate(CAROUSEL_TIP_KEYS)
    }


def apply_carousel_tip_text_patches_to_romfs(romfs: Path) -> int:
    """
    Write carousel tip strings into romfs localization/*.txt (mercury Txt).

    Returns number of key writes across all locale files that contained the keys.
    Safe no-op when disabled or when localization is missing.
    """
    if not carousel_tip_text_patches_enabled():
        return 0
    patches = build_carousel_tip_text_patches()
    loc_dir = romfs / "system" / "localization"
    if not loc_dir.is_dir():
        return 0

    try:
        from mercury_engine_data_structures.formats.txt import Txt
        from mercury_engine_data_structures.game_check import Game
    except ImportError:
        return 0

    writes = 0
    for name in _ALL_TEXT_FILES:
        path = loc_dir / name
        if not path.is_file():
            continue
        try:
            txt = Txt.parse(path.read_bytes(), target_game=Game.DREAD)
        except Exception:
            continue
        changed = False
        for key, value in patches.items():
            if key not in txt.strings:
                continue
            if txt.strings.get(key) != value:
                txt.strings[key] = value
                changed = True
                writes += 1
        if changed:
            path.write_bytes(txt.build())
    return writes

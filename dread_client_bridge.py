"""
Shared Metroid Dread client↔game bridge helpers.

Maps Archipelago location/item IDs to Randovania / open-dread-rando indices
and Lua resource tables used over the Ryujinx TCP protocol (port 6969).
"""

from __future__ import annotations

import json
import os
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

# Package directory (worlds/metroid_dread) — logic + client data live here.
# When loaded from a .apworld zip, Path(__file__) is a virtual path; readers
# below fall back to zip members / extracted runtime.
ROOT = Path(__file__).resolve().parent


def _find_containing_apworld(start: Optional[Path] = None) -> Optional[Path]:
    here = Path(start) if start is not None else ROOT
    for candidate in (here, *here.parents):
        if candidate.suffix.lower() == ".apworld" and candidate.is_file():
            return candidate
    parts = list(here.parts)
    for i, part in enumerate(parts):
        if part.lower().endswith(".apworld"):
            zipped = Path(*parts[: i + 1])
            if zipped.is_file():
                return zipped
    return None


def _read_world_text(filename: str) -> str:
    """
    Read a world-package text file from disk, extracted runtime, or .apworld zip.

    Fixes NotADirectoryError when MetroidDreadClient is launched from zipimport
    under ``custom_worlds/metroid_dread.apworld/.../Items.py``.
    """
    candidates: list[Path] = [ROOT / filename]
    # Extracted Hub runtime (same layout Hub materializes for Electron).
    raw = (os.environ.get("DREAD_HUB_WORLD_DIR") or "").strip()
    if raw:
        candidates.append(Path(raw) / filename)
    try:
        from Utils import user_path  # type: ignore

        candidates.append(
            Path(user_path("custom_worlds", "_metroid_dread_runtime")) / filename
        )
    except Exception:
        pass

    seen: set[Path] = set()
    for path in candidates:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except (NotADirectoryError, OSError):
            continue

    apworld = _find_containing_apworld()
    if apworld is not None:
        member = f"metroid_dread/{filename}".replace("\\", "/")
        with zipfile.ZipFile(apworld, "r") as zf:
            try:
                return zf.read(member).decode("utf-8")
            except KeyError as exc:
                raise FileNotFoundError(
                    f"{filename} not found in {apworld} ({member})"
                ) from exc

    raise FileNotFoundError(f"{filename} not found next to {ROOT}")

# Lua handler class for RL.ReceivePickup(parent, ...) — must be a Lua identifier.
ITEM_PARENT_BY_ID: Dict[str, str] = {
    "ITEM_WEAPON_WIDE_BEAM": "RandomizerWideBeam",
    "ITEM_WEAPON_PLASMA_BEAM": "RandomizerPlasmaBeam",
    "ITEM_WEAPON_WAVE_BEAM": "RandomizerWaveBeam",
    "ITEM_WEAPON_MISSILE_LAUNCHER": "RandomizerMissileLauncher",
    "ITEM_WEAPON_SUPER_MISSILE": "RandomizerSuperMissile",
    "ITEM_WEAPON_ICE_MISSILE": "RandomizerIceMissile",
    "ITEM_MULTILOCKON": "RandomizerStormMissile",
    "ITEM_OPTIC_CAMOUFLAGE": "RandomizerPhantomCloak",
    "ITEM_GHOST_AURA": "RandomizerFlashShift",
    "ITEM_UPGRADE_FLASH_SHIFT_CHAIN": "RandomizerFlashShiftUpgrade",
    "ITEM_SPEED_BOOSTER": "RandomizerSpeedBooster",
    "ITEM_LIFE_SHARDS": "RandomizerEnergyPart",
    "ITEM_WEAPON_POWER_BOMB": "RandomizerPowerBomb",
    "ITEM_WEAPON_POWER_BOMB_MAX": "RandomizerPowerBomb",
}

# Fallbacks for AP item names missing from dread_item_mapping
DNA_ITEM_NAME = "Metroid DNA"
DNA_DYNAMIC_ITEM_ID = "__AP_DNA_NEXT__"

EXTRA_ITEM_RESOURCES: Dict[str, List[dict]] = {
    "Storm Missile": [{"item_id": "ITEM_MULTILOCKON", "quantity": 1}],
    "Slide": [{"item_id": "ITEM_SPECIAL_SLIDE", "quantity": 1}],
    "Omega Cannon": [{"item_id": "ITEM_WEAPON_POWER_BEAM", "quantity": 1}],
    "Omega Stream Beam": [{"item_id": "ITEM_WEAPON_POWER_BEAM", "quantity": 1}],
    "Missile Launcher": [{"item_id": "ITEM_WEAPON_MISSILE_LAUNCHER", "quantity": 1}],
    DNA_ITEM_NAME: [{"item_id": DNA_DYNAMIC_ITEM_ID, "quantity": 1}],
    # ODR/schema id — not ITEM_SPEED_BOOSTER_UPGRADE (invalid; caused grant failures).
    "Speed Booster Upgrade": [{"item_id": "ITEM_UPGRADE_SPEED_BOOST_CHARGE", "quantity": 1}],
}


def is_dna_item(item_name: str) -> bool:
    """True for AP Metroid DNA (numbered Randovania variants included for /give)."""
    name = (item_name or "").strip()
    return name == DNA_ITEM_NAME or name.startswith(f"{DNA_ITEM_NAME} ")


def _ap_location_key(location_name: str) -> str:
    parts = location_name.split(" - ", 2)
    if len(parts) != 3:
        return location_name
    return f"{parts[0]}/{parts[1]}/{parts[2]}"


@lru_cache(maxsize=1)
def pickup_index_to_ap_location() -> Dict[int, int]:
    """
    Randovania pickup bitfield index → Archipelago location ID.

    Parsed from source files to avoid importing the full worlds package
    (which pulls in unrelated game deps at client launch).
    """
    import re

    export_text = _read_world_text("rdvgame_export.py")
    start = export_text.index("AP_TO_RANDOVANIA_LOCATION_MAP = {")
    end = export_text.index("\n}", start) + 2
    ns: dict = {}
    exec(export_text[start:end], ns)  # noqa: S102 — trusted local mapping
    loc_map: Dict[str, tuple] = ns["AP_TO_RANDOVANIA_LOCATION_MAP"]

    locations_text = _read_world_text("Locations.py")
    entries = re.findall(r'"([^"]+)": LocationData\((\d+),', locations_text)

    mapping: Dict[int, int] = {}
    for name, ap_id in entries:
        key = _ap_location_key(name)
        mapped = loc_map.get(key)
        if mapped is None:
            continue
        mapping[int(mapped[1])] = int(ap_id)
    return mapping


@lru_cache(maxsize=1)
def load_pickup_actors() -> Dict[str, dict]:
    path = ROOT / "dread_pickup_actors.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_special_pickups() -> Dict[str, dict]:
    """Boss/EMMI death pickups keyed by PickupIndex (callback-based, not actors)."""
    path = ROOT / "dread_special_pickups.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ap_location_for_pickup_index(pickup_index: int) -> Optional[int]:
    return pickup_index_to_ap_location().get(pickup_index)


@lru_cache(maxsize=1)
def ap_item_id_to_name() -> Dict[int, str]:
    """
    Archipelago item ID → name from worlds/metroid_dread/Items.py.

    Parsed locally so archipelago.gg rooms without a custom datapackage still
    resolve standard Dread item IDs (84000–84103, etc.).
    """
    import re

    text = _read_world_text("Items.py")
    mapping: Dict[int, str] = {}
    for name, offset in re.findall(r'"([^"]+)": ItemData\(base_id \+ (\d+)', text):
        mapping[84000 + int(offset)] = name
    return mapping


ResourceStage = List[dict]
ResourceProgression = List[ResourceStage]


def _normalize_progression(resources: Union[List[dict], ResourceProgression]) -> ResourceProgression:
    if not resources:
        return []
    if isinstance(resources[0], dict):
        return [list(resources)]  # type: ignore[list-item]
    return [list(stage) for stage in resources]  # type: ignore[union-attr]


def _resources_for_item_name(item_name: str) -> Optional[ResourceProgression]:
    """Return multi-stage resource progression for an AP item name."""
    try:
        from dread_item_mapping import get_resource_progression
    except ImportError:
        get_resource_progression = None  # type: ignore

    if get_resource_progression:
        progression = get_resource_progression(item_name)
        if progression:
            return progression

    extra = EXTRA_ITEM_RESOURCES.get(item_name)
    if extra:
        return _normalize_progression(extra)
    return None


def get_item_resources(item_name: str, item_id: Optional[int] = None) -> Optional[ResourceProgression]:
    """Return resource progression [[{item_id, quantity}, ...], ...] for an AP item name or ID."""
    progression = _resources_for_item_name(item_name)
    if progression:
        return progression

    resolved_id = item_id
    if resolved_id is None and item_name.startswith("Item "):
        try:
            resolved_id = int(item_name.split(" ", 1)[1])
        except ValueError:
            resolved_id = None

    if resolved_id is not None:
        local_name = ap_item_id_to_name().get(resolved_id)
        if local_name and local_name != item_name:
            return _resources_for_item_name(local_name)

    return None


def resources_to_lua_progression(progression: Union[List[dict], ResourceProgression]) -> str:
    """
    Build a Lua progression table string for RL.ReceivePickup.

    Shape matches open-dread-rando / Randovania remote pickup:
    {{{item_id=..., quantity=...}, ...}, {{...}, ...}}
    """
    stages = _normalize_progression(progression)
    parts = []
    for stage in stages:
        entries = []
        for resource in stage:
            item_id = resource["item_id"]
            qty = int(resource["quantity"])
            entries.append(f'{{item_id = "{item_id}", quantity = {qty}}}')
        parts.append("{" + ", ".join(entries) + "}")
    return "{" + ", ".join(parts) + "}"


def parent_for_resources(progression: Union[List[dict], ResourceProgression]) -> str:
    stages = _normalize_progression(progression)
    if not stages or not stages[0]:
        return "RandomizerPowerup"
    return ITEM_PARENT_BY_ID.get(stages[0][0]["item_id"], "RandomizerPowerup")


@lru_cache(maxsize=1)
def known_ap_item_names() -> Tuple[str, ...]:
    """
    All known AP item display names, for /give-style fuzzy matching.

    Union of dread_item_mapping.DREAD_ITEM_MAPPING keys, EXTRA_ITEM_RESOURCES
    keys, and the local Items.py id->name table, so newly added items (e.g.
    progressive/DNA variants) are matchable without touching this helper.
    """
    try:
        from dread_item_mapping import DREAD_ITEM_MAPPING
    except ImportError:
        DREAD_ITEM_MAPPING = {}
    names: Set[str] = set(DREAD_ITEM_MAPPING.keys())
    names.update(EXTRA_ITEM_RESOURCES.keys())
    names.update(ap_item_id_to_name().values())
    return tuple(sorted(names))


def resolve_debug_item_name(
    requested: str, limit: int = 5
) -> Tuple[Optional[str], List[str]]:
    """
    Resolve a user-typed /give argument against known AP Dread item names.

    Tries an exact case-insensitive match, then a substring match, then a
    difflib fuzzy match. Returns (resolved_name, suggestions):
      - resolved_name is set only when the match is unambiguous.
      - suggestions holds up to `limit` close names for a helpful error
        message when nothing was unambiguously resolved.
    """
    import difflib

    query = requested.strip()
    if not query:
        return None, []

    names = known_ap_item_names()
    by_lower = {name.lower(): name for name in names}

    exact = by_lower.get(query.lower())
    if exact:
        return exact, []

    query_lower = query.lower()
    substring_hits = [name for name in names if query_lower in name.lower()]
    if len(substring_hits) == 1:
        return substring_hits[0], []

    fuzzy = difflib.get_close_matches(query, names, n=limit, cutoff=0.5)
    candidates = substring_hits or fuzzy
    if len(candidates) == 1:
        return candidates[0], []

    suggestions = list(dict.fromkeys(substring_hits + fuzzy))[:limit]
    if not suggestions:
        # Widen the net purely for error-message suggestions (not auto-resolve)
        # so typos still get a "did you mean" instead of a bare "not found".
        suggestions = difflib.get_close_matches(query, names, n=limit, cutoff=0.2)
    return None, suggestions


def format_dna_debug_give_lua(item_name: str) -> str:
    """Local /give Metroid DNA — grants next ITEM_RANDO_ARTIFACT_N in-game."""
    safe_name = item_name.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "do "
        "local ok, err = pcall(function() "
        "  local granted = RandomizerPowerup.GrantNextArtifact(); "
        "  if granted == nil then error('all required artifacts already owned') end "
        "end); "
        "if ok then "
        f'if RL.SendApLog then RL.SendApLog("AP_GIVE: granted {safe_name}") end; '
        "if Scenario and Scenario.IsUserInteractionEnabled and Scenario.QueueAsyncPopup "
        "and Scenario.IsUserInteractionEnabled(true) then "
        f'pcall(function() Scenario.QueueAsyncPopup("Debug: received {safe_name}.", 5.0) end) '
        "end "
        "else "
        f'if RL.SendApLog then RL.SendApLog("AP_GIVE_FAIL: {safe_name} - "..tostring(err)) end '
        "end "
        "end"
    )


def format_dna_receive_lua(message: str, received_pickups: int, inventory_index: int) -> str:
    """
    Grant Metroid DNA from the AP server via the next free artifact slot.

    Uses RandomizerPowerup.GrantNextArtifact (ODR CheckArtifacts / HUD / Itorash
    gate) instead of a fixed ITEM_RANDO_ARTIFACT_N progression table.
    """
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "do "
        f'local msg = "{safe_message}"; '
        f"local idx = {int(received_pickups)}; "
        f"local inv = {int(inventory_index)}; "
        "if RL and RL.ReceivedPickups and RL.InventoryIndex "
        "and idx == RL.ReceivedPickups() and inv == RL.InventoryIndex() "
        "and not RL.PendingPickup then "
        "  local ok, err = pcall(function() "
        "    local granted = RandomizerPowerup.GrantNextArtifact(); "
        "    if granted == nil then Game.LogWarn(0, 'AP DNA: all artifacts already collected') end "
        "  end); "
        "  if not ok then Game.LogWarn(0, 'AP DNA grant failed: '..tostring(err)) end; "
        '  Scenario.WriteToPlayerBlackboard("ReceivedPickups","f",idx + 1); '
        "  if RL.SendReceivedPickups then RL.SendReceivedPickups(tostring(idx + 1)) end; "
        "  if Scenario and Scenario.IsUserInteractionEnabled and Scenario.QueueAsyncPopup "
        "and Scenario.IsUserInteractionEnabled(true) then "
        "    pcall(function() Scenario.QueueAsyncPopup(msg, 7.0) end) "
        "  end "
        "elseif RL and RL.GetReceivedPickupsAndSend then "
        '  Game.AddSF(0.05, "RL.GetReceivedPickupsAndSend", "b", false); '
        "end "
        "end"
    )


def format_debug_give_lua(item_name: str, progression: Union[List[dict], ResourceProgression]) -> str:
    """
    Build Lua for the client's local /give debug command.

    Grants `progression` through the same OnPickedUp handler real pickups use
    (RandomizerPowerup / RandomizerWideBeam / etc.) so progressive items and
    energy/ammo side effects behave correctly, but WITHOUT touching the
    ReceivedPickups/InventoryIndex blackboard counters that back multiworld
    sync. This must stay local-only: never call it in place of
    RL.ReceivePickup, and never pair it with a LocationCheck send.
    """
    if is_dna_item(item_name):
        return format_dna_debug_give_lua(item_name)
    parent = parent_for_resources(progression)
    progression_lua = resources_to_lua_progression(progression)
    safe_name = item_name.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "do "
        f"local cls = {parent} or RandomizerPowerup; "
        f"local progression = {progression_lua}; "
        "local ok, err = pcall(function() cls.OnPickedUp(nil, progression) end); "
        "if ok then "
        f'if RL.SendApLog then RL.SendApLog("AP_GIVE: granted {safe_name}") end; '
        "if Scenario and Scenario.IsUserInteractionEnabled and Scenario.QueueAsyncPopup "
        "and Scenario.IsUserInteractionEnabled(true) then "
        f'pcall(function() Scenario.QueueAsyncPopup("Debug: received {safe_name}.", 5.0) end) '
        "end "
        "else "
        f'if RL.SendApLog then RL.SendApLog("AP_GIVE_FAIL: {safe_name} - "..tostring(err)) end '
        "end "
        "end"
    )


def inventory_item_ids() -> List[str]:
    """Ordered inventory item_id list for RL.InventoryItems bootstrap."""
    try:
        from dread_item_mapping import DREAD_ITEM_MAPPING
    except ImportError:
        DREAD_ITEM_MAPPING = {}

    seen = set()
    ordered: List[str] = []
    for entry in DREAD_ITEM_MAPPING.values():
        for stage in _normalize_progression(entry.get("resources", [])):
            for resource in stage:
                item_id = resource["item_id"]
                if item_id not in seen and item_id != "ITEM_NONE":
                    seen.add(item_id)
                    ordered.append(item_id)
    for resources in EXTRA_ITEM_RESOURCES.values():
        for resource in resources:
            item_id = resource["item_id"]
            if item_id not in seen and item_id != "ITEM_NONE":
                seen.add(item_id)
                ordered.append(item_id)
    return ordered


@lru_cache(maxsize=1)
def _item_id_to_ap_rules() -> Dict[str, Tuple[str, int]]:
    """
    Map game item_id -> (AP item name, quantity-per-copy).
    Prefer non-progressive AP names so logic can see Charge Beam / Morph Ball etc.
    """
    try:
        from dread_item_mapping import DREAD_ITEM_MAPPING
    except ImportError:
        DREAD_ITEM_MAPPING = {}

    rules: Dict[str, Tuple[str, int]] = {}

    def consider(ap_name: str, item_id: str, qty: int) -> None:
        if not item_id or item_id == "ITEM_NONE" or qty <= 0:
            return
        # Prefer concrete item names over Progressive* aliases for the same item_id.
        prev = rules.get(item_id)
        if prev is None or str(prev[0]).startswith("Progressive"):
            rules[item_id] = (ap_name, int(qty))

    for ap_name, entry in DREAD_ITEM_MAPPING.items():
        resources = entry.get("resources", [])
        stages = _normalize_progression(resources)
        for stage in stages:
            for resource in stage:
                consider(ap_name, resource.get("item_id", ""), int(resource.get("quantity", 1) or 1))
    for ap_name, resources in EXTRA_ITEM_RESOURCES.items():
        for resource in resources:
            consider(ap_name, resource.get("item_id", ""), int(resource.get("quantity", 1) or 1))

    # Explicit logical aliases used by DreadLogic (override progressive/shared ids).
    rules["ITEM_GHOST_AURA"] = ("Flash Shift", 1)
    rules["ITEM_UPGRADE_FLASH_SHIFT_CHAIN"] = ("Flash Shift Upgrade", 1)
    return rules


def counts_from_inventory_amounts(amounts: List[int]) -> Dict[str, int]:
    """Convert RL inventory quantity array into AP item-name counts for logic."""
    ids = inventory_item_ids()
    rules = _item_id_to_ap_rules()
    counts: Dict[str, int] = {}
    for i, item_id in enumerate(ids):
        if i >= len(amounts):
            break
        try:
            amount = int(amounts[i] or 0)
        except Exception:
            amount = 0
        if amount <= 0:
            continue
        rule = rules.get(item_id)
        if not rule:
            continue
        ap_name, unit = rule
        unit = max(1, int(unit))
        if item_id == "ITEM_MAX_LIFE":
            # Base energy is 99; each Energy Tank adds 100.
            n = max(0, (amount - 99) // 100)
        else:
            n = amount // unit
        if n <= 0:
            continue
        counts[ap_name] = max(counts.get(ap_name, 0), n)
    # Flash Shift Upgrade implies Flash Shift ability for logic.
    if counts.get("Flash Shift Upgrade", 0) >= 1:
        counts["Flash Shift"] = max(counts.get("Flash Shift", 0), 1)
    return counts


def counts_from_starting_items(starting_items: Dict[str, int]) -> Dict[str, int]:
    """Convert ODR patch_extras starting_items {ITEM_*: qty} → AP logic counts."""
    rules = _item_id_to_ap_rules()
    counts: Dict[str, int] = {}
    if not isinstance(starting_items, dict):
        return counts
    for item_id, qty in starting_items.items():
        try:
            amount = int(qty or 0)
        except Exception:
            amount = 0
        if amount <= 0:
            continue
        rule = rules.get(str(item_id))
        if not rule:
            continue
        ap_name, unit = rule
        unit = max(1, int(unit))
        n = amount // unit
        if n <= 0:
            continue
        counts[ap_name] = max(counts.get(ap_name, 0), n)
    if counts.get("Flash Shift Upgrade", 0) >= 1:
        counts["Flash Shift"] = max(counts.get("Flash Shift", 0), 1)
    return counts


def _lua_toplevel_split_indices(code: str) -> List[int]:
    """
    Return exclusive end indices of top-level Lua statements.

    Safe split points are only recorded when block/brace/paren depth is 0 and we
    are outside strings/comments — at ';' or at newline. This prevents the old
    packer bug of splitting on ';' inside \"a;b\" or '-- note; more'.
    """
    n = len(code)
    ends: List[int] = []
    i = 0
    block = 0
    braces = 0
    parens = 0
    ignore_next_do = False

    def is_ident_char(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    def at_word_boundary(pos: int) -> bool:
        return pos <= 0 or not is_ident_char(code[pos - 1])

    while i < n:
        c = code[i]

        # Line comment
        if c == "-" and i + 1 < n and code[i + 1] == "-":
            if i + 3 < n and code[i + 2] == "[" and code[i + 3] == "[":
                i += 4
                while i + 1 < n and not (code[i] == "]" and code[i + 1] == "]"):
                    i += 1
                i = min(i + 2, n)
                continue
            while i < n and code[i] not in "\r\n":
                i += 1
            continue

        # Strings
        if c == '"' or c == "'":
            quote = c
            i += 1
            while i < n:
                ch = code[i]
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
                if ch == quote:
                    break
            continue

        # Long bracket strings [[...]] / [=[...]=]
        if c == "[" and i + 1 < n and code[i + 1] in "=[":
            j = i + 1
            eq = 0
            while j < n and code[j] == "=":
                eq += 1
                j += 1
            if j < n and code[j] == "[":
                close = "]" + ("=" * eq) + "]"
                i = j + 1
                idx = code.find(close, i)
                i = n if idx < 0 else idx + len(close)
                continue

        # Depth tracking for brackets
        if c == "{":
            braces += 1
            i += 1
            continue
        if c == "}":
            braces = max(0, braces - 1)
            i += 1
            continue
        if c == "(":
            parens += 1
            i += 1
            continue
        if c == ")":
            parens = max(0, parens - 1)
            i += 1
            continue

        # Keywords / identifiers that affect block depth
        if at_word_boundary(i) and (c.isalpha() or c == "_"):
            start = i
            i += 1
            while i < n and is_ident_char(code[i]):
                i += 1
            word = code[start:i]
            if word in ("function", "if", "for", "while", "repeat"):
                block += 1
                if word in ("for", "while"):
                    ignore_next_do = True
            elif word == "do":
                if ignore_next_do:
                    ignore_next_do = False
                else:
                    block += 1
            elif word == "end":
                block = max(0, block - 1)
                if block == 0 and braces == 0 and parens == 0:
                    ends.append(i)
            elif word == "until":
                block = max(0, block - 1)
                if block == 0 and braces == 0 and parens == 0:
                    ends.append(i)
            continue

        # Top-level statement terminators
        if block == 0 and braces == 0 and parens == 0:
            if c == ";":
                ends.append(i + 1)
            elif c == "\n":
                # Only split if there is non-whitespace before this newline in
                # the current statement (avoid blank-line spam).
                ends.append(i + 1)

        i += 1

    if n and (not ends or ends[-1] != n):
        ends.append(n)
    return ends


def split_lua_for_buffer(code: str, buffer_size: int) -> List[str]:
    """Split one Lua source unit into buffer-sized, independently executable pieces."""
    code = code.strip()
    if not code:
        return []
    if len(code) <= buffer_size:
        return [code]

    ends = _lua_toplevel_split_indices(code)
    segments: List[str] = []
    prev = 0
    for end in ends:
        seg = code[prev:end].strip()
        prev = end
        if seg:
            segments.append(seg)

    pieces: List[str] = []
    buf = ""
    for seg in segments:
        if not buf:
            if len(seg) > buffer_size:
                raise ValueError(
                    f"Lua statement length {len(seg)} exceeds buffer_size {buffer_size}; "
                    "refusing to hard-split mid-statement"
                )
            buf = seg
            continue
        candidate = f"{buf}\n{seg}"
        if len(candidate) <= buffer_size:
            buf = candidate
        else:
            pieces.append(buf)
            if len(seg) > buffer_size:
                raise ValueError(
                    f"Lua statement length {len(seg)} exceeds buffer_size {buffer_size}; "
                    "refusing to hard-split mid-statement"
                )
            buf = seg
    if buf:
        pieces.append(buf)
    return pieces


def pack_lua_chunks(chunks: List[str], buffer_size: int = 4096) -> List[str]:
    """
    Pack Lua source fragments into send units each <= buffer_size.

    Never splits on ';' inside strings/comments, and never byte-slices mid-statement
    (that produced LUA_ERRSYNTAX / \"error parsing buffer: 3\" on ODR/exlaunch).
    """
    packed: List[str] = []
    current = ""
    for code in chunks:
        for piece in split_lua_for_buffer(code, buffer_size):
            if not current:
                current = piece
                continue
            # Join packed units with ';' — safe because each piece is a complete
            # top-level statement sequence.
            candidate = f"{current};{piece}"
            if len(candidate) <= buffer_size:
                current = candidate
            else:
                packed.append(current)
                current = piece
    if current:
        packed.append(current)
    return packed


def lua_chunk_has_balanced_quotes(code: str) -> bool:
    """True if double/single quotes are balanced outside -- comments."""
    in_dq = in_sq = False
    i = 0
    n = len(code)
    while i < n:
        c = code[i]
        if not in_dq and not in_sq and c == "-" and i + 1 < n and code[i + 1] == "-":
            while i < n and code[i] not in "\r\n":
                i += 1
            continue
        if in_dq:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_dq = False
            i += 1
            continue
        if in_sq:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "'":
                in_sq = False
            i += 1
            continue
        if c == '"':
            in_dq = True
        elif c == "'":
            in_sq = True
        i += 1
    return not in_dq and not in_sq


def build_bootstrap_chunks(buffer_size: int = 4096) -> List[str]:
    """
    Build Lua bootstrap chunks compatible with Randovania's DreadExecutor.
    Uploads sync helpers + pickup index → Location_Collected_* mapping.
    """
    actors = load_pickup_actors()
    specials = load_special_pickups()
    # Indices in the bitfield are 0-based; Lua Pickups table is 1-based (index+1).
    max_index = 0
    for key in actors:
        max_index = max(max_index, int(key))
    for key in specials:
        max_index = max(max_index, int(key))
    # Include boss/special indices present in AP map but maybe not in actors json
    for pickup_index in pickup_index_to_ap_location():
        max_index = max(max_index, pickup_index)
    num_nodes = max_index + 1

    inventory = "{" + ",".join(repr(i) for i in inventory_item_ids()) + "}"

    boss_index_entries: List[str] = []
    for index_str, data in specials.items():
        loc_key = f'{data["scenario"]}_{data["callback_function"]}'
        boss_index_entries.append(f'["{loc_key}"]={int(index_str)}')
    boss_index_lua = "{" + ",".join(boss_index_entries) + "}"

    # After DoFile: ensure AP progressive Flash Shift Upgrade exists even when the
    # installed randomizer_powerup.lua is stock ODR (no RandomizerFlashShiftUpgrade).
    # Without this class, RL.ConfirmPickup errors → ReceivedPickups never advances →
    # the client re-sends the same RL.ReceivePickup forever (popup loop).
    part0 = f"""
Game.DoFile('actors/items/randomizer_powerup/scripts/randomizer_powerup.lua')
if RandomizerPowerup and not RandomizerPowerup._APFlashUpgradeHooked then
    RandomizerPowerup._APFlashUpgradeHooked = true
    local _APIncreaseItemAmount = RandomizerPowerup.IncreaseItemAmount
    function RandomizerPowerup.IncreaseItemAmount(item_id, quantity, capacity)
        if item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" and quantity and quantity > 0 then
            if not RandomizerPowerup.HasItem("ITEM_GHOST_AURA") then
                RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
                Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
                quantity = 0
            end
        end
        return _APIncreaseItemAmount(item_id, quantity, capacity)
    end
end
RandomizerFlashShiftUpgrade = RandomizerFlashShiftUpgrade or {{}}
setmetatable(RandomizerFlashShiftUpgrade, {{__index = RandomizerPowerup}})
function RandomizerFlashShiftUpgrade.OnPickedUp(actor, progression)
    progression = progression or {{{{{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 1}}}}}}
    local first = not RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    if first then
        RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
        Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
        for _, resource_list in ipairs(progression) do
            for _, resource in ipairs(resource_list) do
                if resource.item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" then
                    resource.quantity = 0
                end
            end
        end
    end
    RandomizerPowerup.OnPickedUp(actor, progression)
end
if not RL then RL = {{}} end
-- Harden ODR Scenario.SetTunableValue: nil category/property (or failed
-- GetTunableData) used to nil-concat inside the engine helper and abort EXEC.
if Scenario and not Scenario._APSafeSetTunable then
    Scenario._APSafeSetTunable = true
    function Scenario.SetTunableValue(category, property, value)
        if category == nil or property == nil then
            error("SetTunableValue: category/property must be strings, got "
                .. tostring(category) .. ", " .. tostring(property))
        end
        if type(msemenu) ~= "table" or type(msemenu.GetTunableData) ~= "function" then
            error("SetTunableValue: msemenu.GetTunableData missing")
        end
        local ok, td = pcall(msemenu.GetTunableData, category, property)
        if (not ok) or td == nil or td.category == nil or td.property == nil then
            error("SetTunableValue: GetTunableData failed for "
                .. tostring(category) .. "." .. tostring(property)
                .. " (" .. tostring(td) .. ")")
        end
        td.category[td.property] = value
    end
end
RL.Pickups = {{}}
RL.BossPickupIndexByLocation = {boss_index_lua}
function RL.GetCollectedIndicesAndSend()
    -- Boss/EMMI death callbacks often run outside INGAME / with CurrentScenarioID
    -- unset. Prefer player blackboard presence over scenario id.
    local p = Game.GetPlayerBlackboardSectionName()
    if not p then return "not-in-game" end
    local r,v,i = {{}},0,1
    for _,t in ipairs(RL.Pickups) do
        if t ~= '' and Blackboard.GetProp(p,t) then v=v+i end
        i=i*2;if i>=256 then table.insert(r,string.char(v));v=0;i=1 end
    end
    if i>1 then table.insert(r,string.char(v)) end
    RL.SendIndices("locations:"..table.concat(r))
end
for i=1,{num_nodes} do RL.Pickups[i]='' end
""".strip()

    part1 = f"""
function RL.GetInventoryAndSend()
    local r={{}}
    for i,n in ipairs(RL.InventoryItems) do
        r[i]=RandomizerPowerup.GetItemAmount(n)
    end
    local inventory = string.format("[%s]",table.concat(r,","))
    local currentIndex = string.format('"index": %s', RL.InventoryIndex())
    RL.SendInventory(string.format('{{%s,"inventory":%s}}', currentIndex, inventory))
end
RL.InventoryItems={inventory}
""".strip()

    part2 = """
function RL.InventoryIndex()
    local playerSection =  Game.GetPlayerBlackboardSectionName()
    return Blackboard.GetProp(playerSection, "InventoryIndex") or 0
end
function RL.ReceivedPickups()
    local playerSection =  Game.GetPlayerBlackboardSectionName()
    return Blackboard.GetProp(playerSection, "ReceivedPickups") or 0
end
function RL.GetReceivedPickupsAndSend(reset)
    if reset then
        RL.PendingPickup = nil
    end
    RL.SendReceivedPickups(tostring(RL.ReceivedPickups()))
end
function RL.GivePendingPickup()
    if Scenario.IsUserInteractionEnabled(true) then
        Scenario.QueueAsyncPopup(RL.PendingPickup.msg, 7.0)
        Game.AddSF(7.5, "RL.GetReceivedPickupsAndSend", "b", true)
        RL.ConfirmPickup()
    else
        Game.AddSF(0.5, "RL.GivePendingPickup", "")
    end
end
function RL.ConfirmPickup()
    -- Always advance ReceivedPickups even if the grant errors. Otherwise the AP
    -- client keeps re-sending the same RL.ReceivePickup (infinite popup loop).
    local ok, err = pcall(function()
        local cls = RL.PendingPickup.cls
        if cls == nil or type(cls) ~= "table" or cls.OnPickedUp == nil then
            cls = RandomizerPowerup
        end
        cls.OnPickedUp(nil, RL.PendingPickup.progression)
    end)
    if not ok then
        Game.LogWarn(0, "AP ConfirmPickup grant failed: " .. tostring(err))
    end
    Scenario.WriteToPlayerBlackboard("ReceivedPickups","f",RL.ReceivedPickups()+1)
end
function RL.ReceivePickup(msg,cls,progression_string,receivedPickupIndex,inventoryIndex)
    if not RL.PendingPickup then
        if receivedPickupIndex == RL.ReceivedPickups() and inventoryIndex == RL.InventoryIndex() then
            if cls == nil then
                cls = RandomizerPowerup
            end
            progression = assert(loadstring("return " .. progression_string))()
            RL.PendingPickup={cls=cls,progression=progression,msg=msg}
            Game.AddSF(0, "RL.GivePendingPickup", "")
        else
            Game.AddSF(0, "RL.GetInventoryAndSend", "")
            Game.AddSF(0.05, "RL.GetReceivedPickupsAndSend", "b", false)
        end
    end
end
""".strip()

    part3 = """
function RL.GetGameStateAndSend()
    local current_state = Game.GetCurrentGameModeID()
    local current_scenario = ""
    local has_beaten = Init.bBeatenSinceLastReboot
    if current_state == 'INGAME' then
        current_scenario = Game.GetScenarioID()
    else
        current_scenario = current_state
    end
    RL.SendNewGameState(current_scenario .. ";" .. tostring(has_beaten))
end
function RL.UpdateRDVClient(new_scenario)
    RL.GetGameStateAndSend()
    -- Always sync collected locations (boss/EMMI death callbacks often run outside INGAME).
    if RL.GetCollectedIndicesAndSend then
        pcall(RL.GetCollectedIndicesAndSend)
    end
    Game.AddSF(0.05, "RL.GetCollectedIndicesAndSend", "")
    Game.AddSF(1.0, "RL.GetCollectedIndicesAndSend", "")
    if Game.GetCurrentGameModeID() == 'INGAME' then
        if new_scenario == true then
            RL.PendingPickup = nil
        end
        -- Re-paint reachable dim after scenario load (VisitBoundsSafe is grid-local).
        if RL.LastReachable and next(RL.LastReachable) ~= nil and RL.ApplyReachableMap then
            Game.AddSF(3.0, "RL.ReapplyLastReachable", "")
        end
        -- Re-apply collected map-icon labels (OdrText is in-memory; reload/death can drop it).
        if RL.ReapplyLastMapIconLabels then
            if (RL.LastMapIconVariants and next(RL.LastMapIconVariants) ~= nil)
                or (RL.LastMapIconLabels and next(RL.LastMapIconLabels) ~= nil) then
                Game.AddSF(3.0, "RL.ReapplyLastMapIconLabels", "")
            end
        end
        -- Same for icon graphics: minimap.bmmdef is re-parsed on scenario load.
        if RL.ReapplyLastMapIconSprites and RL.LastMapIconSprites
            and next(RL.LastMapIconSprites) ~= nil then
            Game.AddSF(3.0, "RL.ReapplyLastMapIconSprites", "")
        end
        if RL.ReapplyLastMapIconGlobals and RL.LastMapIconGlobals
            and next(RL.LastMapIconGlobals) ~= nil then
            Game.AddSF(3.0, "RL.ReapplyLastMapIconGlobals", "")
        end
        RL.CheckDeath()
        local playerSection =  Game.GetPlayerBlackboardSectionName()
        local currentSaveRandoIdentifier = Blackboard.GetProp(playerSection, "THIS_RANDO_IDENTIFIER")
        if currentSaveRandoIdentifier ~= Init.sThisRandoIdentifier then
            return
        end
        Game.AddSF(0, "RL.GetInventoryAndSend", "")
        if RL.PendingPickup == nil then
            Game.AddSF(0.05, "RL.GetReceivedPickupsAndSend", "b", false)
        end
    end
end
-- DeathLink state: NEVER clear DeathHookInstalled / DeathCheckScheduled on
-- reconnect bootstrap — that nests OnPlayerDead wrappers and stacks AddSF loops
-- (double DeathLink + double ODR death-counter increments).
if RL.DeathHookInstalled == nil then RL.DeathHookInstalled = false end
if RL.DeathCheckScheduled == nil then RL.DeathCheckScheduled = false end
if RL.DeathPollGeneration == nil then RL.DeathPollGeneration = 0 end
if RL.LastKnownDeathCount == nil then RL.LastKnownDeathCount = nil end
-- Fresh episode flags only when not already mid-death (reconnect while dead).
if not RL.DeathSent then
    RL.DeathFromRemote = false
    RL.WasAlive = true
    RL.DeathPending = false
end
function RL.SendApLog(message)
    if RL.SendLog then
        RL.SendLog(message)
    else
        Game.LogWarn(0, message)
    end
end
function RL.GetEffectiveHealth()
    local playerSection = Game.GetPlayerBlackboardSectionName()
    local bb_health = Blackboard.GetProp(playerSection, "ITEM_CURRENT_LIFE")
    local item_health = Game.GetItemAmount(Game.GetPlayerName(), "ITEM_CURRENT_LIFE")
    local life_health = nil
    local player = Game.GetPlayer()
    if player ~= nil and player.LIFE ~= nil then
        life_health = player.LIFE.fCurrentLife
    end
    local effective = nil
    for _, value in ipairs({bb_health, item_health, life_health}) do
        if value ~= nil then
            value = tonumber(value)
            if value ~= nil then
                if effective == nil or value < effective then
                    effective = value
                end
            end
        end
    end
    return effective or 100.0
end
function RL.GetMaxHealth()
    local playerSection = Game.GetPlayerBlackboardSectionName()
    return Blackboard.GetProp(playerSection, "ITEM_MAX_LIFE") or 100.0
end
function RL.GetPlayerDeathCount()
    local count = Blackboard.GetProp("GAME", "ProgressStat_PlayerDeaths")
    if type(count) == "number" then
        return count
    end
    count = Blackboard.GetProp("GAME", "Rando_PlayerDeathCount")
    if type(count) == "number" then
        return count
    end
    return 0
end
function RL.MarkLocalDeath(reason)
    -- One AP_DEATH log per death. Remote kills set DeathFromRemote first.
    -- Shared latch for OnPlayerDead hook + CheckDeath poll (health / death_count).
    if RL.DeathFromRemote then
        return false
    end
    if RL.DeathSent then
        return false
    end
    RL.DeathSent = true
    RL.WasAlive = false
    RL.DeathPending = true
    RL.DeathPollGeneration = (RL.DeathPollGeneration or 0) + 1
    RL.SendApLog("AP_DEATH: Player died")
    -- Labels are BTXT mutations; re-apply after death/respawn like scenario load.
    if RL.ReapplyLastMapIconLabels then
        if (RL.LastMapIconVariants and next(RL.LastMapIconVariants) ~= nil)
            or (RL.LastMapIconLabels and next(RL.LastMapIconLabels) ~= nil) then
            Game.AddSF(1.0, "RL.ReapplyLastMapIconLabels", "")
            Game.AddSF(3.0, "RL.ReapplyLastMapIconLabels", "")
        end
    end
    if RL.ReapplyLastMapIconSprites and RL.LastMapIconSprites
        and next(RL.LastMapIconSprites) ~= nil then
        Game.AddSF(1.0, "RL.ReapplyLastMapIconSprites", "")
        Game.AddSF(3.0, "RL.ReapplyLastMapIconSprites", "")
    end
    if RL.ReapplyLastMapIconGlobals and RL.LastMapIconGlobals
        and next(RL.LastMapIconGlobals) ~= nil then
        Game.AddSF(1.0, "RL.ReapplyLastMapIconGlobals", "")
        Game.AddSF(3.0, "RL.ReapplyLastMapIconGlobals", "")
    end
    return true
end
function RL.InstallDeathHook()
    -- Idempotent across /connect_dread bootstrap. ODR death_counter.lua also wraps
    -- OnPlayerDead — we must call that chain exactly once (never nest our wrapper).
    if RL.DeathHookInstalled then
        return
    end
    if DamagePlants == nil or DamagePlants.OnPlayerDead == nil then
        return
    end
    if RL._APDeathHookFn ~= nil and DamagePlants.OnPlayerDead == RL._APDeathHookFn then
        RL.DeathHookInstalled = true
        return
    end
    local original_OnPlayerDead = DamagePlants.OnPlayerDead
    local hook = function(...)
        -- Call prior chain once (vanilla and/or ODR death_counter). Do not
        -- increment Rando_PlayerDeathCount ourselves — ODR owns the HUD counter.
        original_OnPlayerDead(...)
        RL.MarkLocalDeath("OnPlayerDead")
    end
    RL._APDeathHookFn = hook
    DamagePlants.OnPlayerDead = hook
    RL.DeathHookInstalled = true
    RL.SendApLog("AP: Death hook installed (DamagePlants.OnPlayerDead)")
end
function RL.GetDeathPollStatus()
    RL.InstallDeathHook()
    local mode = Game.GetCurrentGameModeID()
    local health = RL.GetEffectiveHealth()
    local max_health = RL.GetMaxHealth()
    local deaths = RL.GetPlayerDeathCount()
    local pending = RL.DeathPending and 1 or 0
    local gen = RL.DeathPollGeneration or 0
    return string.format(
        "%s,%.1f,%.1f,%d,%d,%d,%s,%s",
        mode,
        health,
        max_health,
        deaths,
        pending,
        gen,
        tostring(RL.WasAlive),
        tostring(RL.DeathSent)
    )
end
function RL.CheckDeath()
    RL.InstallDeathHook()
    local mode = Game.GetCurrentGameModeID()
    local current_health = RL.GetEffectiveHealth()
    local max_health = RL.GetMaxHealth()
    local death_count = RL.GetPlayerDeathCount()
    if RL.LastKnownDeathCount == nil then
        RL.LastKnownDeathCount = death_count
    elseif death_count > RL.LastKnownDeathCount then
        RL.LastKnownDeathCount = death_count
        -- Latch shared with OnPlayerDead — no second AP_DEATH if hook already fired.
        RL.MarkLocalDeath("death_count")
    end
    if current_health <= 0 and RL.WasAlive then
        RL.MarkLocalDeath("health")
    elseif (
        current_health > (max_health * 0.5)
        and not RL.WasAlive
        and mode == "INGAME"
        and RL.DeathSent
    ) then
        -- Only after a marked death, once health is clearly restored.
        RL.DeathSent = false
        RL.DeathFromRemote = false
        RL.WasAlive = true
        RL.DeathPending = false
        RL.SendApLog("AP_DEATH: Player respawned")
    elseif current_health > 0 and mode == "INGAME" and RL.WasAlive and not RL.DeathSent then
        RL.DeathPending = false
    end
end
function RL.ScheduleDeathCheck()
    RL.CheckDeath()
    Game.AddSF(0.25, "RL.ScheduleDeathCheck", "")
end
RL.InstallDeathHook()
if not RL.DeathCheckScheduled then
    RL.DeathCheckScheduled = true
    Game.AddSF(0.25, "RL.ScheduleDeathCheck", "")
end
RL.SendApLog("AP: DeathLink detection active (poll + OnPlayerDead hook)")
RL.APConnected = true
RL.Bootstrap = true
""".strip()

    # Reachable minimap: ApplyReachableMap → VisitBoundsSafe dim paint (flag=4)
    # (needs OdrMap binder + ap_reachable_map_cells.lua for area bounds).
    # Fillmap SetMinimapRegionVisited supplement is OFF (MapFillmapPaintEnabled=false).
    # NEVER call legacy OdrMap.VisitBounds (0xe3b1b0+6; MapNativePaintEnabled stays
    # false). Physical-OR: never revert walk visits (bright = walked). Dim
    # force-save / dim-layout bootstrap is intentionally omitted.
    fillmap_lua_path = ROOT / "data" / "fillmap_actors.lua"
    fillmap_embed = ""
    if fillmap_lua_path.is_file():
        # Drop auto-gen header comments; keep executable lines.
        fillmap_embed = "\n".join(
            ln
            for ln in fillmap_lua_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("--")
        )
    part_map_head = f"""
if not RL then RL = {{}} end
RL.MapBinderWarned = RL.MapBinderWarned or false
RL.MapBoundsLoadedLogged = RL.MapBoundsLoadedLogged or false
RL.MapFillmapLogged = RL.MapFillmapLogged or false
RL.MapBoundsPaintLastSig = RL.MapBoundsPaintLastSig or ""
RL.LastReachable = RL.LastReachable or {{}}
-- Legacy VisitBounds (0xe3b1b0+6) stays crash-guarded forever. Full-room paint uses
-- VisitBoundsSafe instead; do NOT flip this on.
if RL.MapNativePaintEnabled == nil then RL.MapNativePaintEnabled = false end
-- Bright cut_fillmap_* via SetMinimapRegionVisited (flag=6): OFF for reachable paint.
-- Keep VisitFillmap / /map_smoke for manual A/B; dim AABB is VisitBoundsSafe only.
if RL.MapFillmapPaintEnabled == nil then RL.MapFillmapPaintEnabled = false end
-- Prefer dim/visible reachable AABB (flag=4). Bright (6) remains available for A/B.
-- No-op on older binders without the API; forces dim even if binary default drifts.
if OdrMap and OdrMap.SetVisitBoundsSafeFlag then
    pcall(OdrMap.SetVisitBoundsSafeFlag, 4)
end
-- Area → fillmap actor(s) for SetMinimapRegionVisited (not collision_camera_*).
{fillmap_embed}
-- Bright smoke: SetMinimapRegionVisited → entity-name lookup → flag=6.
-- Default = cut_fillmap_54 (Artaria Corpius Arena; confirmed). Alt: Watervalve_fillmap.
-- collision_camera_* asset_ids are BMSCC/logic keys — silent no-op as entity names.
function RL.MapPaintSmoke(assetId)
    local id = assetId
    if id == nil or id == "" then
        id = "cut_fillmap_54"
    end
    local mode, scen = "?", "?"
    pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)
    pcall(function() scen = tostring(Game.GetScenarioID()) end)
    if not Game.SetMinimapRegionVisited then
        RL.SendApLog("AP_MAP: region-visit smoke FAIL no-api id="..tostring(id).." mode="..mode.." scen="..scen)
        return "no-api"
    end
    local before = RL.ProbeVisitedCells(scen)
    local actor_found = "?"
    pcall(function()
        if Game.GetActor then
            local a = Game.GetActor(id)
            actor_found = (a ~= nil) and "yes" or "no"
        else
            actor_found = "no-GetActor"
        end
    end)
    local ret = nil
    local ok, err = pcall(function()
        ret = Game.SetMinimapRegionVisited(id)
    end)
    local after = RL.ProbeVisitedCells(scen)
    pcall(function()
        if minimap and minimap.SetProfileDataDirty then
            minimap.SetProfileDataDirty()
        end
    end)
    local delta = "?"
    if before ~= nil and after ~= nil then
        delta = tostring(after - before)
    end
    if not ok then
        RL.SendApLog("AP_MAP: region-visit smoke FAIL id="..tostring(id).." mode="..mode.." scen="..scen.." err="..tostring(err).." visited="..tostring(before).."->"..tostring(after).." actor="..actor_found)
        return "fail"
    end
    local verdict = "ok"
    if before ~= nil and after ~= nil and after == before then
        verdict = "noop"
    end
    RL.SendApLog("AP_MAP: region-visit smoke "..verdict.." id="..tostring(id).." mode="..mode.." scen="..scen.." ret="..tostring(ret).." visited="..tostring(before).."->"..tostring(after).." d="..delta.." actor="..actor_found)
    return verdict
end
-- Icon pop-out smoke: Game.ForceEntityIconVisible(actor). Does NOT touch VisitBoundsSafe /
-- MapNativePaintEnabled / bright paint. Default = Artaria Charge Tutorial Energy Tank.
function RL.MapIconSmoke(actorName)
    local id = actorName
    if id == nil or id == "" then
        id = "Item_EnergyTank001"
    end
    local mode, scen = "?", "?"
    pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)
    pcall(function() scen = tostring(Game.GetScenarioID()) end)
    if not Game.ForceEntityIconVisible then
        RL.SendApLog("AP_MAP: icon-smoke FAIL no-api actor="..tostring(id).." mode="..mode.." scen="..scen)
        return "no-api"
    end
    local actor_found = "?"
    pcall(function()
        if Game.GetActor then
            local a = Game.GetActor(id)
            actor_found = (a ~= nil) and "yes" or "no"
        else
            actor_found = "no-GetActor"
        end
    end)
    local ret = nil
    local ok, err = pcall(function()
        ret = Game.ForceEntityIconVisible(id)
    end)
    if not ok then
        RL.SendApLog("AP_MAP: icon-smoke FAIL actor="..tostring(id).." mode="..mode.." scen="..scen.." err="..tostring(err).." found="..actor_found)
        return "fail"
    end
    RL.SendApLog("AP_MAP: icon-smoke ok actor="..tostring(id).." mode="..mode.." scen="..scen.." ret="..tostring(ret).." found="..actor_found)
    return "ok"
end
-- Phase 2 collected map-icon labels (OdrText.SetLocalized).
-- Cache desired key→text; reapply on scenario load / death / connect push.
-- Does NOT touch VisitBoundsSafe / MapNativePaintEnabled / bright paint / item grants.
RL.LastMapIconLabels = RL.LastMapIconLabels or {{}}
RL.LastMapIconVariants = RL.LastMapIconVariants or {{}}
RL.MapIconLabelsRetryLeft = RL.MapIconLabelsRetryLeft or 0
-- Phase 3 icon graphics: iconId -> {{row, col}} in the minimap sprite atlas.
RL.LastMapIconSprites = RL.LastMapIconSprites or {{}}
RL.MapIconSpritesRetryLeft = RL.MapIconSpritesRetryLeft or 0
function RL.WarmLanguageBank()
    -- Passive only (0.1.6): never LoadBank/EnsureBank — both crash in Ryujinx.
    -- WarmBank is an alias of IsBankReady; no GetLocalized nudge (that used to force load).
    if OdrText and OdrText.IsBankReady then
        local pack = {{pcall(OdrText.IsBankReady)}}
        if pack[1] and pack[2] then
            return true
        end
    end
    return false
end
function RL.MapIconBankStatus()
    -- "version|ready|reason" for the client-side bank watch.
    --
    -- Returning the OdrText build string alongside readiness is deliberate:
    -- through 0.1.10 the readiness flag was stuck false forever (the native
    -- side read the language-manager holder instead of the manager), and the
    -- client had no way to tell "still loading" apart from "wrong subsdk9
    -- deployed". Logging the version with every probe makes that unambiguous.
    if not OdrText then
        return "no-OdrText|false|no-api"
    end
    local version = tostring(OdrText.Version or "?")
    if not OdrText.IsBankReady then
        return version.."|false|no-IsBankReady"
    end
    local pack = {{pcall(OdrText.IsBankReady)}}
    if not pack[1] then
        return version.."|false|err="..tostring(pack[2])
    end
    local ready = pack[2] and true or false
    return version.."|"..tostring(ready).."|"..tostring(pack[3] or "-")
end
function RL.CallSetLocalized(key, text)
    -- Pack multi-returns: pcall(ok, ret, reason). Plain "local a,b,c=pcall(...)"
    -- can drop reason on some Mercury Lua builds.
    -- (Python f-string: double braces → Lua table constructor.)
    -- Soft-fail only when bank not yet loaded by the game — do not force warm.
    local pack = {{pcall(function()
        return OdrText.SetLocalized(key, text)
    end)}}
    return pack[1], pack[2], pack[3]
end
function RL.SetMapIconLabel(key, text)
    if key == nil or key == "" then
        return "bad-key"
    end
    local t = text
    if t == nil then
        t = ""
    end
    if not OdrText or not OdrText.SetLocalized then
        return "no-api"
    end
    RL.LastMapIconLabels[key] = t
    local ok, ret, reason = RL.CallSetLocalized(key, t)
    if not ok then
        RL.SendApLog("AP_MAP: label FAIL key="..tostring(key).." text="..tostring(t).." err="..tostring(ret))
        return "fail"
    end
    if ret == true then
        RL.SendApLog("AP_MAP: label ok key="..tostring(key).." text="..tostring(t).." ret=true")
        return "ok"
    end
    RL.SendApLog("AP_MAP: label FAIL key="..tostring(key).." text="..tostring(t).." ret="..tostring(ret).." reason="..tostring(reason or "soft-fail"))
    return tostring(reason or "soft-fail")
end
function RL.ApplyMapIconLabels(labels)
    if type(labels) ~= "table" then
        return "bad-arg"
    end
    -- Merge (see RL.ApplyMapIconVariants).
    for key, text in pairs(labels) do
        RL.LastMapIconLabels[key] = text
    end
    if not OdrText or not OdrText.SetLocalized then
        RL.SendApLog("AP_MAP: labels FAIL no-OdrText n="..tostring((function()
            local c = 0
            for _ in pairs(labels) do c = c + 1 end
            return c
        end)()))
        return "no-api"
    end
    -- Passive: soft-fail while bank not loaded by game (no WarmBank/LoadBank).
    local ok_n = 0
    local fail_n = 0
    local retryable = false
    local fail_samples = 0
    local sample_reason = nil
    for key, text in pairs(labels) do
        local ok, ret, reason = RL.CallSetLocalized(key, text)
        if ok and ret == true then
            ok_n = ok_n + 1
            if ok_n <= 3 then
                RL.SendApLog("AP_MAP: label ok key="..tostring(key).." text="..tostring(text).." ret=true")
            end
        else
            fail_n = fail_n + 1
            local why
            if not ok then
                why = "err="..tostring(ret)
                if sample_reason == nil then sample_reason = "err" end
            else
                why = "ret="..tostring(ret).." reason="..tostring(reason or "soft-fail")
                local r = tostring(reason or "")
                if sample_reason == nil then sample_reason = r ~= "" and r or "soft-fail" end
                if r == "bank-not-ready" or r == "not-ready" or r == "mgr-nil" or r == "key-missing" then
                    retryable = true
                end
            end
            if fail_samples < 6 then
                fail_samples = fail_samples + 1
                RL.SendApLog("AP_MAP: label FAIL key="..tostring(key).." text="..tostring(text).." "..why)
            end
        end
    end
    local prior_tries = RL.MapIconLabelsRetryLeft or 0
    local sig = tostring(ok_n).."|"..tostring(fail_n).."|"..tostring(sample_reason or "")
    if sig ~= RL.MapIconLabelsLastSig or fail_n == 0 or (prior_tries % 5 == 0) then
        RL.MapIconLabelsLastSig = sig
        RL.SendApLog("AP_MAP: labels apply ok n="..tostring(ok_n).." fail="..tostring(fail_n).." sample="..tostring(sample_reason or "-"))
    end
    if ok_n > 0 then
        pcall(function()
            if minimap and minimap.SetProfileDataDirty then
                minimap.SetProfileDataDirty()
            end
        end)
    end
    -- Soft-fail while language bank is still loading: retry with backoff.
    -- No hard retry-COUNT cap (a previous 20-try cap made this give up after
    -- ~10-15s and rely on unrelated game events to try again — see
    -- RL.ApplyMapIconVariants comment). Cap the backoff INTERVAL instead so
    -- this politely retries forever until the bank becomes ready.
    if fail_n > 0 and retryable then
        RL.MapIconLabelsRetryLeft = prior_tries + 1
        local delay = 2.0
        if RL.MapIconLabelsRetryLeft > 5 then delay = 4.0 end
        if RL.MapIconLabelsRetryLeft > 15 then delay = 8.0 end
        if Game.AddSF then
            Game.AddSF(delay, "RL.ReapplyLastMapIconLabels", "")
        end
    elseif fail_n == 0 then
        RL.MapIconLabelsRetryLeft = 0
    end
    return tostring(ok_n)
end
function RL.ReapplyLastMapIconLabels()
    if RL.LastMapIconVariants and next(RL.LastMapIconVariants) ~= nil and RL.ApplyMapIconVariants then
        return RL.ApplyMapIconVariants(RL.LastMapIconVariants)
    end
    if RL.LastMapIconLabels and next(RL.LastMapIconLabels) ~= nil then
        return RL.ApplyMapIconLabels(RL.LastMapIconLabels)
    end
    return "empty"
end
-- Preferred map-label path: redirect display key → patch-time variant key via
-- OdrMap.SetIconInspectorLabel (GetLocalized trampoline). No LoadBank/EnsureBank.
-- IMPORTANT: SetIconInspectorLabel only registers the redirect table inside
-- OdrText; it does nothing visually unless the native GetLocalized hook is
-- actually installed (OdrText.HasLabelRedirect == true). That hook is kept
-- disabled for hover-crash safety (see text_hooks.cpp), so redirect-only
-- pushes are currently a silent no-op — always fall through to
-- OdrText.SetLocalized(base, text) in that case. If a future build re-enables
-- a proven-safe native hook, HasLabelRedirect flips true and this
-- automatically prefers the lighter redirect path again.
function RL.ApplyMapIconVariants(variants)
    if type(variants) ~= "table" then
        return "bad-arg"
    end
    -- Merge (chunked pushes must all survive ReapplyLastMapIconLabels).
    for k, v in pairs(variants) do
        RL.LastMapIconVariants[k] = v
    end
    local has_redirect_fn = (OdrMap and OdrMap.SetIconInspectorLabel) and true or false
    local native_redirect_live = (OdrText and OdrText.HasLabelRedirect) and true or false
    local use_redirect = has_redirect_fn and native_redirect_live
    local use_setloc = (OdrText and OdrText.SetLocalized) and true or false
    if not has_redirect_fn and not use_setloc then
        RL.SendApLog("AP_MAP: variants FAIL no-SetIconInspectorLabel/no-OdrText")
        return "no-api"
    end
    local ok_n = 0
    local fail_n = 0
    local sample = nil
    local mode = use_redirect and "redirect" or "setloc"
    for base, spec in pairs(variants) do
        local variant = spec
        local text = nil
        if type(spec) == "table" then
            variant = spec.variant or spec[1]
            text = spec.text or spec[2]
        end
        local applied = false
        if use_redirect and variant ~= nil then
            local icon = tostring(base)
            if string.sub(icon, 1, 9) == "MAP_ICON_" then
                icon = string.sub(icon, 10)
            end
            local label = tostring(variant)
            if string.sub(label, 1, 1) ~= "#" then
                label = "#" .. label
            end
            local pack = {{pcall(function()
                return OdrMap.SetIconInspectorLabel(icon, label)
            end)}}
            if pack[1] and pack[2] then
                applied = true
            end
        end
        if (not applied) and use_setloc and text ~= nil then
            local ok, ret, reason = RL.CallSetLocalized(tostring(base), tostring(text))
            if ok and ret == true then
                applied = true
            elseif sample == nil then
                sample = tostring(base) .. " reason=" .. tostring(reason or ret)
            end
        end
        if applied then
            ok_n = ok_n + 1
        else
            fail_n = fail_n + 1
            if sample == nil then
                sample = tostring(base) .. "->" .. tostring(variant)
            end
        end
    end
    local prior_tries = RL.MapIconLabelsRetryLeft or 0
    local sig = tostring(ok_n) .. "|" .. tostring(fail_n) .. "|" .. mode
    if sig ~= RL.MapIconVariantsLastSig or fail_n == 0 or (prior_tries % 5 == 0) then
        RL.MapIconVariantsLastSig = sig
        RL.SendApLog(
            "AP_MAP: variants apply ok n=" .. tostring(ok_n)
            .. " fail=" .. tostring(fail_n)
            .. " mode=" .. mode
            .. " sample=" .. tostring(sample or "-")
        )
    end
    -- Icon widgets cache label text at map-build time; force a re-read (same
    -- fix as VisitBoundsSafe paint — see ODRMAP.md). No LoadBank/EnsureBank.
    if ok_n > 0 then
        pcall(function()
            if minimap and minimap.SetProfileDataDirty then
                minimap.SetProfileDataDirty()
            end
        end)
    end
    -- Retry SetLocalized soft-fails (bank-not-ready) without forcing LoadBank.
    -- No hard retry-COUNT cap: the language bank may take a long time (or a
    -- menu/scenario transition) to become ready, and giving up would leave
    -- labels stuck on their patch-time default forever. Cap the backoff
    -- INTERVAL instead so this politely retries forever.
    if fail_n > 0 and (not use_redirect) then
        RL.MapIconLabelsRetryLeft = prior_tries + 1
        local delay = 2.0
        if RL.MapIconLabelsRetryLeft > 5 then delay = 4.0 end
        if RL.MapIconLabelsRetryLeft > 15 then delay = 8.0 end
        if Game.AddSF then
            Game.AddSF(delay, "RL.ReapplyLastMapIconLabels", "")
        end
    elseif fail_n == 0 then
        RL.MapIconLabelsRetryLeft = 0
    end
    return tostring(ok_n)
end
-- Phase 3: swap the icon GRAPHIC (not just its label) on collect / AP hint.
--
-- OdrMap.SetIconSprite writes uSpriteRow/uSpriteCol straight into the parsed
-- minimap.bmmdef def, the same "mutate loaded data, install no hook" shape as
-- OdrText.SetLocalized. No language bank involved, so this path never touches
-- EnsureBank/LoadBank and cannot hit the hover-crash the GetLocalized redirect
-- did. ODR gives every AP pickup its own ItemCustom{{n}} def, so one write
-- repoints exactly one location's icon.
function RL.ApplyMapIconSprites(sprites)
    if type(sprites) ~= "table" then
        return "bad-arg"
    end
    -- Merge, never replace: the client chunks these across several 4096-byte
    -- pushes and ReapplyLastMapIconSprites must resend all of them.
    for icon, cell in pairs(sprites) do
        RL.LastMapIconSprites[icon] = cell
    end
    if not OdrMap or not OdrMap.SetIconSprite then
        RL.SendApLog("AP_MAP: sprites FAIL no-SetIconSprite (old subsdk9)")
        return "no-api"
    end
    local ok_n = 0
    local fail_n = 0
    local sample = nil
    local retryable = false
    for icon, cell in pairs(sprites) do
        local row, col
        if type(cell) == "table" then
            row = cell[1] or cell.row
            col = cell[2] or cell.col
        end
        if row == nil or col == nil then
            fail_n = fail_n + 1
            if sample == nil then sample = tostring(icon) .. " reason=bad-cell" end
        else
            local pack = {{pcall(function()
                return OdrMap.SetIconSprite(tostring(icon), row, col)
            end)}}
            if pack[1] and pack[2] then
                ok_n = ok_n + 1
            else
                fail_n = fail_n + 1
                local reason = pack[1] and tostring(pack[3] or "soft-fail") or ("err=" .. tostring(pack[2]))
                -- The map def is not resident during boot / scenario changes.
                if reason == "mgr-nil" or reason == "no-def" or reason == "bad-count" or reason == "bad-arrays" then
                    retryable = true
                end
                if sample == nil then sample = tostring(icon) .. " reason=" .. reason end
            end
        end
    end
    local prior_tries = RL.MapIconSpritesRetryLeft or 0
    local sig = tostring(ok_n) .. "|" .. tostring(fail_n)
    if sig ~= RL.MapIconSpritesLastSig or fail_n == 0 or (prior_tries % 5 == 0) then
        RL.MapIconSpritesLastSig = sig
        RL.SendApLog(
            "AP_MAP: sprites apply ok n=" .. tostring(ok_n)
            .. " fail=" .. tostring(fail_n)
            .. " sample=" .. tostring(sample or "-")
        )
    end
    -- Icon widgets cache their sprite cell at map-build time, same as labels.
    if ok_n > 0 then
        pcall(function()
            if minimap and minimap.SetProfileDataDirty then
                minimap.SetProfileDataDirty()
            end
        end)
    end
    -- Backoff interval, no retry-COUNT cap (see RL.ApplyMapIconVariants).
    if fail_n > 0 and retryable then
        RL.MapIconSpritesRetryLeft = prior_tries + 1
        local delay = 2.0
        if RL.MapIconSpritesRetryLeft > 5 then delay = 4.0 end
        if RL.MapIconSpritesRetryLeft > 15 then delay = 8.0 end
        if Game.AddSF then
            Game.AddSF(delay, "RL.ReapplyLastMapIconSprites", "")
        end
    elseif fail_n == 0 then
        RL.MapIconSpritesRetryLeft = 0
    end
    return tostring(ok_n)
end
function RL.ReapplyLastMapIconSprites()
    if RL.LastMapIconSprites and next(RL.LastMapIconSprites) ~= nil then
        return RL.ApplyMapIconSprites(RL.LastMapIconSprites)
    end
    return "empty"
end
-- "version|has_api|status" for the client-side icon-def watch, mirroring
-- RL.MapIconBankStatus so a stale subsdk9 is obvious in the log.
function RL.MapIconSpriteStatus()
    if not OdrMap then
        return "no-OdrMap|false|no-api"
    end
    local version = tostring(OdrMap.Version or "?")
    if not OdrMap.SetIconSprite then
        return version .. "|false|no-SetIconSprite"
    end
    local status = "?"
    if OdrMap.IconDefStatus then
        local pack = {{pcall(OdrMap.IconDefStatus)}}
        status = pack[1] and tostring(pack[2]) or ("err=" .. tostring(pack[2]))
    end
    return version .. "|true|" .. status
end
-- Phase 4 bonus: flip SMapIconDef.bIsGlobal so hinted icons appear on the
-- pause / world-map region selector. Cleared again when the icon is no longer
-- in the hinted set (collect still keeps the sprite; global is hint-driven).
RL.LastMapIconGlobals = RL.LastMapIconGlobals or {{}}
RL.MapIconGlobalsRetryLeft = RL.MapIconGlobalsRetryLeft or 0
RL.MapIconGlobalsLastSig = RL.MapIconGlobalsLastSig or ""
function RL.ApplyMapIconGlobals(globals_map)
    if type(globals_map) ~= "table" then
        return "bad-arg"
    end
    for icon, flag in pairs(globals_map) do
        RL.LastMapIconGlobals[icon] = flag and true or false
    end
    if not OdrMap or not OdrMap.SetIconGlobal then
        RL.SendApLog("AP_MAP: globals FAIL no-SetIconGlobal (old subsdk9)")
        return "no-api"
    end
    local ok_n = 0
    local fail_n = 0
    local sample = nil
    local retryable = false
    for icon, flag in pairs(globals_map) do
        local pack = {{pcall(function()
            return OdrMap.SetIconGlobal(tostring(icon), flag and true or false)
        end)}}
        if pack[1] and pack[2] then
            ok_n = ok_n + 1
        else
            fail_n = fail_n + 1
            local reason = pack[1] and tostring(pack[3] or "soft-fail") or ("err=" .. tostring(pack[2]))
            if reason == "mgr-nil" or reason == "no-def" or reason == "bad-count" or reason == "bad-arrays" then
                retryable = true
            end
            if sample == nil then sample = tostring(icon) .. " reason=" .. reason end
        end
    end
    local prior_tries = RL.MapIconGlobalsRetryLeft or 0
    local sig = tostring(ok_n) .. "|" .. tostring(fail_n)
    if sig ~= RL.MapIconGlobalsLastSig or fail_n == 0 or (prior_tries % 5 == 0) then
        RL.MapIconGlobalsLastSig = sig
        RL.SendApLog(
            "AP_MAP: globals apply ok n=" .. tostring(ok_n)
            .. " fail=" .. tostring(fail_n)
            .. " sample=" .. tostring(sample or "-")
        )
    end
    if ok_n > 0 then
        pcall(function()
            if minimap and minimap.SetProfileDataDirty then
                minimap.SetProfileDataDirty()
            end
        end)
    end
    if fail_n > 0 and retryable then
        RL.MapIconGlobalsRetryLeft = prior_tries + 1
        local delay = 2.0
        if RL.MapIconGlobalsRetryLeft > 5 then delay = 4.0 end
        if RL.MapIconGlobalsRetryLeft > 15 then delay = 8.0 end
        if Game.AddSF then
            Game.AddSF(delay, "RL.ReapplyLastMapIconGlobals", "")
        end
    elseif fail_n == 0 then
        RL.MapIconGlobalsRetryLeft = 0
    end
    return tostring(ok_n)
end
function RL.ReapplyLastMapIconGlobals()
    if RL.LastMapIconGlobals and next(RL.LastMapIconGlobals) ~= nil then
        return RL.ApplyMapIconGlobals(RL.LastMapIconGlobals)
    end
    return "empty"
end
-- Map-label smoke: OdrText.SetLocalized on one MAP_ICON_ItemCustom* key.
-- Does NOT touch VisitBoundsSafe / MapNativePaintEnabled / bright paint.
-- Default key: first existing MAP_ICON_ItemCustomN, else MAP_ICON_ItemCustom0.
-- Find keys: patched romfs system/localization/us_english.txt (MAP_ICON_ItemCustom*),
-- or minimap.bmmdef sInspectorLabel (#MAP_ICON_ItemCustomN).
function RL.MapLabelSmoke(key, text)
    local k = key
    local t = text
    if t == nil or t == "" then
        t = "Label Smoke OK"
    end
    local mode, scen = "?", "?"
    pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)
    pcall(function() scen = tostring(Game.GetScenarioID()) end)
    if not OdrText or not OdrText.SetLocalized then
        RL.SendApLog("AP_MAP: label-smoke FAIL no-OdrText mode="..mode.." scen="..scen)
        return "no-api"
    end
    -- Gated (0.1.6): never WarmBank/LoadBank. Soft-fail if bank not game-loaded.
    if OdrText.IsBankReady then
        local okb, ready = pcall(OdrText.IsBankReady)
        if not okb or ready == false then
            RL.SendApLog("AP_MAP: label-smoke soft-fail reason=bank-not-ready mode="..mode.." scen="..scen)
            return "soft-fail"
        end
    else
        RL.SendApLog("AP_MAP: label-smoke soft-fail reason=no-IsBankReady mode="..mode.." scen="..scen)
        return "soft-fail"
    end
    if k == nil or k == "" then
        k = "MAP_ICON_ItemCustom0"
        if OdrText.HasLocalized then
            for i = 0, 200 do
                local cand = "MAP_ICON_ItemCustom"..tostring(i)
                local ok, has = pcall(OdrText.HasLocalized, cand)
                if ok and has then
                    k = cand
                    break
                end
            end
        end
    end
    local ok, ret, reason = pcall(function()
        return OdrText.SetLocalized(k, t)
    end)
    if not ok then
        RL.SendApLog("AP_MAP: label-smoke FAIL key="..tostring(k).." mode="..mode.." scen="..scen.." err="..tostring(ret))
        return "fail"
    end
    -- SetLocalized returns ok, reason
    local set_ok = ret
    local set_reason = reason
    if set_ok == true then
        local got = "?"
        pcall(function()
            if OdrText.GetLocalized then
                local v = OdrText.GetLocalized(k)
                got = tostring(v)
            end
        end)
        RL.SendApLog("AP_MAP: label-smoke ok key="..tostring(k).." text="..tostring(t).." got="..got.." mode="..mode.." scen="..scen)
        return "ok"
    end
    RL.SendApLog("AP_MAP: label-smoke soft-fail key="..tostring(k).." reason="..tostring(set_reason).." mode="..mode.." scen="..scen)
    return "soft-fail"
end
function RL.VisitFillmap(name)
    if name == nil or name == "" then
        return false
    end
    if not Game.SetMinimapRegionVisited then
        return false
    end
    local ok = pcall(function()
        Game.SetMinimapRegionVisited(name)
    end)
    return ok == true
end
function RL.PaintReachableFillmaps(by_scenario)
    -- Current-scenario only: fillmap actors exist only while that scenario is loaded.
    if type(by_scenario) ~= "table" or not RL.AreaFillmaps then
        return 0
    end
    if not RL.IsInGameForMapPaint or not RL.IsInGameForMapPaint() then
        return 0
    end
    local scen = nil
    pcall(function() scen = tostring(Game.GetScenarioID()) end)
    if not scen or not RL.AreaFillmaps[scen] then
        return 0
    end
    local areas = by_scenario[scen]
    if type(areas) ~= "table" then
        return 0
    end
    local painted = 0
    local seen = {{}}
    for _, area in ipairs(areas) do
        local fms = RL.AreaFillmaps[scen][area]
        if type(fms) == "table" then
            for _, fm in ipairs(fms) do
                if fm and not seen[fm] then
                    seen[fm] = true
                    if RL.VisitFillmap(fm) then
                        painted = painted + 1
                    end
                end
            end
        end
    end
    if painted > 0 then
        pcall(function()
            if minimap and minimap.SetProfileDataDirty then
                minimap.SetProfileDataDirty()
            end
        end)
    end
    return painted
end
""".strip()
    part_map_tail = """
function RL.ProbeVisitedCells(scenario)
    if not scenario or not minimap or not minimap.GetNumVisitedCells then
        return nil
    end
    local ok, n = pcall(function() return minimap.GetNumVisitedCells(scenario) end)
    if ok then return n end
    return nil
end
function RL.EnsureMapBounds()
    -- Load area AABB table only (no dim FOW / RevealDim / RegionVisible spam).
    if not RL.MapAreaBounds then
        -- Resolves to system/scripts/ap_reachable_map_cells.lc via TOC/system.pkg
        -- (ODR pattern; loose romfs .lua alone is not enough).
        local ok, err = pcall(function()
            Game.DoFile("system/scripts/ap_reachable_map_cells.lua")
        end)
        if not ok and not RL.MapBoundsLoadedLogged then
            RL.SendApLog("AP_MAP: DoFile ap_reachable_map_cells.lua failed: "..tostring(err))
        end
    end
    if RL.MapAreaBounds then
        if not RL.MapBoundsLoadedLogged then
            RL.MapBoundsLoadedLogged = true
            RL.SendApLog("AP_MAP: area bounds table loaded")
        end
    else
        if not RL.MapBoundsLoadedLogged then
            RL.MapBoundsLoadedLogged = true
            RL.SendApLog("AP_MAP: area bounds missing (not in TOC/system.pkg or file too large — re-run finalize_mod / install_reachable_map_script)")
        end
    end
end
function RL.IsInGameForMapPaint()
    local ok, mode = pcall(Game.GetCurrentGameModeID)
    return ok and mode == "INGAME"
end
function RL.NativeVisitWriterReady()
    -- Legacy VisitBounds (0xe3b1b0+6) readiness — kept for diagnostics only.
    if OdrMap == nil then
        return false
    end
    if OdrMap.IsVisitWriterReady then
        local ok, ready = pcall(OdrMap.IsVisitWriterReady)
        if ok and ready then
            return true
        end
    end
    return OdrMap.HasVisitWriter == true
end
function RL.NativeVisitBoundsSafeReady()
    -- Full-room paint via VisitBoundsSafe (stackvt → 0xe3ad38 flag=4 dim default).
    -- Soft-fails are not latched; ready can flip true once mgr/grid is live.
    if OdrMap == nil or not OdrMap.VisitBoundsSafe then
        return false
    end
    if OdrMap.IsVisitBoundsSafeReady then
        local ok, ready = pcall(OdrMap.IsVisitBoundsSafeReady)
        if ok then
            return ready == true
        end
    end
    return OdrMap.HasVisitBoundsSafe == true
end
function RL.CanPaintReachableMap()
    -- Gate: INGAME + VisitBoundsSafe ready (or SetCellsVisited fallback).
    -- Never enable legacy VisitBounds via MapNativePaintEnabled.
    if not RL.IsInGameForMapPaint() then
        return false
    end
    if not RL.MapAreaBounds and not (OdrMap and OdrMap.SetCellsVisited and RL.MapAreaCells) then
        return false
    end
    if RL.NativeVisitBoundsSafeReady() then
        return true
    end
    if OdrMap and OdrMap.SetCellsVisited and RL.MapAreaCells then
        return true
    end
    return false
end
function RL.VisitAreaBounds(scenario, area)
    if not RL.IsInGameForMapPaint() then
        return false
    end
    local bounds = nil
    if RL.MapAreaBounds and RL.MapAreaBounds[scenario] then
        bounds = RL.MapAreaBounds[scenario][area]
    end
    if not bounds then
        return false
    end
    local x1,y1,x2,y2 = bounds[1], bounds[2], bounds[3], bounds[4]
    -- Prefer VisitBoundsSafe. Do NOT call legacy OdrMap.VisitBounds (SEGV).
    if OdrMap and OdrMap.VisitBoundsSafe then
        local ret = nil
        local ok = pcall(function()
            ret = OdrMap.VisitBoundsSafe(scenario, x1, y1, x2, y2)
        end)
        -- Soft-fail (ret=false) is per-call; never latch-disable the binder.
        if ok and ret then
            return true
        end
        return false
    end
    if OdrMap and OdrMap.SetCellsVisited and RL.MapAreaCells and RL.MapAreaCells[scenario] and RL.MapAreaCells[scenario][area] then
        local ok = pcall(function()
            OdrMap.SetCellsVisited(scenario, RL.MapAreaCells[scenario][area])
        end)
        if ok then
            return true
        end
    end
    return false
end
function RL.CountReachableAreas(by_scenario)
    local total = 0
    for _, areas in pairs(by_scenario) do
        if type(areas) == "table" then
            total = total + #areas
        end
    end
    return total
end
function RL.ApplyReachableMap(by_scenario)
    if type(by_scenario) ~= "table" then
        return "bad-arg"
    end
    RL.EnsureMapBounds()
    RL.LastReachable = by_scenario
    local total = RL.CountReachableAreas(by_scenario)
    -- AABB writer is current-grid only — paint this scenario's reachable rooms.
    local scen = nil
    pcall(function() scen = tostring(Game.GetScenarioID()) end)
    local painted = 0
    local failed = 0
    if not RL.CanPaintReachableMap() then
        if total > 0 and not RL.MapBinderWarned then
            RL.MapBinderWarned = true
            if not RL.IsInGameForMapPaint() then
                RL.SendApLog("AP_MAP: paint deferred — not INGAME ("..tostring(total).." areas queued)")
            elseif not RL.MapAreaBounds then
                RL.SendApLog("AP_MAP: paint skipped — area bounds not loaded ("..tostring(total).." areas queued). Need bounds-only ap_reachable_map_cells.lua in mod romfs.")
            elseif not (OdrMap and OdrMap.VisitBoundsSafe) then
                RL.SendApLog("AP_MAP: VisitBoundsSafe missing — need subsdk9 0.4.1-stackvt; fillmaps used when mapped")
                RL.SendApLog("AP_MAP: tip — while INGAME try /map_smoke_bounds Corpius Arena or /map_smoke (fillmap cutout)")
            elseif not RL.NativeVisitBoundsSafeReady() then
                RL.SendApLog("AP_MAP: VisitBoundsSafe not ready — reachability queued ("..tostring(total).." areas). Retry on scenario load.")
            else
                RL.SendApLog("AP_MAP: paint gated — queued "..tostring(total).." areas")
            end
        end
    elseif scen and type(by_scenario[scen]) == "table" then
        for _, area in ipairs(by_scenario[scen]) do
            if RL.VisitAreaBounds(scen, area) then
                painted = painted + 1
            else
                failed = failed + 1
            end
        end
        if painted > 0 then
            pcall(function()
                if minimap and minimap.SetProfileDataDirty then
                    minimap.SetProfileDataDirty()
                end
            end)
        end
        local flag = "?"
        pcall(function()
            if OdrMap and OdrMap.VisitBoundsSafeStatus then
                flag = tostring(OdrMap.VisitBoundsSafeStatus())
            end
        end)
        local sig = tostring(scen).."|"..tostring(painted).."|"..tostring(failed).."|"..flag
        if sig ~= RL.MapBoundsPaintLastSig then
            RL.MapBoundsPaintLastSig = sig
            RL.SendApLog("AP_MAP: reachable bounds paint ok n="..tostring(painted).." fail="..tostring(failed).." status="..flag)
        end
    end
    -- Fillmaps: optional bright supplement (flag=6). Default OFF — dim AABB only.
    local fill_n = 0
    if RL.MapFillmapPaintEnabled and RL.PaintReachableFillmaps then
        fill_n = RL.PaintReachableFillmaps(by_scenario) or 0
    end
    if fill_n > 0 then
        if not RL.MapFillmapLogged then
            RL.MapFillmapLogged = true
            RL.SendApLog("AP_MAP: fillmap paint ok n="..tostring(fill_n).." (SetMinimapRegionVisited supplement; not VisitBounds/collision_camera)")
        else
            RL.SendApLog("AP_MAP: fillmap paint n="..tostring(fill_n))
        end
    end
    if painted == 0 and fill_n == 0 and total > 0 then
        return "queued"
    end
    return tostring(painted + fill_n)
end
function RL.ReapplyLastReachable()
    if RL.LastReachable and next(RL.LastReachable) ~= nil then
        return RL.ApplyReachableMap(RL.LastReachable)
    end
    return "empty"
end
-- Physical-OR policy: do NOT hook/revert guicallbacks.OnMinimapCellVisited.
-- Native walk visits stay; AP OR-reveals via VisitBoundsSafe dim only.
-- Bright = physically visited (or manual /map_smoke fillmap); not AP fillmap paint.
RL.EnsureMapBounds()
Game.AddSF(2.0, "RL.EnsureMapBounds", "")
""".strip()
    part_map = part_map_head + "\n" + part_map_tail

    chunks = [part0, part1, part2, part3, part_map]

    # Per-scenario pickup → blackboard property assignments
    # Actor pickups use actor_name; boss/EMMI use callback_function (Randovania).
    by_scenario: Dict[str, List[Tuple[str, int]]] = {}
    for index_str, data in actors.items():
        scenario = data["scenario"]
        actor = data["actor"]
        pickup_index = int(index_str)
        by_scenario.setdefault(scenario, []).append((actor, pickup_index + 1))

    for index_str, data in specials.items():
        scenario = data["scenario"]
        key = data["callback_function"]
        pickup_index = int(index_str)
        by_scenario.setdefault(scenario, []).append((key, pickup_index + 1))

    for scenario, pairs in by_scenario.items():
        entries = ",".join(f"{name}={lua_index}" for name, lua_index in pairs)
        loc_prefix = f"{scenario}_"
        code = (
            f'for n,i in pairs{{{entries}}} do '
            f'RL.Pickups[i]=RandomizerPowerup.PropertyForLocation("{loc_prefix}"..n) end'
        )
        chunks.append(code)

    # Pack into buffer-sized send units (never emit a chunk larger than buffer_size).
    # Must not split on ';' inside strings/comments — that yields LUA_ERRSYNTAX (3).
    packed = pack_lua_chunks(chunks, buffer_size)
    for i, piece in enumerate(packed):
        if len(piece) > buffer_size:
            raise ValueError(f"bootstrap chunk {i} length {len(piece)} > buffer {buffer_size}")
        if not lua_chunk_has_balanced_quotes(piece):
            raise ValueError(f"bootstrap chunk {i} has unbalanced quotes (packing bug)")
    return packed


def format_receive_pickup_lua(
    message: str,
    parent: str,
    progression_lua: str,
    received_pickups: int,
    inventory_index: int,
) -> str:
    """
    Build RL.ReceivePickup(...) matching Randovania's DreadRemoteConnector.

    On grant, bootstrap RL.GivePendingPickup shows the message via
    Scenario.QueueAsyncPopup(msg, 7.0) then applies the item.
    """
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'RL.ReceivePickup("{safe_message}",{parent},{repr(progression_lua)},'
        f"{received_pickups},{inventory_index})"
    )


def should_skip_local_inworld_grant(
    item_player: int,
    item_location: int,
    slot: Optional[int],
    is_solo_world: bool,
    game_reported_locations: Optional[Set[int]] = None,
    locations_checked: Optional[Set[int]] = None,
) -> bool:
    """
    Direct-patch local Dread items already apply resources on pickup
    (see ap_to_patcher._pickup_resources_and_caption / is_foreign=False).
    Re-granting them via RL.ReceivePickup doubles progressive stages, or
    otherwise desyncs the in-game inventory index from the server's.

    Solo (exactly one real player in the room): every location the local
    player can ever check is their own, so any item the server echoes back
    for a location we found (item_player == slot) was, by construction,
    already granted in-game the instant it was collected — there is no
    "foreign" pickup in a solo room. Skip unconditionally in that case.

    Multiworld: skip when this client saw the location collected in-game
    (``game_reported_locations``) OR the AP server already has it checked
    (``locations_checked``). The latter covers reconnect catch-up after
    ``game_reported_locations`` is cleared on Dread reconnect — without it,
    stackable local tanks can be re-granted while waiting for bitfield sync.
    Items from other players' worlds use ``item_player != slot`` and must
    always grant.

    Start inventory / non-location items (location <= 0) and items found by
    other players always grant, in both solo and multiworld rooms.
    """
    if slot is None:
        return False
    if item_player != slot:
        return False
    if item_location <= 0:
        return False
    if is_solo_world:
        return True
    if game_reported_locations and item_location in game_reported_locations:
        return True
    if locations_checked and item_location in locations_checked:
        return True
    return False


def inventory_grant_would_be_noop(
    amounts: Optional[List[int]],
    resources: Optional[Union[List[dict], ResourceProgression]],
    inventory_ids: Optional[List[str]] = None,
) -> bool:
    """
    True when Lua ``HandlePickupResources`` would grant nothing for ``resources``.

    Multi-stage progressives must inspect every stage (not only stage 0): owning
    Wide/Varia/Charge must not block the next Progressive Beam/Suit/Charge tier.
    Single-stage stackables (tanks, Flash Shift chains, Speed Booster charges)
    always grant in Lua and must never be treated as already-owned duplicates.
    """
    if not amounts or not resources:
        return False
    stages = _normalize_progression(resources)
    if not stages:
        return False

    ids = inventory_ids if inventory_ids is not None else inventory_item_ids()
    id_to_idx = {iid: i for i, iid in enumerate(ids)}
    stackable = {
        "ITEM_WEAPON_MISSILE_MAX",
        "ITEM_WEAPON_POWER_BOMB_MAX",
        "ITEM_MAX_LIFE",
        "ITEM_LIFE_SHARDS",
        "ITEM_NONE",
        # Stacking upgrades (Lua alwaysGrant for single-stage).
        "ITEM_UPGRADE_FLASH_SHIFT_CHAIN",
        "ITEM_UPGRADE_SPEED_BOOST_CHARGE",
    }

    # Single-stage: skip only when every unique resource is already owned.
    # Any stackable in the stage means Lua would still apply quantity → grant.
    if len(stages) == 1:
        checked = 0
        for res in stages[0]:
            if not isinstance(res, dict):
                return False
            iid = str(res.get("item_id") or "")
            try:
                qty = int(res.get("quantity") or 0)
            except Exception:
                qty = 0
            if not iid or qty <= 0:
                continue
            if iid in stackable:
                return False
            idx = id_to_idx.get(iid)
            if idx is None or idx >= len(amounts):
                return False
            if int(amounts[idx] or 0) < qty:
                return False
            checked += 1
        return checked > 0

    # Multi-stage: Lua grants the first stage whose gate item is missing.
    # Only a full clear of every stage is a true no-op / reconnect duplicate.
    saw_stage = False
    for stage in stages:
        if not stage:
            continue
        first = stage[0]
        if not isinstance(first, dict):
            return False
        iid = str(first.get("item_id") or "")
        try:
            qty = int(first.get("quantity") or 0)
        except Exception:
            qty = 0
        if not iid or qty <= 0:
            continue
        if iid in stackable:
            return False
        idx = id_to_idx.get(iid)
        if idx is None or idx >= len(amounts):
            return False
        if int(amounts[idx] or 0) < qty:
            return False
        saw_stage = True
    return saw_stage


def format_skip_local_pickup_lua(received_pickups: int) -> str:
    """
    Advance ReceivedPickups without granting or showing a popup.

    Keeps AP index sync when an in-world local pickup already applied the item.
    Clears PendingPickup so a mid-popup remote grant cannot block index catch-up
    (previously the skip no-op'd while PendingPickup was set, stalling reconnect).
    """
    return (
        "do "
        f"local idx = {int(received_pickups)}; "
        "if RL.ReceivedPickups and idx == RL.ReceivedPickups() then "
        "RL.PendingPickup = nil; "
        'Scenario.WriteToPlayerBlackboard("ReceivedPickups","f",idx + 1); '
        "if RL.SendReceivedPickups then RL.SendReceivedPickups(tostring(idx + 1)) end; "
        "elseif RL.GetReceivedPickupsAndSend then "
        'Game.AddSF(0, "RL.GetReceivedPickupsAndSend", "b", false); '
        "end; "
        "end"
    )


def format_deathlink_kill_lua(source: str = "DeathLink") -> str:
    """
    Force a player death the same way ODR updates energy in randomizer_powerup.lua:
    Game.SetItemAmount + live LIFE.fCurrentLife (Blackboard alone does NOT kill).

    Sets DeathFromRemote/DeathSent so OnPlayerDead does not emit AP_DEATH (no echo).
    """
    safe = source.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return f"""
do
  local ok, err = pcall(function()
    if RL ~= nil then
      RL.DeathFromRemote = true
      RL.DeathSent = true
      RL.WasAlive = false
      RL.DeathPending = false
    end
    Game.SetItemAmount(Game.GetPlayerName(), "ITEM_CURRENT_LIFE", 0)
    local player = Game.GetPlayer()
    if player ~= nil and player.LIFE ~= nil then
      player.LIFE.fCurrentLife = 0
    end
    local section = Game.GetPlayerBlackboardSectionName()
    if section ~= nil then
      Blackboard.SetProp(section, "ITEM_CURRENT_LIFE", "f", 0.0)
    end
    Blackboard.SetProp("PLAYER_INVENTORY", "ITEM_CURRENT_LIFE", "f", 0.0)
    Scenario.QueueAsyncPopup("DeathLink from {safe}", 3.0)
  end)
  if not ok then
    Game.LogWarn(0, "AP DeathLink kill failed: " .. tostring(err))
  end
end
""".strip()

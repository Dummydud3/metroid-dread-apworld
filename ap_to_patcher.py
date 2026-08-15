#!/usr/bin/env python3
"""
Direct Archipelago → Dread Patcher Converter

Converts Archipelago spoiler logs directly to open-dread-rando patcher.json format,
bypassing Randovania's validation entirely.

This allows foreign item names (e.g., "Monomon" from Hollow Knight) to appear in-game!
"""

import copy
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent
# Prefer dread_paths so AP root (Options/CommonClient) wins over this world dir's Options.py.
# Runtime extracts at custom_worlds/_metroid_dread_runtime must not shadow via parents[1].
try:
    import dread_paths

    dread_paths.ensure_import_paths()
    _AP_ROOT = dread_paths.AP_ROOT
except Exception:
    # Minimal fallback when dread_paths is unavailable (keep AP ahead of world).
    import os

    _AP_ROOT = _ROOT.parents[1] if len(_ROOT.parents) >= 2 else _ROOT
    for key in ("DREAD_HUB_AP_ROOT", "ARCHIPELAGO_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if (candidate / "Options.py").is_file() and (candidate / "CommonClient.py").is_file():
                _AP_ROOT = candidate.resolve()
                break
    for _p in (_ROOT, _AP_ROOT):
        _s = str(_p)
        if _s in sys.path:
            sys.path.remove(_s)
        sys.path.insert(0, _s)

# Load pickup actor mapping (always from this script's directory)
with open(_ROOT / "dread_pickup_actors.json", encoding="utf-8") as _f:
    PICKUP_ACTORS = json.load(_f)

# Boss / EMMI death rewards — not world actors; ODR patches via lua callbacks
with open(_ROOT / "dread_special_pickups.json", encoding="utf-8") as _f:
    SPECIAL_PICKUPS = json.load(_f)

# Load Dread item mappings
from dread_item_mapping import get_dread_item_data, normalize_resource_progression, DEFAULT_STARTING_LOCATION, DEFAULT_STARTING_ITEMS

# Minimap sprite-atlas cell each placement reveals to (collect / AP hint).
from dread_map_icon_labels import sprite_for_item

# Multiworld: "Region - Area - Node (Player): Item (Player)"
LOCATION_RE = re.compile(
    r"^(?P<region>.+?) - (?P<area>.+?) - (?P<node>.+) \((?P<location_player>[^)]+)\): (?P<item>.+) \((?P<item_player>[^)]+)\)$"
)
# Solo / single-game: "Region - Area - Node: Item" (no player suffixes)
SOLO_LOCATION_RE = re.compile(
    r"^(?P<region>.+?) - (?P<area>.+?) - (?P<node>.+): (?P<item>.+)$"
)
PLAYER_HEADER_RE = re.compile(r"^Player \d+:\s*(.+)$")
SOLO_SLOT_NAME = "__solo_dread__"
# Spoiler header from MetroidDreadWorld.write_spoiler_header
STARTING_LOCATION_RE = re.compile(
    r"^Starting Location \((?P<player>[^)]+)\):\s*(?P<path>.+)$"
)
DREAD_PATCH_EXTRAS_PREFIX = "DREAD_PATCH_EXTRAS_JSON:"
DREAD_DNA_LOCS_PREFIX = "DREAD_DNA_LOCATIONS:"

# Load AP → Randovania location mapping.
# Under frozen installs, dread_paths registers WORLD_DIR as worlds.metroid_dread.
from worlds.metroid_dread.rdvgame_export import AP_TO_RANDOVANIA_LOCATION_MAP
from worlds.metroid_dread.starting_locations import (
    DEFAULT_PATCHER_REF,
    get_by_path,
    patcher_ref_for_node,
)


def _iter_spoiler_header_lines(spoiler_path: Path):
    """Yield non-empty header lines before the Locations: section."""
    with open(spoiler_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line == "Locations:":
                break
            yield line


def _spoiler_header_player_names(spoiler_path: Path) -> List[str]:
    """Player names from MetroidDreadWorld.write_spoiler_header machine lines."""
    seen: set[str] = set()
    names: List[str] = []
    for line in _iter_spoiler_header_lines(spoiler_path):
        player: Optional[str] = None
        match = STARTING_LOCATION_RE.match(line)
        if match:
            player = match.group("player").strip()
        elif line.startswith(DREAD_PATCH_EXTRAS_PREFIX):
            player = line[len(DREAD_PATCH_EXTRAS_PREFIX) :].split(":", 1)[0].strip()
        elif line.startswith(DREAD_DNA_LOCS_PREFIX):
            player = line[len(DREAD_DNA_LOCS_PREFIX) :].split(":", 1)[0].strip()
        if player and player not in seen:
            seen.add(player)
            names.append(player)
    return names


def _path_to_patcher_ref(path: str, player: str) -> Dict[str, str]:
    info = get_by_path(path)
    if info is not None:
        ref = info.patcher_ref
        print(f"[OK] Starting location for {player}: {path} -> {ref}")
        return ref
    parts = path.split("/")
    if len(parts) == 3:
        try:
            ref = patcher_ref_for_node((parts[0], parts[1], parts[2]))
            print(f"[OK] Starting location for {player}: {path} -> {ref}")
            return ref
        except KeyError:
            pass
    print(f"[WARNING] Unknown starting location path {path!r}; using default")
    return dict(DEFAULT_PATCHER_REF)


def is_solo_dread_spoiler(spoiler_path: Path) -> bool:
    """True when spoiler is a single-game Metroid Dread seed (no Player N: blocks)."""
    saw_player_header = False
    saw_solo_game = False
    with open(spoiler_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line == "Locations:":
                break
            if PLAYER_HEADER_RE.match(line):
                saw_player_header = True
                break
            if line.startswith("Game:") and line.split(":", 1)[1].strip() == "Metroid Dread":
                saw_solo_game = True
    return saw_solo_game and not saw_player_header


def detect_dread_players(spoiler_path: Path) -> List[str]:
    """Return player names whose game is Metroid Dread (spoiler header)."""
    if is_solo_dread_spoiler(spoiler_path):
        header_names = _spoiler_header_player_names(spoiler_path)
        if header_names:
            return header_names
        # Solo spoilers omit Player N: blocks; sentinel when header has no names.
        return [SOLO_SLOT_NAME]

    players: List[str] = []
    current: Optional[str] = None
    with open(spoiler_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line == "Locations:":
                break
            m = PLAYER_HEADER_RE.match(line)
            if m:
                current = m.group(1).strip()
                continue
            if current is not None and line.startswith("Game:"):
                game = line.split(":", 1)[1].strip()
                if game == "Metroid Dread":
                    players.append(current)
                current = None
    return players


def resolve_dread_player(spoiler_path: Path, requested: str) -> str:
    """
    Use requested name if it has placements; otherwise auto-pick the sole
    Metroid Dread player from the spoiler header.
    """
    if is_solo_dread_spoiler(spoiler_path):
        header_names = _spoiler_header_player_names(spoiler_path)
        if header_names:
            actual = header_names[0]
            if requested and requested != actual:
                print(
                    f"[INFO] Solo Metroid Dread spoiler — player in header is "
                    f"{actual!r} (requested {requested!r})"
                )
            return actual
        name = (requested or "DreadPlayer").strip() or "DreadPlayer"
        print(f"[INFO] Solo Metroid Dread spoiler — using player label {name!r}")
        return name

    dread_players = detect_dread_players(spoiler_path)
    if requested and parse_spoiler(spoiler_path, requested):
        return requested
    if len(dread_players) == 1:
        only = dread_players[0]
        if requested and requested != only:
            print(
                f"[WARN] No placements for player '{requested}'. "
                f"Auto-using Metroid Dread player '{only}' from spoiler."
            )
        return only
    if requested in dread_players:
        return requested
    if dread_players:
        listed = ", ".join(repr(p) for p in dread_players)
        raise ValueError(
            f"No item placements for player {requested!r}.\n"
            f"Metroid Dread player(s) in this spoiler: {listed}\n"
            f"Pass --player with the exact name from your YAML."
        )
    raise ValueError(
        f"No Metroid Dread player found in spoiler, and no placements for {requested!r}."
    )


def parse_starting_location(spoiler_path: Path, our_player_name: str) -> Dict[str, str]:
    """
    Read Starting Location (Player): Region/Area/Node from spoiler header.
    Falls back to Artaria Intro StartPoint0 when missing.
    """
    entries: List[Tuple[str, str]] = []
    for line in _iter_spoiler_header_lines(spoiler_path):
        match = STARTING_LOCATION_RE.match(line)
        if match:
            entries.append((match.group("player").strip(), match.group("path").strip()))

    for player, path in entries:
        if player == our_player_name or our_player_name == SOLO_SLOT_NAME:
            return _path_to_patcher_ref(path, player)

    if len(entries) == 1:
        player, path = entries[0]
        if player != our_player_name:
            print(
                f"[INFO] Using sole starting location for {player!r} "
                f"(requested {our_player_name!r})"
            )
        return _path_to_patcher_ref(path, player)

    print(f"[INFO] No starting location in spoiler for {our_player_name}; using default Intro")
    return dict(DEFAULT_PATCHER_REF)


def parse_spoiler(spoiler_path: Path, our_player_name: str) -> List[Tuple]:
    """Parse Archipelago spoiler log (multiworld or solo Dread)."""
    placements = []
    solo = is_solo_dread_spoiler(spoiler_path)
    in_locations = False

    with open(spoiler_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line == "Locations:":
                in_locations = True
                continue
            if not in_locations:
                continue
            if line.startswith("Archipelago") or line.startswith("=") or line.startswith("Player "):
                continue

            match = LOCATION_RE.match(line)
            if match:
                region = match.group("region")
                area = match.group("area")
                node = match.group("node")
                location_player = match.group("location_player")
                item = match.group("item")
                item_player = match.group("item_player")
                if location_player == our_player_name:
                    is_ours = item_player == our_player_name
                    placements.append((region, area, node, item, item_player, is_ours))
                continue

            if solo:
                solo_match = SOLO_LOCATION_RE.match(line)
                if solo_match:
                    region = solo_match.group("region")
                    area = solo_match.group("area")
                    node = solo_match.group("node")
                    item = solo_match.group("item").strip()
                    placements.append((region, area, node, item, our_player_name, True))

    return placements

# open-dread-rando schema enum for resources.item_id (v2.19)
VALID_ITEM_IDS = {
    "ITEM_NONE",
    "ITEM_WEAPON_WIDE_BEAM",
    "ITEM_WEAPON_PLASMA_BEAM",
    "ITEM_WEAPON_WAVE_BEAM",
    "ITEM_WEAPON_HYPER_BEAM",
    "ITEM_WEAPON_CHARGE_BEAM",
    "ITEM_WEAPON_DIFFUSION_BEAM",
    "ITEM_WEAPON_GRAPPLE_BEAM",
    "ITEM_WEAPON_SUPER_MISSILE",
    "ITEM_WEAPON_ICE_MISSILE",
    "ITEM_MULTILOCKON",
    "ITEM_OPTIC_CAMOUFLAGE",
    "ITEM_GHOST_AURA",
    "ITEM_SONAR",
    "ITEM_VARIA_SUIT",
    "ITEM_GRAVITY_SUIT",
    "ITEM_HYPER_SUIT",
    "ITEM_MORPH_BALL",
    "ITEM_WEAPON_BOMB",
    "ITEM_WEAPON_LINE_BOMB",
    "ITEM_WEAPON_POWER_BOMB",
    "ITEM_MAGNET_GLOVE",
    "ITEM_SPEED_BOOSTER",
    "ITEM_DOUBLE_JUMP",
    "ITEM_SPACE_JUMP",
    "ITEM_SCREW_ATTACK",
    "ITEM_ENERGY_TANKS",
    "ITEM_LIFE_SHARDS",
    "ITEM_MAX_LIFE",
    "ITEM_CURRENT_LIFE",
    "ITEM_WEAPON_MISSILE_CURRENT",
    "ITEM_WEAPON_MISSILE_MAX",
    "ITEM_WEAPON_POWER_BOMB_CURRENT",
    "ITEM_WEAPON_POWER_BOMB_MAX",
    "ITEM_FLOOR_SLIDE",
    "ITEM_METROIDNIZATION",
    "ITEM_RANDO_ARTIFACT_1",
    "ITEM_RANDO_ARTIFACT_2",
    "ITEM_RANDO_ARTIFACT_3",
    "ITEM_RANDO_ARTIFACT_4",
    "ITEM_RANDO_ARTIFACT_5",
    "ITEM_RANDO_ARTIFACT_6",
    "ITEM_RANDO_ARTIFACT_7",
    "ITEM_RANDO_ARTIFACT_8",
    "ITEM_RANDO_ARTIFACT_9",
    "ITEM_RANDO_ARTIFACT_10",
    "ITEM_RANDO_ARTIFACT_11",
    "ITEM_RANDO_ARTIFACT_12",
    "ITEM_UPGRADE_FLASH_SHIFT_CHAIN",
    "ITEM_UPGRADE_SPEED_BOOST_CHARGE",
}

# Legacy / mistaken IDs → schema-valid IDs
ITEM_ID_ALIASES = {
    "ITEM_SONAR_SIGHT": "ITEM_SONAR",
    "ITEM_SPECIAL_SLIDE": "ITEM_FLOOR_SLIDE",
    "ITEM_WEAPON_MISSILE_LAUNCHER": "ITEM_WEAPON_MISSILE_MAX",
    "ITEM_SPEED_BOOSTER_UPGRADE": "ITEM_UPGRADE_SPEED_BOOST_CHARGE",
}


def _sanitize_item_id(item_id: str) -> str:
    item_id = ITEM_ID_ALIASES.get(item_id, item_id)
    if item_id not in VALID_ITEM_IDS:
        print(f"[WARNING] Invalid item_id {item_id!r} -> ITEM_NONE")
        return "ITEM_NONE"
    return item_id


def _sanitize_resources(resources_groups):
    """Ensure every item_id is valid for open-dread-rando."""
    out = []
    for group in resources_groups:
        new_group = []
        for entry in group:
            eid = _sanitize_item_id(entry.get("item_id", "ITEM_NONE"))
            qty = entry.get("quantity", 0)
            # Missile launcher alias: capacity grant needs a meaningful quantity
            if (
                entry.get("item_id") == "ITEM_WEAPON_MISSILE_LAUNCHER"
                and eid == "ITEM_WEAPON_MISSILE_MAX"
                and qty == 1
            ):
                qty = 15
            new_group.append({"item_id": eid, "quantity": qty})
        out.append(new_group)
    return out


def _display_item_name(item_name: str) -> str:
    return item_name.replace("_", " ")


def _format_pickup_caption(item_name: str, player_name: str = None) -> str:
    """In-game pickup notification shown when collecting a world location."""
    display = _display_item_name(item_name)
    if player_name:
        return f"You just grabbed {player_name}'s {display}!"
    return f"You just grabbed {display}!"


def _map_icon_item_label(
    item_name: str,
    is_foreign: bool,
    player_name: str = None,
) -> str:
    """Short minimap reveal name (no 'You just grabbed')."""
    display = _display_item_name(item_name)
    if is_foreign and player_name:
        return f"{player_name}'s {display}"
    return display


def _pickup_resources_and_caption(
    item_name: str,
    is_foreign: bool,
    player_name: str = None,
    dna_artifact_index: Optional[int] = None,
    flash_shift_plan: Optional[dict] = None,
    yield_plan: Optional[dict] = None,
) -> Tuple[list, str, Optional[dict]]:
    """Return (resources, caption, dread_item_data_or_None)."""
    caption = _format_pickup_caption(item_name, player_name)
    if is_foreign:
        return [[{"item_id": "ITEM_NONE", "quantity": 0}]], caption, None

    if item_name == "Metroid DNA":
        if dna_artifact_index is not None and 1 <= int(dna_artifact_index) <= 12:
            artifact_id = f"ITEM_RANDO_ARTIFACT_{int(dna_artifact_index)}"
            return [[{"item_id": artifact_id, "quantity": 1}]], caption, None
        print(f"[WARNING] Metroid DNA pickup without artifact index — using ITEM_NONE")
        return [[{"item_id": "ITEM_NONE", "quantity": 0}]], caption, None

    item_data = get_dread_item_data(item_name)
    if item_data:
        try:
            from dread_item_mapping import apply_yield_overrides

            if yield_plan:
                item_data = apply_yield_overrides(item_name, item_data, yield_plan)
        except Exception as exc:
            print(f"[WARN] yield override failed for {item_name}: {exc}")
        # Prefer yield-adjusted caption for local tanks / energy when not foreign-named.
        if item_name in (
            "Missile Tank",
            "Missile+ Tank",
            "Power Bomb Tank",
            "Energy Tank",
            "Energy Part",
        ):
            caption = item_data.get("caption") or caption
        resources = _sanitize_resources(normalize_resource_progression(item_data["resources"]))
        if flash_shift_plan and item_name in ("Flash Shift", "Flash Shift Upgrade"):
            try:
                from flash_shift import main_resources, upgrade_resources

                if item_name == "Flash Shift":
                    resources = _sanitize_resources(
                        normalize_resource_progression(
                            main_resources(int(flash_shift_plan.get("included_ammo", 2) or 2))
                        )
                    )
                else:
                    resources = _sanitize_resources(
                        normalize_resource_progression(
                            upgrade_resources(int(flash_shift_plan.get("upgrade_amount", 1) or 1))
                        )
                    )
            except Exception as exc:
                print(f"[WARN] Flash Shift resource adjust failed: {exc}")
        return resources, caption, item_data

    print(f"[WARNING] Unknown Dread item: {item_name}, using generic")
    return [[{"item_id": "ITEM_NONE", "quantity": 0}]], caption, None


def create_special_pickup_entry(
    special: dict,
    item_name: str,
    is_foreign: bool,
    player_name: str = None,
    dna_artifact_index: Optional[int] = None,
    flash_shift_plan: Optional[dict] = None,
    yield_plan: Optional[dict] = None,
) -> dict:
    """
    Boss/EMMI death rewards for open-dread-rando.

    Same shapes as Randovania: cutscene/corpius/corex/emmi with pickup_lua_callback.
    Vanilla death grants are cleared and replaced by these resources.
    """
    resources, caption, _ = _pickup_resources_and_caption(
        item_name,
        is_foreign,
        player_name,
        dna_artifact_index=dna_artifact_index,
        flash_shift_plan=flash_shift_plan,
        yield_plan=yield_plan,
    )
    entry = {
        "pickup_type": special["pickup_type"],
        "caption": caption,
        "resources": resources,
        "pickup_lua_callback": {
            "scenario": special["scenario"],
            "function": special["callback_function"],
            "args": int(special.get("callback_args", 0)),
        },
    }
    if special["pickup_type"] != "cutscene":
        entry["pickup_actordef"] = special["actor_def"]
        entry["pickup_string_key"] = special["string_key"]
    return entry


def create_pickup_entry(
    pickup_index: int,
    item_name: str,
    is_foreign: bool,
    player_name: str = None,
    dna_artifact_index: Optional[int] = None,
    flash_shift_plan: Optional[dict] = None,
    yield_plan: Optional[dict] = None,
) -> dict:
    """Create a pickup entry for patcher.json."""

    special = SPECIAL_PICKUPS.get(str(pickup_index))
    if special:
        return create_special_pickup_entry(
            special,
            item_name,
            is_foreign,
            player_name,
            dna_artifact_index=dna_artifact_index,
            flash_shift_plan=flash_shift_plan,
            yield_plan=yield_plan,
        )

    actor_data = PICKUP_ACTORS.get(str(pickup_index))
    if not actor_data:
        print(f"[WARNING] No actor/special data for pickup index {pickup_index}")
        return None

    pickup_actor = {
        "scenario": actor_data["scenario"],
        "actor": actor_data["actor"]
    }

    # Minimap icon actor may differ from the world pickup actor. The 12 major-item
    # spheres (ItemSphere_ChargeBeam, IT_VARIA_GEN_001, …) live under powerup_*
    # names in the scenario .bmmap `items` category — same map_icon_actor extras
    # Randovania uses. Without this, ODR never replaces the vanilla major icons
    # (world-map visible + full-zoom pulse).
    map_actor_name = actor_data.get("map_icon_actor") or actor_data["actor"]
    original_actor = {
        "scenario": actor_data["scenario"],
        "actor": map_actor_name,
    }

    resources, caption, item_data = _pickup_resources_and_caption(
        item_name,
        is_foreign,
        player_name,
        dna_artifact_index=dna_artifact_index,
        flash_shift_plan=flash_shift_plan,
        yield_plan=yield_plan,
    )

    # Spoiler-hide: unique ItemCustom{n} per location, ? sprite, "Unknown Item".
    # Use coords + is_global/full_zoom_scale instead of base_icon="unknown":
    # MapIconEditor.copy-from-base keeps unknown's True flags (world map + pulse).
    # Tanks use False/False; majors use True/True — we want tank-like AP unknowns.
    # ODR MapIconEditor numbers custom_icon entries in pickups-array order when
    # original_actor is in that scenario's vanilla items list (Phase 2 sidecar).
    map_icon = {
        "custom_icon": {
            "label": "Unknown Item",
            "coords": {"row": 7, "col": 15},  # ODR "unknown" atlas cell
            "is_global": False,
            "full_zoom_scale": False,
        },
        "original_actor": original_actor,
    }

    if is_foreign:
        # Foreign AP item — grant nothing in-game (AP client delivers)
        return {
            "pickup_type": "actor",
            "caption": caption,
            "resources": resources,
            "pickup_actor": pickup_actor,
            "model": ["itemsphere"],
            "map_icon": map_icon,
        }

    if item_data:
        return {
            "pickup_type": "actor",
            "caption": caption,
            "resources": resources,
            "pickup_actor": pickup_actor,
            "model": [item_data["model"]],
            "map_icon": map_icon,
        }

    return {
        "pickup_type": "actor",
        "caption": caption,
        "resources": resources,
        "pickup_actor": pickup_actor,
        "model": ["itemsphere"],
        "map_icon": map_icon,
    }

def enable_death_counter(patcher_data: dict) -> None:
    """Turn on ODR's in-game HUD death counter (cosmetic_patches.lua.custom_init)."""
    cosmetic = patcher_data.setdefault("cosmetic_patches", {})
    if not isinstance(cosmetic, dict):
        cosmetic = {}
        patcher_data["cosmetic_patches"] = cosmetic
    lua = cosmetic.setdefault("lua", {})
    if not isinstance(lua, dict):
        lua = {}
        cosmetic["lua"] = lua
    custom_init = lua.setdefault("custom_init", {})
    if not isinstance(custom_init, dict):
        custom_init = {}
        lua["custom_init"] = custom_init
    custom_init["enable_death_counter"] = True


COSMETIC_COMBAT_PATHS: dict[str, tuple[str, ...]] = {
    "bShowBossLifebar": ("cosmetic_patches", "config", "AIManager", "bShowBossLifebar"),
    "bShowEnemyLife": ("cosmetic_patches", "config", "AIManager", "bShowEnemyLife"),
    "bShowEnemyDamage": ("cosmetic_patches", "config", "AIManager", "bShowEnemyDamage"),
    "bShowPlayerDamage": ("cosmetic_patches", "config", "AIManager", "bShowPlayerDamage"),
    "enable_death_counter": ("cosmetic_patches", "lua", "custom_init", "enable_death_counter"),
    # ODR ≥2.19 only — gated at emit/sanitize time against installed schema.
    "show_dna_in_hud": ("cosmetic_patches", "lua", "custom_init", "show_dna_in_hud"),
    "enable_room_name_display": ("cosmetic_patches", "lua", "custom_init", "enable_room_name_display"),
    "raven_beak_damage_table_handling": ("game_patches", "raven_beak_damage_table_handling"),
    "nerf_power_bombs": ("game_patches", "nerf_power_bombs"),
    "default_x_released": ("game_patches", "default_x_released"),
    "energy_per_tank": ("energy_per_tank",),
    # Top-level ODR keys (not under cosmetic_patches) — same as RDV Energy tab.
    "immediate_energy_parts": ("immediate_energy_parts",),
}


def _normalize_constant_environment_damage(raw) -> dict:
    """ODR expects heat/cold/lava keys; null = vanilla scaling, number = constant DPS."""
    if not isinstance(raw, dict):
        raw = {}
    out = {}
    for key in ("heat", "cold", "lava"):
        val = raw.get(key, None)
        if val is None:
            out[key] = None
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            out[key] = None
            continue
        # YAML Range 0 means "off" (vanilla); positive = constant DPS.
        out[key] = None if num <= 0 else num
    return out

# Fields older ODR schemas reject via additionalProperties: false.
# show_dna_in_hud / has_*_upgrades / enable_logging / skip_item_popups: ODR ≥2.19.
# split_saves under cosmetic_patches: ODR ≥2.19.
_CUSTOM_INIT_OPTIONAL_KEYS = frozenset({"show_dna_in_hud"})
_ROOT_OPTIONAL_KEYS = frozenset({
    "has_flash_upgrades",
    "has_speed_upgrades",
    "enable_logging",
    "skip_item_popups",
})
_COSMETIC_OPTIONAL_KEYS = frozenset({"split_saves"})

# Cache probed ODR schemas per interpreter key (None = this process).
_ODR_SCHEMA_CACHE: dict[Optional[tuple], Optional[dict]] = {}


def _load_odr_schema(py_cmd: Optional[List[str]] = None) -> Optional[dict]:
    """Load open-dread-rando files/schema.json from *py_cmd* or this process."""
    cache_key: Optional[tuple]
    if py_cmd:
        cache_key = tuple(py_cmd)
    else:
        cache_key = None
    if cache_key in _ODR_SCHEMA_CACHE:
        return _ODR_SCHEMA_CACHE[cache_key]

    schema: Optional[dict] = None
    if py_cmd:
        import subprocess

        # Compact probe: only the property-name sets we sanitize against.
        probe = (
            "import json,os;"
            "import open_dread_rando;"
            "p=os.path.join(os.path.dirname(open_dread_rando.__file__),'files','schema.json');"
            "s=json.load(open(p,encoding='utf-8'));"
            "ci=s['properties']['cosmetic_patches']['properties']['lua']"
            "['properties']['custom_init']['properties'];"
            "cp=s['properties']['cosmetic_patches']['properties'];"
            "print(json.dumps({"
            "'root':sorted(s['properties']),"
            "'custom_init':sorted(ci),"
            "'cosmetic':sorted(cp)"
            "}))"
        )
        try:
            r = subprocess.run(
                list(py_cmd) + ["-c", probe],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if r.returncode == 0 and (r.stdout or "").strip():
                summary = json.loads(r.stdout.strip().splitlines()[-1])
                # Rebuild a minimal schema-shaped dict for the helpers below.
                schema = {
                    "properties": {
                        **{k: {} for k in summary.get("root", [])},
                        "cosmetic_patches": {
                            "properties": {
                                **{k: {} for k in summary.get("cosmetic", [])},
                                "lua": {
                                    "properties": {
                                        "custom_init": {
                                            "properties": {
                                                k: {}
                                                for k in summary.get("custom_init", [])
                                            }
                                        }
                                    }
                                },
                            }
                        },
                    }
                }
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, KeyError):
            schema = None
    else:
        try:
            import open_dread_rando

            schema_path = (
                Path(open_dread_rando.__file__).resolve().parent / "files" / "schema.json"
            )
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception:
            schema = None

    _ODR_SCHEMA_CACHE[cache_key] = schema
    return schema


def _load_odr_custom_init_properties(
    py_cmd: Optional[List[str]] = None,
) -> Optional[frozenset]:
    """Return allowed custom_init property names from an installed ODR schema."""
    schema = _load_odr_schema(py_cmd)
    if not schema:
        return None
    try:
        props = (
            schema["properties"]["cosmetic_patches"]["properties"]["lua"]["properties"][
                "custom_init"
            ]["properties"]
        )
        return frozenset(str(k) for k in props)
    except (KeyError, TypeError):
        return None


def _load_odr_root_properties(
    py_cmd: Optional[List[str]] = None,
) -> Optional[frozenset]:
    """Return allowed top-level patcher.json property names from ODR schema."""
    schema = _load_odr_schema(py_cmd)
    if not schema:
        return None
    try:
        return frozenset(str(k) for k in schema["properties"])
    except (KeyError, TypeError):
        return None


def _cosmetic_custom_init_field_supported(field: str) -> bool:
    """Whether *field* may be written under cosmetic_patches.lua.custom_init."""
    allowed = _load_odr_custom_init_properties()
    if allowed is not None:
        return field in allowed
    # Unknown ODR: omit keys that older schemas (≤2.18) reject.
    return field not in _CUSTOM_INIT_OPTIONAL_KEYS


def _root_field_supported(field: str, py_cmd: Optional[List[str]] = None) -> bool:
    """Whether *field* may be written at the patcher.json root for target ODR."""
    allowed = _load_odr_root_properties(py_cmd)
    if allowed is not None:
        return field in allowed
    return field not in _ROOT_OPTIONAL_KEYS


def sanitize_custom_init_for_odr(
    patcher_data: dict,
    *,
    py_cmd: Optional[List[str]] = None,
) -> list[str]:
    """Drop custom_init keys the target ODR schema does not allow.

    Returns the list of removed keys (empty if nothing changed).
    """
    try:
        custom_init = patcher_data["cosmetic_patches"]["lua"]["custom_init"]
    except (KeyError, TypeError):
        return []
    if not isinstance(custom_init, dict):
        return []

    allowed = _load_odr_custom_init_properties(py_cmd)
    removed: list[str] = []
    if allowed is None:
        # Conservative fallback when schema cannot be probed.
        drop = [k for k in list(custom_init) if k in _CUSTOM_INIT_OPTIONAL_KEYS]
    else:
        drop = [k for k in list(custom_init) if k not in allowed]

    for key in drop:
        custom_init.pop(key, None)
        removed.append(key)
    return removed


def sanitize_root_for_odr(
    patcher_data: dict,
    *,
    py_cmd: Optional[List[str]] = None,
) -> list[str]:
    """Drop root keys the target ODR schema rejects (additionalProperties: false).

    Same skew class as show_dna_in_hud: ODR ≤2.18 has no has_flash_upgrades /
    has_speed_upgrades / enable_logging / skip_item_popups.
    """
    if not isinstance(patcher_data, dict):
        return []
    allowed = _load_odr_root_properties(py_cmd)
    removed: list[str] = []
    if allowed is None:
        drop = [k for k in list(patcher_data) if k in _ROOT_OPTIONAL_KEYS]
    else:
        drop = [k for k in list(patcher_data) if k not in allowed]
    for key in drop:
        patcher_data.pop(key, None)
        removed.append(key)
    return removed


def sanitize_cosmetic_for_odr(
    patcher_data: dict,
    *,
    py_cmd: Optional[List[str]] = None,
) -> list[str]:
    """Drop cosmetic_patches keys unsupported by the target ODR schema."""
    try:
        cosmetic = patcher_data["cosmetic_patches"]
    except (KeyError, TypeError):
        return []
    if not isinstance(cosmetic, dict):
        return []

    schema = _load_odr_schema(py_cmd)
    removed: list[str] = []
    if schema is None:
        drop = [k for k in list(cosmetic) if k in _COSMETIC_OPTIONAL_KEYS]
    else:
        try:
            allowed = frozenset(
                schema["properties"]["cosmetic_patches"]["properties"]
            )
        except (KeyError, TypeError):
            drop = [k for k in list(cosmetic) if k in _COSMETIC_OPTIONAL_KEYS]
        else:
            # Only strip known optional keys when schema omits them — never
            # delete required keys (config/lua/shield_versions) if probe is odd.
            drop = [
                k
                for k in list(cosmetic)
                if k in _COSMETIC_OPTIONAL_KEYS and k not in allowed
            ]
    for key in drop:
        cosmetic.pop(key, None)
        removed.append(key)
    return removed


def sanitize_patcher_for_odr(
    patcher_data: dict,
    *,
    py_cmd: Optional[List[str]] = None,
) -> list[str]:
    """Strip all known ODR-version-skew fields the target schema rejects.

    Returns dotted paths of removed keys (e.g. ``show_dna_in_hud``,
    ``has_flash_upgrades``, ``cosmetic_patches.split_saves``).
    """
    removed: list[str] = []
    for key in sanitize_root_for_odr(patcher_data, py_cmd=py_cmd):
        removed.append(key)
    for key in sanitize_cosmetic_for_odr(patcher_data, py_cmd=py_cmd):
        removed.append(f"cosmetic_patches.{key}")
    for key in sanitize_custom_init_for_odr(patcher_data, py_cmd=py_cmd):
        removed.append(key)
    return removed


def _patcher_has_item(patcher_data: dict, item_id: str) -> bool:
    """True if starting_items or any pickup grants *item_id* with qty > 0."""
    start = patcher_data.get("starting_items") or {}
    if isinstance(start, dict) and int(start.get(item_id, 0) or 0) > 0:
        return True
    for pickup in patcher_data.get("pickups") or []:
        if not isinstance(pickup, dict):
            continue
        for stage in pickup.get("resources") or []:
            if not isinstance(stage, list):
                continue
            for entry in stage:
                if (
                    isinstance(entry, dict)
                    and entry.get("item_id") == item_id
                    and int(entry.get("quantity", 0) or 0) > 0
                ):
                    return True
    return False


def apply_upgrade_menu_flags(
    patcher_data: dict,
    *,
    py_cmd: Optional[List[str]] = None,
) -> None:
    """Set has_flash_upgrades / has_speed_upgrades when the ODR schema allows.

    Mirrors Randovania patch_data_factory: these flags control Samus-menu rows.
    Omitted on ODR ≤2.18 (root additionalProperties: false).
    """
    if _root_field_supported("has_flash_upgrades", py_cmd):
        patcher_data["has_flash_upgrades"] = _patcher_has_item(
            patcher_data, "ITEM_UPGRADE_FLASH_SHIFT_CHAIN"
        )
    else:
        patcher_data.pop("has_flash_upgrades", None)

    if _root_field_supported("has_speed_upgrades", py_cmd):
        patcher_data["has_speed_upgrades"] = _patcher_has_item(
            patcher_data, "ITEM_UPGRADE_SPEED_BOOST_CHARGE"
        )
    else:
        patcher_data.pop("has_speed_upgrades", None)

LIGHT_REGION_TO_SCENARIO: dict[str, str] = {
    "artaria": "s010_cave",
    "cataris": "s020_magma",
    "dairon": "s030_baselab",
    "burenia": "s040_aqua",
    "ghavoran": "s050_forest",
    "elun": "s060_quarantine",
    "ferenia": "s070_basesanc",
    "hanubia": "s080_shipyard",
    "itorash": "s090_skybase",
}

def _set_nested(root: dict, path: tuple[str, ...], value) -> None:
    cur = root
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


def parse_dread_patch_extras(spoiler_path: Path, player_name: str) -> dict:
    """Read machine-readable extras written by MetroidDreadWorld.write_spoiler*."""
    collected: List[Tuple[str, dict, list]] = []
    try:
        for line in _iter_spoiler_header_lines(spoiler_path):
            if line.startswith(DREAD_PATCH_EXTRAS_PREFIX):
                rest = line[len(DREAD_PATCH_EXTRAS_PREFIX) :]
                marker_player, _, payload = rest.partition(":")
                extras = json.loads(payload)
                if not isinstance(extras, dict):
                    extras = {}
                collected.append((marker_player.strip(), extras, []))
            elif line.startswith(DREAD_DNA_LOCS_PREFIX):
                rest = line[len(DREAD_DNA_LOCS_PREFIX) :]
                marker_player, _, payload = rest.partition(":")
                dna_locs = json.loads(payload)
                if not isinstance(dna_locs, list):
                    dna_locs = []
                for idx, (p, ex, dna) in enumerate(collected):
                    if p == marker_player.strip():
                        collected[idx] = (p, ex, dna_locs)
                        break
                else:
                    collected.append((marker_player.strip(), {}, dna_locs))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Could not parse Dread patch extras: {exc}")
        return {}

    for player, extras, dna_locs in collected:
        if player == player_name or player_name == SOLO_SLOT_NAME:
            if dna_locs:
                extras = dict(extras)
                extras["dna_locations"] = dna_locs
            return extras

    if len(collected) == 1:
        player, extras, dna_locs = collected[0]
        if player != player_name:
            print(
                f"[INFO] Using sole patch extras for {player!r} "
                f"(requested {player_name!r})"
            )
        if dna_locs:
            extras = dict(extras)
            extras["dna_locations"] = dna_locs
        return extras

    return {}


def _objective_hints_for(required_artifacts: int, game_goal: int = 0) -> list:
    n = int(required_artifacts)
    goal = int(game_goal)
    if goal == 1:
        if n <= 0:
            return ["Collect 100% of checks, then defeat Raven Beak."]
        return [
            f"Collect 100% of checks and {n} Metroid DNA, then defeat Raven Beak."
        ]
    if goal == 2:
        if n <= 0:
            return ["Defeat every boss, then defeat Raven Beak."]
        return [
            f"Defeat every boss, collect {n} Metroid DNA, then defeat Raven Beak."
        ]
    if n <= 0:
        return ["Return to your ship and escape ZDR."]
    return [f"Collect {n} Metroid DNA, then defeat Raven Beak."]


def _sanitize_connection_name(name: str) -> str:
    """Normalize transporter labels for ODR map-icon ids / BTXT keys."""
    cleaned = str(name or "").replace(".", "").strip()
    return cleaned or "Unknown"


def _harden_elevator_entry(entry: dict) -> dict:
    """Ensure elevator entries are safe for open-dread-rando + in-game use.

    - Require teleporter/destination scenario+actor (non-empty strings).
    - Ensure connection_name (ODR schema); strip '.' (E.M.M.I. → EMMI).
    - Reject destination.actor that looks like a missing/null placeholder.
    """
    entry = dict(entry)
    tele = dict(entry.get("teleporter") or {})
    dest = dict(entry.get("destination") or {})
    for blob, label in ((tele, "teleporter"), (dest, "destination")):
        scen = blob.get("scenario")
        actor = blob.get("actor")
        if not isinstance(scen, str) or not scen.strip():
            raise ValueError(f"elevator {label}.scenario missing/empty: {entry!r}")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError(f"elevator {label}.actor missing/empty: {entry!r}")
        blob["scenario"] = scen.strip()
        blob["actor"] = actor.strip()
    entry["teleporter"] = tele
    entry["destination"] = dest
    raw_name = entry.get("connection_name") or dest.get("scenario") or dest.get("actor") or "Unknown"
    entry["connection_name"] = _sanitize_connection_name(raw_name)
    return entry


def _apply_elevator_destination_room_names(patcher_data: dict, elevators: list) -> None:
    """Overlay transporter collision-cameras with shuffled destination labels.

    Matches Randovania: room-name HUD shows "Transport to {connection_name}" for
    elevator/shuttle rooms. Also forces room-name display on when elevators are
    shuffled and the cosmetic was NEVER (otherwise destination labels never appear).
    """
    if not elevators:
        return
    cosmetic = patcher_data.setdefault("cosmetic_patches", {})
    lua = cosmetic.setdefault("lua", {})
    custom_init = lua.setdefault("custom_init", {})
    if custom_init.get("enable_room_name_display") == "NEVER":
        custom_init["enable_room_name_display"] = "ALWAYS"
    camera_dict = lua.setdefault("camera_names_dict", {})
    applied = 0
    for entry in elevators:
        tele = entry.get("teleporter") or {}
        scenario = tele.get("scenario")
        camera = entry.get("source_camera")
        label = entry.get("connection_name")
        if not scenario or not camera or not label:
            continue
        camera_dict.setdefault(scenario, {})[camera] = f"Transport to {label}"
        applied += 1
    if applied:
        print(f"[OK] Applied {applied} transporter room-name overlays")


def _normalize_mass_delete_entry(entry: dict) -> dict:
    """Coerce a mass_delete_actors to_remove entry to open-dread-rando schema."""
    entry = dict(entry)
    method = entry.get("method", "all")
    if isinstance(method, list):
        method = method[0] if method else "all"
    elif not isinstance(method, str):
        method = str(method)
    entry["method"] = method
    if method in ("remove_from_groups", "keep_from_groups"):
        groups = entry.get("actor_groups")
        if isinstance(groups, str):
            entry["actor_groups"] = [groups]
        elif not isinstance(groups, list):
            entry["actor_groups"] = []
    return entry


def _mass_delete_to_remove_list(patcher_data: dict) -> list:
    """Return the to_remove list, accepting legacy flat-list mass_delete_actors."""
    mda = patcher_data.get("mass_delete_actors")
    if isinstance(mda, dict):
        to_remove = mda.get("to_remove")
        if isinstance(to_remove, list):
            return [_normalize_mass_delete_entry(e) for e in to_remove if isinstance(e, dict)]
        return []
    if isinstance(mda, list):
        return [_normalize_mass_delete_entry(e) for e in mda if isinstance(e, dict)]
    return []


def _set_mass_delete_to_remove(patcher_data: dict, to_remove: list) -> None:
    """Write to_remove under mass_delete_actors using the ODR object shape."""
    mda = patcher_data.get("mass_delete_actors")
    if isinstance(mda, dict):
        mda = dict(mda)
    else:
        mda = {}
    mda["to_remove"] = [_normalize_mass_delete_entry(e) for e in to_remove if isinstance(e, dict)]
    mda.setdefault("to_keep", [])
    patcher_data["mass_delete_actors"] = mda


def apply_dread_patch_extras(patcher_data: dict, extras: dict, *, our_player: str) -> None:
    """Merge door/elevator/DNA/cosmetic overrides from generation into patcher JSON."""
    if not extras:
        return

    door_patches = extras.get("door_patches") or []
    if door_patches:
        patcher_data["door_patches"] = door_patches
        print(f"[OK] Applied {len(door_patches)} door_patches from seed options")

    elevators = extras.get("elevators") or []
    if elevators:
        elevators = [_harden_elevator_entry(entry) for entry in elevators]
        patcher_data["elevators"] = elevators
        print(f"[OK] Applied {len(elevators)} elevators from seed options")

    cosmetic = extras.get("cosmetic_combat") or {}
    for field, path in COSMETIC_COMBAT_PATHS.items():
        if field not in cosmetic:
            continue
        # Skip custom_init keys the installed ODR schema rejects (e.g. show_dna_in_hud
        # on open-dread-rando ≤2.18 — additionalProperties: false).
        if (
            len(path) >= 4
            and path[:3] == ("cosmetic_patches", "lua", "custom_init")
            and not _cosmetic_custom_init_field_supported(field)
        ):
            print(
                f"[INFO] Omitting cosmetic_patches.lua.custom_init.{field} - "
                f"not in installed open-dread-rando schema "
                f"(upgrade to open-dread-rando>=2.19 for DNA HUD)"
            )
            continue
        _set_nested(patcher_data, path, cosmetic[field])

    # Constant environmental damage: top-level ODR object (heat/cold/lava).
    if "constant_environment_damage" in cosmetic:
        patcher_data["constant_environment_damage"] = _normalize_constant_environment_damage(
            cosmetic.get("constant_environment_damage")
        )

    # RDV: Energy Per Tank only applies with Immediate Energy Parts; otherwise
    # force 100 so part/tank Lua capacity stays vanilla.
    if "immediate_energy_parts" in cosmetic and not cosmetic.get("immediate_energy_parts"):
        patcher_data["energy_per_tank"] = 100.0

    # After cosmetic_combat (which may set enable_room_name_display), overlay
    # transporter destination names and optionally force display for elevator rando.
    if elevators:
        _apply_elevator_destination_room_names(patcher_data, elevators)

    lights = extras.get("disabled_lights") or []
    if lights:
        deletes = _mass_delete_to_remove_list(patcher_data)
        for region_key in lights:
            scenario = LIGHT_REGION_TO_SCENARIO.get(str(region_key).lower())
            if not scenario:
                continue
            entry = {
                "scenario": scenario,
                "actor_layer": "rLightsLayer",
                "method": "all",
            }
            if entry not in deletes:
                deletes.append(entry)
        _set_mass_delete_to_remove(patcher_data, deletes)
        print(f"[OK] Applied {len(lights)} disabled_lights region(s) to mass_delete_actors")

    required = extras.get("required_artifacts")
    if required is not None:
        obj = patcher_data.setdefault("objective", {})
        if not isinstance(obj, dict):
            obj = {}
            patcher_data["objective"] = obj
        obj["required_artifacts"] = int(required)
        # Prefer real required_dna for ADAM text (All Bosses may force artifacts≥1
        # for the Itorash door while DNA is still 0).
        hint_dna = extras.get("required_dna")
        if hint_dna is None:
            hint_dna = required
        obj["hints"] = _objective_hints_for(
            int(hint_dna), int(extras.get("game_goal", 0) or 0)
        )
        # Pre-grant artifacts beyond required so the in-game gate matches N.
        start = patcher_data.setdefault("starting_items", {})
        if not isinstance(start, dict):
            start = {}
            patcher_data["starting_items"] = start
        for i in range(int(required) + 1, 13):
            start[f"ITEM_RANDO_ARTIFACT_{i}"] = 1
        print(f"[OK] objective.required_artifacts={required}")

    start = patcher_data.setdefault("starting_items", {})
    if not isinstance(start, dict):
        start = {}
        patcher_data["starting_items"] = start
    if "starting_missiles" in extras:
        start["ITEM_WEAPON_MISSILE_MAX"] = int(extras["starting_missiles"])
    if "starting_power_bombs" in extras and int(extras["starting_power_bombs"]) > 0:
        start["ITEM_WEAPON_POWER_BOMB_MAX"] = int(extras["starting_power_bombs"])
    if extras.get("start_with_pulse_radar"):
        start["ITEM_SONAR"] = 1  # Pulse Radar
    # Items granted so a cramped random starting location has checks in logic.
    for item_id, qty in (extras.get("starting_items") or {}).items():
        start[item_id] = max(int(start.get(item_id, 0) or 0), int(qty))

    # Prefer DNA location hints on Adam terminals when requested.
    if extras.get("hint_all_dna") and extras.get("dna_locations"):
        from dread_adam_hints import ADAM_HINT_TERMINALS, format_region_hint, JOKE_HINTS

        dna_locs = list(extras["dna_locations"])
        hints = []
        for i, terminal in enumerate(ADAM_HINT_TERMINALS):
            if i < len(dna_locs):
                loc = dna_locs[i]
                # "Region - Area - Node" → hint region
                region = loc.split(" - ", 1)[0] if " - " in loc else loc
                text = format_region_hint("Metroid DNA", region)
            else:
                text = JOKE_HINTS[i % len(JOKE_HINTS)]
            hints.append({
                "accesspoint_actor": dict(terminal["accesspoint_actor"]),
                "hint_id": terminal["hint_id"],
                "text": text,
            })
        patcher_data["hints"] = hints
        print(f"[OK] hint_all_dna: {min(len(dna_locs), len(ADAM_HINT_TERMINALS))} DNA Adam hints")


# Sample/template placeholders — never treat these as a real seed identity.
_PLACEHOLDER_LAYOUT_UUIDS = frozenset({
    "00000000-0000-1111-0000-000000000000",
})
# Stable namespace so the same AP room + player always yields the same layout UUID.
_AP_DREAD_LAYOUT_NAMESPACE = uuid.UUID("b3c8f0a1-5e2d-4a7b-9c6e-1f8d4a2b0e73")
_AP_ROOM_RE = re.compile(r"AP_(\d{10,})")
_SEED_LINE_RE = re.compile(r"\bSeed:\s*(\d+)\b")


def spoiler_seed_key(spoiler_path: Path) -> str:
    """Stable seed identity from AP room id / spoiler Seed line / path."""
    for part in (spoiler_path.name, spoiler_path.stem, spoiler_path.parent.name):
        match = _AP_ROOM_RE.search(part)
        if match:
            return f"AP_{match.group(1)}"
    try:
        with open(spoiler_path, encoding="utf-8", errors="replace") as f:
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                match = _SEED_LINE_RE.search(line)
                if match:
                    return f"SEED_{match.group(1)}"
    except OSError:
        pass
    return spoiler_path.resolve().as_posix()


# Title-screen branding (BTXT GUI_COMPANY_TITLE_SCREEN). ODR uses `|` inside the
# second line for its own separator; we use `\n` between the two visual lines.
DEFAULT_ODR_VERSION = "2.18.0"
_STALE_RDV_SEED_MARKERS = ("Slaaga Spittail Robe", "57GXBFRH")
_DIFSELECTOR_LABEL_KEYS = (
    "GUI_DIFSELECTOR_LABEL_DESCRIPTOR_EASY",
    "GUI_DIFSELECTOR_LABEL_DESCRIPTOR_NORMAL",
    "GUI_DIFSELECTOR_LABEL_DESCRIPTOR_HARD_UNLOCKED",
    "GUI_DIFSELECTOR_LABEL_DESCRIPTOR_EXPERT",
)


def ap_world_version() -> str:
    """AP world / apworld build version from archipelago.json."""
    path = _ROOT / "archipelago.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("world_version") if isinstance(data, dict) else None
        if isinstance(version, str) and version.strip():
            return version.strip()
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return "0.0.0"


def open_dread_rando_version() -> str:
    """Installed ODR version when importable; else the pinned fallback."""
    try:
        from open_dread_rando.version import version as odr_version

        text = str(odr_version).strip()
        if text:
            return text
    except Exception:
        pass
    return DEFAULT_ODR_VERSION


def format_display_seed_id(seed_key: str) -> str:
    """Turn spoiler_seed_key / raw seed into a short title-screen id."""
    key = (seed_key or "").strip()
    if not key or any(m in key for m in _STALE_RDV_SEED_MARKERS):
        return ""
    match = re.fullmatch(r"(?:SEED_|AP_)?(\d{10,})", key)
    if match:
        return match.group(1)
    if key.startswith("SEED_"):
        return key[5:]
    if key.startswith("AP_"):
        return key
    # Path fallbacks are not useful on the title screen.
    if "/" in key or "\\" in key or len(key) > 48:
        return ""
    return key


def layout_uuid_short(layout_uuid: Optional[str]) -> str:
    if not isinstance(layout_uuid, str):
        return ""
    value = layout_uuid.strip()
    if not value or value in _PLACEHOLDER_LAYOUT_UUIDS:
        return ""
    compact = value.replace("-", "")
    return compact[:8].upper() if len(compact) >= 8 else compact.upper()


def resolve_title_seed_id(
    *,
    spoiler_path: Optional[Path] = None,
    seed_id: Optional[str] = None,
    patcher_data: Optional[dict] = None,
) -> str:
    """Prefer the real AP seed; fall back to a short layout UUID."""
    direct = format_display_seed_id(seed_id or "")
    if direct:
        return direct
    if spoiler_path is not None:
        from_spoiler = format_display_seed_id(spoiler_seed_key(spoiler_path))
        if from_spoiler:
            return from_spoiler
    if isinstance(patcher_data, dict):
        short = layout_uuid_short(patcher_data.get("layout_uuid"))
        if short:
            return short
    return "unknown"


def build_company_title_screen(
    *,
    version: Optional[str] = None,
    odr_version: Optional[str] = None,
    seed_id: str,
) -> str:
    ver = (version or ap_world_version()).strip()
    odr = (odr_version or open_dread_rando_version()).strip()
    sid = (seed_id or "unknown").strip() or "unknown"
    return (
        f"Metroid Bread AP\n"
        f"AP World v{ver} - open-dread-rando {odr}|{sid}"
    )


def apply_company_title_screen(
    patcher_data: dict,
    *,
    seed_id: Optional[str] = None,
    spoiler_path: Optional[Path] = None,
) -> str:
    """
    Replace GUI_COMPANY_TITLE_SCREEN entirely (no RDV leftover prepend).

    Also refreshes difficulty-selector descriptors when present so they do not
    keep the stale sample-seed word hash.
    """
    sid = resolve_title_seed_id(
        spoiler_path=spoiler_path,
        seed_id=seed_id,
        patcher_data=patcher_data,
    )
    title = build_company_title_screen(seed_id=sid)
    text = patcher_data.setdefault("text_patches", {})
    if isinstance(text, dict):
        text["GUI_COMPANY_TITLE_SCREEN"] = title
        for key in _DIFSELECTOR_LABEL_KEYS:
            text[key] = sid
    return title


def _read_layout_uuid(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    value = data.get("layout_uuid") if isinstance(data, dict) else None
    if isinstance(value, str) and value and value not in _PLACEHOLDER_LAYOUT_UUIDS:
        return value
    return None


def derive_layout_uuid(spoiler_path: Path, player_name: str) -> str:
    """Deterministic UUID for a spoiler+player (safe across re-patches)."""
    key = f"{spoiler_seed_key(spoiler_path)}::{player_name}"
    return str(uuid.uuid5(_AP_DREAD_LAYOUT_NAMESPACE, key))


def resolve_layout_uuid(
    spoiler_path: Path,
    player_name: str,
    template_patcher: dict,
    *,
    layout_uuid: Optional[str] = None,
) -> str:
    """
    Pick layout_uuid without inventing a fresh random id each run.

    Priority:
      1. Explicit override (recovery / CLI)
      2. Existing AP_<player>_patcher.json next to the spoiler (preserve prior patch)
      3. Non-placeholder UUID already on the template (rare intentional override)
      4. Deterministic uuid5(seed, player)
    """
    if isinstance(layout_uuid, str) and layout_uuid.strip():
        return layout_uuid.strip()

    existing = _read_layout_uuid(spoiler_path.parent / f"AP_{player_name}_patcher.json")
    if existing:
        print(f"[OK] Preserving layout_uuid from existing patcher JSON: {existing}")
        return existing

    tmpl = template_patcher.get("layout_uuid")
    if isinstance(tmpl, str) and tmpl and tmpl not in _PLACEHOLDER_LAYOUT_UUIDS:
        print(f"[OK] Using layout_uuid from template: {tmpl}")
        return tmpl

    derived = derive_layout_uuid(spoiler_path, player_name)
    print(f"[OK] Derived stable layout_uuid from seed+player: {derived}")
    return derived


# Reveal sprite per pickup_index from the most recent create_patcher_json call.
# patcher.json cannot carry it (ODR rejects unknown keys) and only the spoiler
# knows the AP item name, which beats the pickup `model` for progressives.
_LAST_MAP_ICON_SPRITES: Dict[int, Tuple[int, int]] = {}


def last_map_icon_sprites() -> Dict[int, Tuple[int, int]]:
    return dict(_LAST_MAP_ICON_SPRITES)


def create_patcher_json(
    spoiler_path: Path,
    our_player_name: str,
    template_patcher: dict,
    *,
    layout_uuid: Optional[str] = None,
) -> dict:
    """Create patcher.json from Archipelago spoiler."""
    
    print(f"[INFO] Parsing spoiler: {spoiler_path}")
    our_player_name = resolve_dread_player(spoiler_path, our_player_name)
    print(f"[INFO] Using player: {our_player_name}")
    placements = parse_spoiler(spoiler_path, our_player_name)
    print(f"[INFO] Found {len(placements)} item placements")
    if not placements:
        raise ValueError(
            f"Spoiler parsed OK but found 0 placements for {our_player_name!r}. "
            "Check that location lines use '(PlayerName): Item (Owner)' format."
        )
    
    start_ref = parse_starting_location(spoiler_path, our_player_name)
    resolved_layout_uuid = resolve_layout_uuid(
        spoiler_path,
        our_player_name,
        template_patcher,
        layout_uuid=layout_uuid,
    )

    # Start with template structure (open-dread-rando schema; same target as Randovania)
    patcher_data = {
        "configuration_identifier": "AP_MULTIWORLD",
        "starting_location": start_ref,
        "starting_items": {
            "ITEM_WEAPON_MISSILE_MAX": 15,
            "ITEM_FLOOR_SLIDE": 1,
        },
        "starting_text": [["{c1}Archipelago Multiworld{c0}"]],
        "pickups": [],
        "elevators": template_patcher.get("elevators", []),
        "hints": [],  # filled from spoiler below
        "text_patches": template_patcher.get("text_patches", {}),
        "spoiler_log": template_patcher.get("spoiler_log", {}),  # Dict, not array
        # Deep-copy so seed cosmetics cannot mutate the shared template dict.
        "cosmetic_patches": copy.deepcopy(template_patcher.get("cosmetic_patches", {})),
        "energy_per_tank": template_patcher.get("energy_per_tank", 100),
        # Defaults match RDV starter / Options.py (YAML extras override below).
        "immediate_energy_parts": template_patcher.get("immediate_energy_parts", True),
        "enable_remote_lua": True,  # Required for Archipelago client
        "constant_environment_damage": _normalize_constant_environment_damage(
            template_patcher.get(
                "constant_environment_damage",
                {"heat": 20, "cold": 20, "lava": 20},
            )
        ),
        "game_patches": {
            # Cannot include custom files here due to schema restrictions
            # randomizer_powerup.lua must be manually copied to the mod folder
            **template_patcher.get("game_patches", {})
        },
        "show_shields_on_minimap": template_patcher.get("show_shields_on_minimap", True),
        "door_patches": template_patcher.get("door_patches", []),
        "tile_group_patches": template_patcher.get("tile_group_patches", []),
        "new_spawn_points": template_patcher.get("new_spawn_points", []),
        "objective": template_patcher.get("objective", {}),  # Back to template
        "mass_delete_actors": template_patcher.get(
            "mass_delete_actors", {"to_remove": [], "to_keep": []}
        ),
        "layout_uuid": resolved_layout_uuid,
        "mod_compatibility": "ryujinx",  # Required for Ryujinx emulator
        "mod_category": "romfs"  # Required for proper mod loading
    }

    # Seed YAML extras (doors / elevators / DNA / cosmetics) from write_spoiler_header.
    extras = parse_dread_patch_extras(spoiler_path, our_player_name)

    # Death counter: YAML default ON; extras may override via cosmetic_combat.
    if not extras or extras.get("cosmetic_combat", {}).get("enable_death_counter", True):
        enable_death_counter(patcher_data)

    from dread_adam_hints import build_adam_hints

    patcher_data["hints"] = build_adam_hints(placements, our_player=our_player_name)
    print(f"[OK] Generated {len(patcher_data['hints'])} Adam Nav Station hints")

    apply_dread_patch_extras(patcher_data, extras, our_player=our_player_name)

    try:
        from flash_shift import plan_from_extras

        flash_shift_plan = plan_from_extras(extras)
    except Exception:
        flash_shift_plan = None

    try:
        from dread_item_mapping import yields_from_extras

        yield_plan = yields_from_extras(extras)
    except Exception:
        yield_plan = None

    # Legacy spoilers without extras: keep vanilla X and no DNA gate.
    if not extras:
        if "game_patches" in patcher_data and isinstance(patcher_data["game_patches"], dict):
            patcher_data["game_patches"]["default_x_released"] = False
        if "objective" in patcher_data and isinstance(patcher_data["objective"], dict):
            patcher_data["objective"]["required_artifacts"] = 0
            patcher_data["objective"]["hints"] = []

    # Sanitize starting_items against ODR schema
    start = patcher_data.get("starting_items") or {}
    patcher_data["starting_items"] = {
        _sanitize_item_id(k): v for k, v in start.items() if _sanitize_item_id(k) != "ITEM_NONE" or k == "ITEM_NONE"
    }
    
    # Generate pickups (dedupe by PickupIndex — spoilers can list the same check twice)
    foreign_count = 0
    dread_count = 0
    seen_indices: set[int] = set()
    skipped_dupes = 0
    # pickup_index → reveal name for MAP_ICON_ItemCustom{n}_R / _R_IL text_patches.
    # Keyed by pickup_index, never by a local counter: only the sidecar knows which
    # pickups ODR actually numbers (via original_actor ∈ vanilla bmmap items).
    map_icon_item_by_pickup: dict[int, str] = {}
    # pickup_index → (row, col) the icon reveals to on collect / AP hint.
    map_icon_sprite_by_pickup: dict[int, tuple[int, int]] = {}
    dna_artifact_next = 1

    for region, area, node, item, item_player, is_ours in placements:
        # Get pickup index
        location_key = f"{region}/{area}/{node}"
        if location_key not in AP_TO_RANDOVANIA_LOCATION_MAP:
            print(f"[WARNING] Unknown location: {location_key}")
            continue

        _, pickup_index = AP_TO_RANDOVANIA_LOCATION_MAP[location_key]
        if pickup_index in seen_indices:
            skipped_dupes += 1
            continue
        seen_indices.add(pickup_index)

        is_foreign = not is_ours
        dna_idx = None
        if item == "Metroid DNA" and is_ours:
            dna_idx = dna_artifact_next
            dna_artifact_next += 1
        pickup_entry = create_pickup_entry(
            pickup_index,
            item,
            is_foreign,
            item_player,
            dna_artifact_index=dna_idx,
            flash_shift_plan=flash_shift_plan,
            yield_plan=yield_plan,
        )

        if pickup_entry:
            patcher_data["pickups"].append(pickup_entry)
            if is_foreign:
                foreign_count += 1
            else:
                dread_count += 1
            if (
                pickup_entry.get("pickup_type") == "actor"
                and isinstance(pickup_entry.get("map_icon"), dict)
                and "custom_icon" in pickup_entry["map_icon"]
            ):
                map_icon_item_by_pickup[pickup_index] = _map_icon_item_label(
                    item, is_foreign, item_player if is_foreign else None
                )
                map_icon_sprite_by_pickup[pickup_index] = sprite_for_item(
                    item, is_foreign=is_foreign
                )

    special_count = sum(
        1 for p in patcher_data["pickups"] if p.get("pickup_type") != "actor"
    )
    actor_custom = sum(
        1
        for p in patcher_data["pickups"]
        if p.get("pickup_type") == "actor"
        and isinstance(p.get("map_icon"), dict)
        and "custom_icon" in p["map_icon"]
    )
    print(f"[OK] Generated {len(patcher_data['pickups'])} pickups")
    print(f"     - {dread_count} Dread items")
    print(f"     - {foreign_count} foreign items (display names; AP client grants)")
    print(f"     - {special_count} boss/EMMI death pickups (lua callbacks)")
    print(f"     - {actor_custom} actor pickups with unique MAP_ICON_ItemCustom* (Phase 2)")
    if skipped_dupes:
        print(f"     - skipped {skipped_dupes} duplicate spoiler lines")
    if special_count < len(SPECIAL_PICKUPS):
        print(
            f"[WARN] Expected {len(SPECIAL_PICKUPS)} special pickups; "
            "some boss/EMMI checks may still grant vanilla items."
        )

    # Bake [IN/OUT OF LOGIC] × Unknown/revealed BTXT keys (ODR text_patches).
    from dread_map_icon_labels import (
        build_map_icon_keys_for_patcher,
        build_map_label_text_patches,
        item_names_by_custom_n,
        merge_text_patches,
    )

    _LAST_MAP_ICON_SPRITES.clear()
    _LAST_MAP_ICON_SPRITES.update(map_icon_sprite_by_pickup)

    keys_preview = build_map_icon_keys_for_patcher(
        patcher_data, sprite_by_pickup_index=map_icon_sprite_by_pickup
    )
    label_patches = build_map_label_text_patches(
        keys_preview, item_names_by_custom_n(keys_preview, map_icon_item_by_pickup)
    )
    patcher_data["text_patches"] = merge_text_patches(
        patcher_data.get("text_patches"), label_patches
    )
    print(
        f"[OK] Map label text_patches: {len(label_patches)} keys "
        f"({keys_preview.get('custom_icon_count', 0)} icons × 4 variants)"
    )
    no_icon = len(keys_preview.get("skipped") or [])
    if no_icon:
        print(f"     - {no_icon} pickups keep their vanilla map icon (no ItemCustom slot)")

    # Title screen: replace RDV sample leftovers with AP branding + real seed id.
    title = apply_company_title_screen(patcher_data, spoiler_path=spoiler_path)
    print(f"[OK] Title screen: {title.replace(chr(10), ' / ')}")

    # Samus-menu upgrade rows (ODR ≥2.19). Safe no-op / strip on ≤2.18.
    apply_upgrade_menu_flags(patcher_data)

    # Belt-and-suspenders: strip any fields this process's ODR rejects
    # (template leftovers, validate()-filled defaults, extras applied early).
    removed = sanitize_patcher_for_odr(patcher_data)
    if removed:
        print(
            f"[INFO] Stripped unsupported patcher keys for ODR schema: "
            f"{', '.join(removed)}"
        )

    print("[NOTE] Prefer: py -3.11 dread_direct_patch.py --spoiler ... --player ...")

    return patcher_data


def main():
    if len(sys.argv) < 3:
        print("Usage: python ap_to_patcher.py <spoiler_file> <player_name> [output_file]")
        print("Or use the full pipeline: python dread_direct_patch.py --spoiler ... --player ...")
        sys.exit(1)

    spoiler_path = Path(sys.argv[1])
    our_player_name = sys.argv[2]
    output_file = Path(sys.argv[3]) if len(sys.argv) > 3 else _ROOT / "archipelago_patcher.json"

    print("[INFO] Loading template patcher.json...")
    with open(_ROOT / "sample_patcher_WORKING.json", encoding="utf-8") as f:
        template = json.load(f)

    patcher_data = create_patcher_json(spoiler_path, our_player_name, template)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(patcher_data, f, indent=2)

    from dread_map_icon_labels import (
        build_map_icon_keys_for_patcher,
        write_map_icon_keys,
    )

    keys_path = output_file.with_name(
        output_file.name.replace("_patcher.json", "_map_icon_keys.json")
        if output_file.name.endswith("_patcher.json")
        else "map_icon_keys.json"
    )
    if keys_path == output_file:
        keys_path = output_file.parent / "map_icon_keys.json"
    keys = build_map_icon_keys_for_patcher(
        patcher_data, sprite_by_pickup_index=last_map_icon_sprites()
    )
    write_map_icon_keys(keys_path, keys)

    print(f"\n[OK] Created: {output_file}")
    print(
        f"[OK] Created: {keys_path} "
        f"({keys.get('custom_icon_count', 0)} MAP_ICON_ItemCustom* keys)"
    )
    print("Apply with dread_direct_patch.py (recommended) or:")
    print(f"  py -3.11 -m open_dread_rando --input-json {output_file} --input-path <base_rom> --output-path <ryujinx_mod>")


if __name__ == "__main__":
    main()

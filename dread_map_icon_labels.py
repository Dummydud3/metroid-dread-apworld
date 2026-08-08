"""
Map-icon labels: Unknown until collect/hint, with [IN LOGIC]/[OUT OF LOGIC] prefixes.

ODR MapIconEditor assigns ItemCustom{n} sequentially for actor pickups that have
map_icon.custom_icon, in patcher.json pickups-array order (special boss/EMMI
entries have no custom_icon and do not consume a number).

CRITICAL: having custom_icon is necessary but NOT sufficient. ODR only reaches
MapIconEditor.get_data() — the call that increments the counter — from
pickup.py::patch_minimap_icon, and only when the pickup's map actor is present in
that scenario's vanilla .bmmap `items` category:

    if map_actor["actor"] in map_def.items:
        icon = map_def.items.pop(map_actor["actor"])
        icon.sIconId = editor.map_icon_editor.get_data(self.pickup)

The 12 major-item spheres (ItemSphere_ChargeBeam, IT_VARIA_GEN_001,
itemsphere_gravitysuit, powerup-label pickups, ...) have no minimap `items`
entry, so they get no custom icon and consume no number. Numbering them anyway
shifts every later pickup (Waterfall Energy Part drifted +3: the client wrote its
label into MAP_ICON_ItemCustom22 while the game reads MAP_ICON_ItemCustom19),
which shows the wrong in/out-of-logic state AND the wrong revealed item name.
dread_map_icon_actors.json carries the vanilla `items` lists so this module can
reproduce ODR's numbering without the base ROM.

Patch-time BTXT (via ODR text_patches) bakes four keys per icon:
  MAP_ICON_ItemCustom{n}      → [OUT OF LOGIC] Unknown Item  (default / display key)
  MAP_ICON_ItemCustom{n}_IL   → [IN LOGIC] Unknown Item
  MAP_ICON_ItemCustom{n}_R    → [OUT OF LOGIC] {Item}
  MAP_ICON_ItemCustom{n}_R_IL → [IN LOGIC] {Item}

Runtime: RL.ApplyMapIconVariants prefers OdrMap.SetIconInspectorLabel (retargets
the display key → variant key, no language-bank force) but ONLY treats it as
applied when the native GetLocalized hook is confirmed live
(OdrText.HasLabelRedirect). That hook is currently disabled for hover-crash
safety, so the working path today is OdrText.SetLocalized(base_key, full_text)
— callers must pass `texts` to format_apply_map_icon_variants_chunks, not just
`variants`, or icons stay stuck on their patch-time default text.

Icon GRAPHICS follow the same revealed set as the labels. Every ItemCustom{n}
is a separate bmmdef icon definition used by exactly one pickup, so revealing
one location is a single write of that definition's sprite-atlas cell:

    OdrMap.SetIconSprite("ItemCustom19", row, col)

Unrevealed icons are pushed back to UNKNOWN_SPRITE (the ? cell ODR bakes in at
patch time), so un-hinting or a fresh connect restores the hidden state. The
atlas cell for each location's real item is baked into the sidecar at patch
time (entries[].sprite) from the same placement the _R label variants use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

ROOT = Path(__file__).resolve().parent

MapIconKeys = Dict[str, Any]

# v3 reproduced ODR's real ItemCustom{n} numbering (v2 numbered pickups ODR skips).
# v4 adds entries[].sprite — the atlas cell each icon reveals to.
KEYS_VERSION = 4

PREFIX_IN = "[IN LOGIC]"
PREFIX_OUT = "[OUT OF LOGIC]"
UNKNOWN_ITEM = "Unknown Item"

Sprite = Tuple[int, int]

# Minimap sprite-atlas cells as (row, col).
#
# open_dread_rando.pickups.map_icons.ALL_ICONS stores these the other way round
# — MapIcon.coords is (col, row) and add_to_defs passes coords[1] then
# coords[0] — so every entry here is that tuple reversed. Cross-checked against
# the vanilla bmmdef: item_missiletank coords=(7, 0) and the shipped
# ItemMissileTank def has uSpriteRow=0, uSpriteCol=7.
UNKNOWN_SPRITE: Sprite = (7, 15)  # ODR "unknown" — the ? cell every icon starts on
GENERIC_ITEM_SPRITE: Sprite = (0, 4)  # vanilla ItemSphere; used when nothing better fits

ICON_SPRITES: Dict[str, Sprite] = {
    "item_energytank": (0, 5),
    "item_energyfragment": (0, 6),
    "item_missiletank": (0, 7),
    "item_missiletankplus": (0, 8),
    "item_powerbombtank": (0, 9),
    "item_speedboostupgrade": (5, 14),
    "item_flashshiftupgrade": (5, 15),
    "powerup_widebeam": (6, 0),
    "powerup_plasmabeam": (6, 1),
    "powerup_wavebeam": (6, 2),
    "powerup_chargebeam": (6, 3),
    "powerup_diffusionbeam": (6, 4),
    "powerup_grapplebeam": (6, 5),
    "powerup_supermissile": (6, 6),
    "powerup_icemissile": (6, 7),
    "powerup_stormmissile": (6, 8),
    "powerup_opticcamo": (6, 9),
    "powerup_ghostaura": (6, 10),
    "powerup_sonar": (6, 11),
    "powerup_variasuit": (6, 12),
    "powerup_gravitysuit": (6, 13),
    "powerup_morphball": (6, 14),
    "powerup_bomb": (6, 15),
    "powerup_crossbomb": (7, 0),
    "powerup_powerbomb": (7, 1),
    "powerup_spidermagnet": (7, 2),
    "powerup_speedbooster": (7, 3),
    "powerup_doublejump": (7, 4),
    "powerup_spacejump": (7, 5),
    "powerup_screwattack": (7, 6),
    "PROGRESSIVE_BEAM": (7, 7),
    "PROGRESSIVE_CHARGE": (7, 8),
    "PROGRESSIVE_MISSILE": (7, 9),
    "PROGRESSIVE_SUIT": (7, 10),
    "PROGRESSIVE_BOMB": (7, 11),
    "PROGRESSIVE_SPIN": (7, 12),
    "DNA": (7, 13),
    "itemsphere": GENERIC_ITEM_SPRITE,
    "unknown": UNKNOWN_SPRITE,
}

# patcher.json `model` values that do not name an ALL_ICONS entry. These are 3D
# model names from dread_item_mapping, which predate (and do not track) ODR's
# icon keys — Spider Magnet ships as "powerup_magnet" but its icon is
# "powerup_spidermagnet". Missile Launcher and Slide have no icon of their own.
MODEL_TO_ICON: Dict[str, str] = {
    "powerup_magnet": "powerup_spidermagnet",
    "powerup_phantom": "powerup_opticcamo",
    "powerup_flashshift": "powerup_ghostaura",
    "powerup_grapple": "powerup_grapplebeam",
    "item_multimisilletank": "item_missiletankplus",
    "powerup_missilelauncher": "item_missiletank",
    "powerup_slide": "itemsphere",
}

# AP item name → icon key. Progressive items get their own atlas cell, so they
# must not fall through to the first stage's icon.
ITEM_TO_ICON: Dict[str, str] = {
    "Energy Tank": "item_energytank",
    "Energy Part": "item_energyfragment",
    "Missile Tank": "item_missiletank",
    "Missile+ Tank": "item_missiletankplus",
    "Power Bomb Tank": "item_powerbombtank",
    "Wide Beam": "powerup_widebeam",
    "Plasma Beam": "powerup_plasmabeam",
    "Wave Beam": "powerup_wavebeam",
    "Charge Beam": "powerup_chargebeam",
    "Diffusion Beam": "powerup_diffusionbeam",
    "Ice Missile": "powerup_icemissile",
    "Storm Missile": "powerup_stormmissile",
    "Super Missile": "powerup_supermissile",
    "Varia Suit": "powerup_variasuit",
    "Gravity Suit": "powerup_gravitysuit",
    "Morph Ball": "powerup_morphball",
    "Spider Magnet": "powerup_spidermagnet",
    "Speed Booster": "powerup_speedbooster",
    "Speed Booster Upgrade": "item_speedboostupgrade",
    "Spin Boost": "powerup_doublejump",
    "Space Jump": "powerup_spacejump",
    "Screw Attack": "powerup_screwattack",
    "Bomb": "powerup_bomb",
    "Cross Bomb": "powerup_crossbomb",
    "Power Bomb": "powerup_powerbomb",
    "Phantom Cloak": "powerup_opticcamo",
    "Flash Shift": "powerup_ghostaura",
    "Flash Shift Upgrade": "item_flashshiftupgrade",
    "Slide": "itemsphere",
    "Missile Launcher": "item_missiletank",
    "Missiles": "item_missiletank",
    "Pulse Radar": "powerup_sonar",
    "Grapple Beam": "powerup_grapplebeam",
    "Progressive Charge Beam": "PROGRESSIVE_CHARGE",
    "Progressive Suit": "PROGRESSIVE_SUIT",
    "Progressive Beam": "PROGRESSIVE_BEAM",
    "Progressive Missile": "PROGRESSIVE_MISSILE",
    "Progressive Missiles": "PROGRESSIVE_MISSILE",
    "Progressive Bomb": "PROGRESSIVE_BOMB",
    "Progressive Bombs": "PROGRESSIVE_BOMB",
    "Progressive Spin": "PROGRESSIVE_SPIN",
}


def sprite_for_model(model: Optional[str]) -> Sprite:
    """Atlas cell for a patcher.json `model` value (the derive-from-json path)."""
    key = (model or "").strip()
    if not key:
        return GENERIC_ITEM_SPRITE
    key = MODEL_TO_ICON.get(key, key)
    return ICON_SPRITES.get(key, GENERIC_ITEM_SPRITE)


def sprite_for_item(item_name: Optional[str], *, is_foreign: bool = False) -> Sprite:
    """
    Atlas cell for an AP item name.

    Foreign items still resolve when the other world happens to use a Dread
    item name; anything unrecognised falls back to the generic item sphere
    rather than the ? cell, so a revealed icon always looks revealed.
    """
    name = (item_name or "").strip()
    if not name:
        return GENERIC_ITEM_SPRITE
    if name.startswith("Metroid DNA"):
        return ICON_SPRITES["DNA"]
    icon = ITEM_TO_ICON.get(name)
    if icon is None:
        return GENERIC_ITEM_SPRITE
    return ICON_SPRITES.get(icon, GENERIC_ITEM_SPRITE)


def normalize_sprite(value: Any) -> Optional[Sprite]:
    """Coerce a sidecar/JSON sprite to (row, col), rejecting out-of-atlas values."""
    if isinstance(value, Mapping):
        value = (value.get("row"), value.get("col"))
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        row = int(value[0])
        col = int(value[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= row <= 63 and 0 <= col <= 63):
        return None
    return row, col


def _load_pickup_actors() -> Dict[str, dict]:
    path = ROOT / "dread_pickup_actors.json"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _actor_key(scenario: str, actor: str) -> str:
    return f"{scenario}/{actor}"


_MAP_ITEM_ACTORS: Optional[Dict[str, frozenset]] = None


def map_item_actors() -> Dict[str, frozenset]:
    """scenario → actors in the vanilla minimap `items` category (ODR's gate)."""
    global _MAP_ITEM_ACTORS
    if _MAP_ITEM_ACTORS is None:
        data: Dict[str, Any] = {}
        path = ROOT / "dread_map_icon_actors.json"
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded.get("items") or {}
            except (OSError, json.JSONDecodeError):
                data = {}
        _MAP_ITEM_ACTORS = {
            str(scenario): frozenset(str(a) for a in actors)
            for scenario, actors in data.items()
            if isinstance(actors, (list, tuple, set))
        }
    return _MAP_ITEM_ACTORS


def has_custom_map_icon(scenario: str, actor: str) -> bool:
    """Does ODR assign this pickup an ItemCustom{n}?

    True when the actor is a vanilla minimap item. Unknown scenarios fall back to
    True so a missing/stale table degrades to the old (over-numbering) behaviour
    instead of dropping every label.
    """
    table = map_item_actors()
    known = table.get(scenario)
    if known is None:
        return True
    return actor in known


def actor_to_pickup_index() -> Dict[str, int]:
    """scenario/actor → Randovania pickup index."""
    out: Dict[str, int] = {}
    for index_str, data in _load_pickup_actors().items():
        if not isinstance(data, dict):
            continue
        scenario = str(data.get("scenario") or "")
        actor = str(data.get("actor") or "")
        if scenario and actor:
            out[_actor_key(scenario, actor)] = int(index_str)
    return out


def pickup_index_to_location_id() -> Dict[int, int]:
    """Reuse client bridge mapping (pickup bit index → AP location id)."""
    try:
        from dread_client_bridge import pickup_index_to_ap_location

        return dict(pickup_index_to_ap_location())
    except Exception:
        return {}


def build_map_icon_keys_from_pickups(
    pickups: Sequence[Mapping[str, Any]],
    *,
    pickup_indices: Optional[Sequence[Optional[int]]] = None,
    sprite_by_pickup_index: Optional[Mapping[int, Sequence[int]]] = None,
) -> MapIconKeys:
    """
    Build sidecar mapping mirroring ODR custom_icon assignment order.

    If pickup_indices is provided, it must align with pickups (None for skips).
    Otherwise pickup_index is resolved from pickup_actor via dread_pickup_actors.json.

    Pickups whose map actor has no vanilla minimap `items` entry are skipped
    without consuming a number, exactly like ODR's patch_minimap_icon.

    Each entry also carries the atlas cell its icon reveals to. Callers that
    know the AP item name (ap_to_patcher) should pass sprite_by_pickup_index;
    otherwise it is derived from the pickup's `model`, which is all a bare
    patcher.json exposes.
    """
    actor_lookup = actor_to_pickup_index()
    loc_lookup = pickup_index_to_location_id()

    by_pickup_index: Dict[str, str] = {}
    by_location_id: Dict[str, str] = {}
    by_actor: Dict[str, str] = {}
    entries: List[dict] = []
    skipped: List[dict] = []

    custom_n = 0
    for i, pickup in enumerate(pickups):
        if not isinstance(pickup, Mapping):
            continue
        if pickup.get("pickup_type") != "actor":
            continue
        map_icon = pickup.get("map_icon") or {}
        if not isinstance(map_icon, Mapping) or "custom_icon" not in map_icon:
            continue

        pa = pickup.get("pickup_actor") or {}
        if not isinstance(pa, Mapping):
            pa = {}
        scenario = str(pa.get("scenario") or "")
        actor = str(pa.get("actor") or "")
        actor_path = _actor_key(scenario, actor) if scenario and actor else ""

        pickup_index: Optional[int] = None
        if pickup_indices is not None and i < len(pickup_indices):
            pickup_index = pickup_indices[i]
        if pickup_index is None and actor_path:
            pickup_index = actor_lookup.get(actor_path)
        loc_id = loc_lookup.get(int(pickup_index)) if pickup_index is not None else None

        # ODR reads the icon off map_icon.original_actor when present.
        original = map_icon.get("original_actor")
        if isinstance(original, Mapping):
            map_scenario = str(original.get("scenario") or scenario)
            map_actor = str(original.get("actor") or actor)
        else:
            map_scenario, map_actor = scenario, actor

        if not has_custom_map_icon(map_scenario, map_actor):
            skipped.append(
                {
                    "pickup_index": pickup_index,
                    "location_id": loc_id,
                    "scenario": map_scenario,
                    "actor": map_actor,
                    "reason": "no vanilla minimap item entry",
                }
            )
            continue

        key = f"MAP_ICON_ItemCustom{custom_n}"
        custom_n += 1

        if actor_path:
            by_actor[actor_path] = key
        if pickup_index is not None:
            by_pickup_index[str(pickup_index)] = key
            if loc_id is not None:
                by_location_id[str(loc_id)] = key

        sprite: Optional[Sprite] = None
        if sprite_by_pickup_index is not None and pickup_index is not None:
            sprite = normalize_sprite(sprite_by_pickup_index.get(int(pickup_index)))
        if sprite is None:
            model = pickup.get("model")
            if isinstance(model, (list, tuple)) and model:
                model = model[0]
            sprite = sprite_for_model(model if isinstance(model, str) else None)

        entries.append(
            {
                "custom_n": custom_n - 1,
                "key": key,
                "icon_id": f"ItemCustom{custom_n - 1}",
                "pickup_index": pickup_index,
                "location_id": loc_id,
                "scenario": scenario,
                "actor": actor,
                "sprite": [sprite[0], sprite[1]],
            }
        )

    return {
        "version": KEYS_VERSION,
        "custom_icon_count": custom_n,
        "unknown_sprite": [UNKNOWN_SPRITE[0], UNKNOWN_SPRITE[1]],
        "by_pickup_index": by_pickup_index,
        "by_location_id": by_location_id,
        "by_actor": by_actor,
        "entries": entries,
        "skipped": skipped,
    }


def _sprites_from_reveal_patches(patcher_data: Mapping[str, Any]) -> Dict[int, Sprite]:
    """
    custom_n → sprite, read back out of the baked MAP_ICON_ItemCustom{n}_R strings.

    A patcher.json on its own only exposes each pickup's 3D `model`, which cannot
    tell Progressive Beam from Wide Beam. The revealed label already carries the
    AP item name, so rebuilds from patcher.json alone stay exact.
    """
    out: Dict[int, Sprite] = {}
    patches = patcher_data.get("text_patches")
    if not isinstance(patches, Mapping):
        return out
    for key, value in patches.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if not (key.startswith("MAP_ICON_ItemCustom") and key.endswith("_R")):
            continue
        try:
            n = int(key[len("MAP_ICON_ItemCustom") : -len("_R")])
        except ValueError:
            continue
        name = value.strip()
        for prefix in (PREFIX_IN, PREFIX_OUT):
            if name.startswith(prefix):
                name = name[len(prefix) :].strip()
                break
        if name and name != UNKNOWN_ITEM:
            out[n] = sprite_for_item(name)
    return out


def build_map_icon_keys_for_patcher(
    patcher_data: Mapping[str, Any],
    *,
    sprite_by_pickup_index: Optional[Mapping[int, Sequence[int]]] = None,
) -> MapIconKeys:
    pickups = patcher_data.get("pickups") or []
    if not isinstance(pickups, list):
        pickups = []
    keys = build_map_icon_keys_from_pickups(
        pickups, sprite_by_pickup_index=sprite_by_pickup_index
    )
    if not sprite_by_pickup_index:
        by_custom_n = _sprites_from_reveal_patches(patcher_data)
        if by_custom_n:
            for entry in keys["entries"]:
                sprite = by_custom_n.get(entry.get("custom_n"))
                if sprite is not None:
                    entry["sprite"] = [sprite[0], sprite[1]]
    return keys


def write_map_icon_keys(path: Path, keys: MapIconKeys) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    return path


def load_map_icon_keys(path: Union[str, Path]) -> Optional[MapIconKeys]:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def find_map_icon_keys_file(
    *,
    mod_root: Optional[Union[str, Path]] = None,
    spoiler_dir: Optional[Union[str, Path]] = None,
    player_name: Optional[str] = None,
    games_folder: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Search common patch-output locations for map_icon_keys.json."""
    candidates: List[Path] = []
    if mod_root:
        root = Path(mod_root)
        for base in (root, root / "DreadRandovania"):
            candidates.append(base / "map_icon_keys.json")
    if spoiler_dir:
        sd = Path(spoiler_dir)
        if player_name:
            candidates.append(sd / f"AP_{player_name}_map_icon_keys.json")
        candidates.extend(sorted(sd.glob("AP_*_map_icon_keys.json")))
    if games_folder and player_name:
        gf = Path(games_folder)
        candidates.append(gf / f"AP_{player_name}_map_icon_keys.json")
        for sub in sorted(gf.glob("*")):
            if sub.is_dir():
                candidates.append(sub / f"AP_{player_name}_map_icon_keys.json")

    for path in candidates:
        if path.is_file():
            return path
    return None


def load_or_derive_map_icon_keys(
    *,
    mod_root: Optional[Union[str, Path]] = None,
    spoiler_dir: Optional[Union[str, Path]] = None,
    player_name: Optional[str] = None,
    games_folder: Optional[Union[str, Path]] = None,
    patcher_json: Optional[Union[str, Path]] = None,
) -> Tuple[Optional[MapIconKeys], Optional[Path]]:
    """
    Load sidecar if present; else derive from patcher.json pickups order.

    A sidecar written before KEYS_VERSION is ignored in favour of re-deriving from
    patcher.json: v2 files numbered every custom_icon pickup, including the major-item
    spheres ODR never gives an icon, so their keys are shifted and would paint labels
    onto the wrong map icons. The stale file is still used as a last resort when no
    patcher.json is reachable.

    Returns (keys, source_path_or_None).
    """
    found = find_map_icon_keys_file(
        mod_root=mod_root,
        spoiler_dir=spoiler_dir,
        player_name=player_name,
        games_folder=games_folder,
    )
    stale: Tuple[Optional[MapIconKeys], Optional[Path]] = (None, None)
    if found is not None:
        keys = load_map_icon_keys(found)
        if keys is not None:
            try:
                version = int(keys.get("version") or 0)
            except (TypeError, ValueError):
                version = 0
            if version >= KEYS_VERSION:
                return keys, found
            stale = (keys, found)

    patcher_candidates: List[Path] = []
    if patcher_json:
        patcher_candidates.append(Path(patcher_json))
    if mod_root:
        root = Path(mod_root)
        for base in (root, root / "DreadRandovania"):
            patcher_candidates.append(base / "patcher.json")
    if spoiler_dir and player_name:
        patcher_candidates.append(Path(spoiler_dir) / f"AP_{player_name}_patcher.json")

    for pj in patcher_candidates:
        if not pj.is_file():
            continue
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("pickups"), list):
            return build_map_icon_keys_for_patcher(data), pj
    return stale


def logic_prefix(in_logic: bool) -> str:
    return PREFIX_IN if in_logic else PREFIX_OUT


def format_map_label(item_or_unknown: str, in_logic: bool) -> str:
    name = (item_or_unknown or "").strip() or UNKNOWN_ITEM
    return f"{logic_prefix(in_logic)} {name}"


def revealed_key(base_key: str) -> str:
    return f"{base_key}_R"


def variant_key(base_key: str, *, revealed: bool, in_logic: bool) -> str:
    """Pick BTXT key for (revealed × in_logic). Display key is always base_key."""
    if revealed and in_logic:
        return f"{base_key}_R_IL"
    if revealed:
        return f"{base_key}_R"
    if in_logic:
        return f"{base_key}_IL"
    return base_key


def icon_id_from_base_key(base_key: str) -> str:
    """MAP_ICON_ItemCustom12 → ItemCustom12."""
    prefix = "MAP_ICON_"
    if base_key.startswith(prefix):
        return base_key[len(prefix) :]
    return base_key


def build_map_label_text_patches(
    keys: Mapping[str, Any],
    item_name_by_custom_n: Mapping[int, str],
) -> Dict[str, str]:
    """
    Four BTXT strings per custom icon for ODR configuration['text_patches'].

    item_name_by_custom_n: custom_n → human-readable item (e.g. \"Morph Ball\").
    """
    patches: Dict[str, str] = {}
    entries = keys.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        try:
            n = int(entry.get("custom_n"))
        except (TypeError, ValueError):
            continue
        base = str(entry.get("key") or f"MAP_ICON_ItemCustom{n}")
        item = str(item_name_by_custom_n.get(n) or UNKNOWN_ITEM).strip() or UNKNOWN_ITEM
        patches[base] = format_map_label(UNKNOWN_ITEM, False)
        patches[f"{base}_IL"] = format_map_label(UNKNOWN_ITEM, True)
        patches[f"{base}_R"] = format_map_label(item, False)
        patches[f"{base}_R_IL"] = format_map_label(item, True)
    return patches


def item_names_by_custom_n(
    keys: Mapping[str, Any],
    item_name_by_pickup_index: Mapping[int, str],
) -> Dict[int, str]:
    """Re-key reveal names pickup_index → custom_n using the built sidecar.

    Callers must never run their own custom_n counter: only the sidecar knows
    which pickups ODR actually numbered.
    """
    out: Dict[int, str] = {}
    entries = keys.get("entries") or []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        try:
            n = int(entry.get("custom_n"))
            pi = int(entry.get("pickup_index"))
        except (TypeError, ValueError):
            continue
        name = item_name_by_pickup_index.get(pi)
        if name:
            out[n] = name
    return out


def merge_text_patches(
    existing: Optional[Mapping[str, Any]],
    new_patches: Mapping[str, str],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(existing, Mapping):
        for k, v in existing.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    out.update(dict(new_patches))
    return out


def collected_label_text(item_name: str) -> str:
    """Legacy helper (SetLocalized path). Prefer format_map_label + variant_key."""
    name = (item_name or "").strip() or UNKNOWN_ITEM
    return f"{name} (Collected)"


def _lua_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def format_apply_map_icon_labels_lua(labels: Mapping[str, str]) -> str:
    """Legacy SetLocalized apply (soft-fail path). Prefer format_apply_map_icon_variants_lua."""
    parts: List[str] = []
    for key in sorted(labels):
        text = labels[key]
        parts.append(f'["{_lua_escape(key)}"]="{_lua_escape(text)}"')
    table = "{" + ",".join(parts) + "}"
    return f"RL.ApplyMapIconLabels({table})"


def format_apply_map_icon_variants_lua(
    variants: Mapping[str, str],
    texts: Optional[Mapping[str, str]] = None,
) -> str:
    """
    Build RL.ApplyMapIconVariants({[baseKey]={variant=..., text=...}, ...}).

    Prefer OdrMap.SetIconInspectorLabel(redirect). If that API is missing (old
    subsdk9), Lua falls back to OdrText.SetLocalized(base, text).

    For large maps use format_apply_map_icon_variants_chunks — a full 137-icon
    table is ~13KB and exceeds the Dread remote-Lua 4096 buffer (PACKET_MALFORMED).
    """
    parts: List[str] = []
    for base in sorted(variants):
        var = _lua_escape(variants[base])
        if texts is not None and base in texts:
            txt = _lua_escape(texts[base])
            parts.append(
                f'["{_lua_escape(base)}"]={{variant="{var}",text="{txt}"}}'
            )
        else:
            parts.append(f'["{_lua_escape(base)}"]="{var}"')
    table = "{" + ",".join(parts) + "}"
    return f"RL.ApplyMapIconVariants({table})"


def format_apply_map_icon_variants_chunks(
    variants: Mapping[str, str],
    texts: Optional[Mapping[str, str]] = None,
    *,
    buffer_size: int = 4096,
    overhead: int = 64,
) -> List[str]:
    """
    Split variant applies into PACKET_REMOTE_LUA_EXEC-safe chunks.

    Uses compact redirect-only entries (no text) when possible — SetIconInspectorLabel
    path does not need text. Falls back to including text only if texts is provided
    AND a single redirect-only entry still needs the setloc fallback (always include
    text when texts is provided for old-subsdk9 compatibility, but keep batches small).
    """
    # RecvBuffer is BufferSize bytes total and also holds type+u32 len (5 bytes).
    max_len = max(256, int(buffer_size) - max(int(overhead), 5))
    bases = sorted(variants)
    chunks: List[str] = []
    batch: List[str] = []

    def _flush() -> None:
        nonlocal batch
        if not batch:
            return
        table = "{" + ",".join(batch) + "}"
        chunks.append(f"RL.ApplyMapIconVariants({table})")
        batch = []

    for base in bases:
        var = _lua_escape(variants[base])
        if texts is not None and base in texts:
            txt = _lua_escape(texts[base])
            entry = f'["{_lua_escape(base)}"]={{variant="{var}",text="{txt}"}}'
        else:
            entry = f'["{_lua_escape(base)}"]="{var}"'

        def _entry_fits(e: str, existing: List[str]) -> bool:
            table = "{" + ",".join(existing + [e]) + "}"
            return len(f"RL.ApplyMapIconVariants({table})") <= max_len

        if batch and not _entry_fits(entry, batch):
            _flush()

        if not _entry_fits(entry, []):
            # Last resort: redirect-only without text (compact).
            entry = f'["{_lua_escape(base)}"]="{var}"'
            if not _entry_fits(entry, []):
                # Should never happen for normal keys; skip rather than MALFORMED.
                continue

        if batch and not _entry_fits(entry, batch):
            _flush()
        batch.append(entry)
    _flush()
    return chunks


def revealed_sprites_by_location_id(keys: Mapping[str, Any]) -> Dict[int, Sprite]:
    """location_id → the atlas cell that location's icon reveals to."""
    out: Dict[int, Sprite] = {}
    entries = keys.get("entries") or []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        try:
            loc_id = int(entry.get("location_id"))
        except (TypeError, ValueError):
            continue
        sprite = normalize_sprite(entry.get("sprite"))
        if sprite is not None:
            out[loc_id] = sprite
    return out


def unknown_sprite(keys: Optional[Mapping[str, Any]] = None) -> Sprite:
    """The hidden-state atlas cell, honouring a sidecar override if present."""
    if isinstance(keys, Mapping):
        override = normalize_sprite(keys.get("unknown_sprite"))
        if override is not None:
            return override
    return UNKNOWN_SPRITE


def format_apply_map_icon_sprites_chunks(
    sprites: Mapping[str, Sequence[int]],
    *,
    buffer_size: int = 4096,
    overhead: int = 64,
) -> List[str]:
    """
    Split RL.ApplyMapIconSprites applies into remote-Lua-safe chunks.

    Keys are icon ids ("ItemCustom19"), not BTXT keys, both because that is
    what OdrMap.SetIconSprite wants and because dropping the MAP_ICON_ prefix
    keeps roughly a third more icons in each 4096-byte packet.
    """
    max_len = max(256, int(buffer_size) - max(int(overhead), 5))
    chunks: List[str] = []
    batch: List[str] = []

    def _flush() -> None:
        nonlocal batch
        if not batch:
            return
        chunks.append("RL.ApplyMapIconSprites({" + ",".join(batch) + "})")
        batch = []

    def _fits(extra: str, existing: List[str]) -> bool:
        table = "{" + ",".join(existing + [extra]) + "}"
        return len(f"RL.ApplyMapIconSprites({table})") <= max_len

    for raw_key in sorted(sprites):
        sprite = normalize_sprite(sprites[raw_key])
        if sprite is None:
            continue
        icon = icon_id_from_base_key(str(raw_key))
        entry = f'["{_lua_escape(icon)}"]={{{sprite[0]},{sprite[1]}}}'
        if not _fits(entry, []):
            continue
        if batch and not _fits(entry, batch):
            _flush()
        batch.append(entry)
    _flush()
    return chunks


def sprites_signature(sprites: Mapping[str, Sequence[int]]) -> Tuple[Tuple[str, Tuple[int, int]], ...]:
    out: List[Tuple[str, Tuple[int, int]]] = []
    for key in sorted(sprites):
        sprite = normalize_sprite(sprites[key])
        if sprite is not None:
            out.append((str(key), sprite))
    return tuple(out)


def format_set_map_icon_label_lua(key: str, text: str) -> str:
    return f'RL.SetMapIconLabel("{_lua_escape(key)}", "{_lua_escape(text)}")'


def labels_signature(labels: Mapping[str, str]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


def variants_signature(variants: Mapping[str, str]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted(variants.items()))

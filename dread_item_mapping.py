"""
Dread Item Mappings for Archipelago

Maps Archipelago item names to Dread resources, models, and icons.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping, Optional

# Default tank yields (match Options.py / RDV starter).
DEFAULT_MISSILE_TANK_AMMO = 2
DEFAULT_MISSILE_PLUS_TANK_AMMO = 10
DEFAULT_POWER_BOMB_TANK_AMMO = 1
DEFAULT_ENERGY_PER_TANK = 100


def yields_from_extras(extras: Optional[Mapping[str, Any]]) -> Dict[str, int]:
    """Resolve ammo / energy yields from patch_extras (or empty → defaults)."""
    extras = extras or {}
    combat = extras.get("cosmetic_combat") if isinstance(extras.get("cosmetic_combat"), Mapping) else {}
    ept = combat.get("energy_per_tank", extras.get("energy_per_tank", DEFAULT_ENERGY_PER_TANK))
    return {
        "missile_tank_ammo": max(1, int(extras.get("missile_tank_ammo", DEFAULT_MISSILE_TANK_AMMO) or DEFAULT_MISSILE_TANK_AMMO)),
        "missile_plus_tank_ammo": max(
            1, int(extras.get("missile_plus_tank_ammo", DEFAULT_MISSILE_PLUS_TANK_AMMO) or DEFAULT_MISSILE_PLUS_TANK_AMMO)
        ),
        "power_bomb_tank_ammo": max(
            1, int(extras.get("power_bomb_tank_ammo", DEFAULT_POWER_BOMB_TANK_AMMO) or DEFAULT_POWER_BOMB_TANK_AMMO)
        ),
        "energy_per_tank": max(1, int(ept or DEFAULT_ENERGY_PER_TANK)),
    }


def _set_resource_qty(resources: Any, item_id: str, qty: int) -> Any:
    """Rewrite quantity for item_id in a flat or staged resources list (in place)."""

    def _walk(stage: Any) -> None:
        if isinstance(stage, list):
            if stage and isinstance(stage[0], dict):
                for entry in stage:
                    if isinstance(entry, dict) and entry.get("item_id") == item_id:
                        entry["quantity"] = int(qty)
            else:
                for nested in stage:
                    _walk(nested)

    _walk(resources)
    return resources


def apply_yield_overrides(
    item_name: str,
    item_data: MutableMapping[str, Any],
    yields: Optional[Mapping[str, int]] = None,
) -> MutableMapping[str, Any]:
    """
    Copy *item_data* and apply YAML ammo / energy-per-tank yields.

    Used by the patcher (world pickups) and the client bridge (remote grants)
    so ROM pickups and AP receives stay in sync with Options.py.
    """
    out = deepcopy(dict(item_data))
    y = dict(yields or {})
    missile = int(y.get("missile_tank_ammo", DEFAULT_MISSILE_TANK_AMMO))
    missile_plus = int(y.get("missile_plus_tank_ammo", DEFAULT_MISSILE_PLUS_TANK_AMMO))
    pb = int(y.get("power_bomb_tank_ammo", DEFAULT_POWER_BOMB_TANK_AMMO))
    ept = int(y.get("energy_per_tank", DEFAULT_ENERGY_PER_TANK))
    part = max(1, ept // 4)

    if item_name == "Missile Tank":
        _set_resource_qty(out["resources"], "ITEM_WEAPON_MISSILE_MAX", missile)
        out["caption"] = f"Missile Tank acquired.\nMissile capacity increased by {missile}."
    elif item_name == "Missile+ Tank":
        _set_resource_qty(out["resources"], "ITEM_WEAPON_MISSILE_MAX", missile_plus)
        out["caption"] = f"Missile+ Tank acquired.\nMissile capacity increased by {missile_plus}."
    elif item_name == "Power Bomb Tank":
        _set_resource_qty(out["resources"], "ITEM_WEAPON_POWER_BOMB_MAX", pb)
        out["caption"] = f"Power Bomb Tank acquired.\nPower Bomb capacity increased by {pb}."
    elif item_name == "Energy Tank":
        _set_resource_qty(out["resources"], "ITEM_MAX_LIFE", ept)
        out["caption"] = f"Energy Tank acquired.\nEnergy capacity increased by {ept}."
    elif item_name == "Energy Part":
        # ODR still grants ITEM_LIFE_SHARDS qty 1; caption reflects ept/4 when immediate.
        out["caption"] = f"Energy Part acquired.\nEnergy capacity increased by {part}."
    return out


# Map AP item names → Dread item IDs and models
DREAD_ITEM_MAPPING = {
    # Energy
    "Energy Tank": {
        "resources": [{"item_id": "ITEM_MAX_LIFE", "quantity": 100}],
        "model": "item_energytank",
        "icon": "item_energytank",
        "caption": "Energy Tank acquired.\nEnergy capacity increased by 100."
    },
    "Energy Part": {
        "resources": [{"item_id": "ITEM_LIFE_SHARDS", "quantity": 1}],
        "model": "item_energyfragment",
        "icon": "item_energyfragment",
        "caption": "Energy Part acquired.\nEnergy capacity increased by 25."
    },
    
    # Missiles
    "Missile Tank": {
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 2}],
        "model": "item_missiletank",
        "icon": "item_missiletank",
        "caption": "Missile Tank acquired.\nMissile capacity increased by 2."
    },
    "Missile+ Tank": {
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 10}],
        "model": "item_multimisilletank",
        "icon": "item_multimisilletank",
        "caption": "Missile+ Tank acquired.\nMissile capacity increased by 10."
    },
    
    # Power Bombs
    "Power Bomb Tank": {
        "resources": [{"item_id": "ITEM_WEAPON_POWER_BOMB_MAX", "quantity": 1}],
        "model": "item_powerbombtank",
        "icon": "item_powerbombtank",
        "caption": "Power Bomb Tank acquired.\nPower Bomb capacity increased by 1."
    },
    
    # Beams
    "Wide Beam": {
        "resources": [{"item_id": "ITEM_WEAPON_WIDE_BEAM", "quantity": 1}],
        "model": "powerup_widebeam",
        "icon": "powerup_widebeam",
        "caption": "Wide Beam acquired."
    },
    "Plasma Beam": {
        "resources": [{"item_id": "ITEM_WEAPON_PLASMA_BEAM", "quantity": 1}],
        "model": "powerup_plasmabeam",
        "icon": "powerup_plasmabeam",
        "caption": "Plasma Beam acquired."
    },
    "Wave Beam": {
        "resources": [{"item_id": "ITEM_WEAPON_WAVE_BEAM", "quantity": 1}],
        "model": "powerup_wavebeam",
        "icon": "powerup_wavebeam",
        "caption": "Wave Beam acquired."
    },
    
    # Charge variants
    "Charge Beam": {
        "resources": [{"item_id": "ITEM_WEAPON_CHARGE_BEAM", "quantity": 1}],
        "model": "powerup_chargebeam",
        "icon": "powerup_chargebeam",
        "caption": "Charge Beam acquired."
    },
    "Diffusion Beam": {
        "resources": [{"item_id": "ITEM_WEAPON_DIFFUSION_BEAM", "quantity": 1}],
        "model": "powerup_diffusionbeam",
        "icon": "powerup_diffusionbeam",
        "caption": "Diffusion Beam acquired."
    },
    
    # Missiles special
    "Ice Missile": {
        "resources": [{"item_id": "ITEM_WEAPON_ICE_MISSILE", "quantity": 1}],
        "model": "powerup_icemissile",
        "icon": "powerup_icemissile",
        "caption": "Ice Missile acquired."
    },
    "Storm Missile": {
        "resources": [{"item_id": "ITEM_MULTILOCKON", "quantity": 1}],
        "model": "powerup_stormmissile",
        "icon": "powerup_stormmissile",
        "caption": "Storm Missile acquired."
    },
    "Super Missile": {
        "resources": [{"item_id": "ITEM_WEAPON_SUPER_MISSILE", "quantity": 1}],
        "model": "powerup_supermissile",
        "icon": "powerup_supermissile",
        "caption": "Super Missile acquired."
    },
    
    # Suits
    "Varia Suit": {
        "resources": [{"item_id": "ITEM_VARIA_SUIT", "quantity": 1}],
        "model": "powerup_variasuit",
        "icon": "powerup_variasuit",
        "caption": "Varia Suit acquired."
    },
    "Gravity Suit": {
        "resources": [{"item_id": "ITEM_GRAVITY_SUIT", "quantity": 1}],
        "model": "powerup_gravitysuit",
        "icon": "powerup_gravitysuit",
        "caption": "Gravity Suit acquired."
    },
    
    # Movement
    "Morph Ball": {
        "resources": [{"item_id": "ITEM_MORPH_BALL", "quantity": 1}],
        "model": "powerup_morphball",
        "icon": "powerup_morphball",
        "caption": "Morph Ball acquired."
    },
    "Spider Magnet": {
        "resources": [{"item_id": "ITEM_MAGNET_GLOVE", "quantity": 1}],
        "model": "powerup_magnet",
        "icon": "powerup_magnet",
        "caption": "Spider Magnet acquired."
    },
    "Speed Booster": {
        "resources": [{"item_id": "ITEM_SPEED_BOOSTER", "quantity": 1}],
        "model": "powerup_speedbooster",
        "icon": "powerup_speedbooster",
        "caption": "Speed Booster acquired."
    },
    "Speed Booster Upgrade": {
        # ODR: ITEM_UPGRADE_SPEED_BOOST_CHARGE (reduces charge time by 0.25s each).
        "resources": [{"item_id": "ITEM_UPGRADE_SPEED_BOOST_CHARGE", "quantity": 1}],
        "model": "item_speedboostupgrade",
        "icon": "item_speedboostupgrade",
        "caption": "Speed Booster Upgrade acquired."
    },
    "Spin Boost": {
        "resources": [{"item_id": "ITEM_DOUBLE_JUMP", "quantity": 1}],
        "model": "powerup_doublejump",
        "icon": "powerup_doublejump",
        "caption": "Spin Boost acquired."
    },
    "Space Jump": {
        "resources": [{"item_id": "ITEM_SPACE_JUMP", "quantity": 1}],
        "model": "powerup_spacejump",
        "icon": "powerup_spacejump",
        "caption": "Space Jump acquired."
    },
    "Screw Attack": {
        "resources": [{"item_id": "ITEM_SCREW_ATTACK", "quantity": 1}],
        "model": "powerup_screwattack",
        "icon": "powerup_screwattack",
        "caption": "Screw Attack acquired."
    },
    
    # Bombs
    "Bomb": {
        "resources": [{"item_id": "ITEM_WEAPON_BOMB", "quantity": 1}],
        "model": "powerup_bomb",
        "icon": "powerup_bomb",
        "caption": "Bomb acquired."
    },
    "Cross Bomb": {
        "resources": [{"item_id": "ITEM_WEAPON_LINE_BOMB", "quantity": 1}],
        "model": "powerup_crossbomb",
        "icon": "powerup_crossbomb",
        "caption": "Cross Bomb acquired."
    },
    "Power Bomb": {
        # Randovania starter/default: MainPB + included_ammo [2] → MAX capacity +2
        # (not vanilla endgame 3). IncreaseAmmo also fills CURRENT from MAX.
        "resources": [
            {"item_id": "ITEM_WEAPON_POWER_BOMB", "quantity": 1},
            {"item_id": "ITEM_WEAPON_POWER_BOMB_MAX", "quantity": 2},
        ],
        "model": "powerup_powerbomb",
        "icon": "powerup_powerbomb",
        "caption": "Power Bomb acquired.\nPower Bomb capacity increased by 2."
    },
    
    # Visors/Abilities
    "Phantom Cloak": {
        "resources": [{"item_id": "ITEM_OPTIC_CAMOUFLAGE", "quantity": 1}],
        "model": "powerup_phantom",
        "icon": "powerup_phantom",
        "caption": "Phantom Cloak acquired."
    },
    "Flash Shift": {
        # Vanilla / main item: Ghost Aura + included_ammo chains (default 2 = RDV/ODR).
        # Patcher may rewrite chain quantity from flash_shift_included_ammo.
        "resources": [
            {"item_id": "ITEM_GHOST_AURA", "quantity": 1},
            {"item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "quantity": 2},
        ],
        "model": "powerup_ghostaura",
        "icon": "powerup_ghostaura",
        "caption": "Flash Shift acquired."
    },
    "Flash Shift Upgrade": {
        # Chains only. Progressive unlock of Ghost Aura (when Require Main is off)
        # is handled by RandomizerFlashShiftUpgrade / AP IncreaseItemAmount hook.
        # Flash uses = 1 + chain_count once the ability is owned.
        "resources": [{"item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "quantity": 1}],
        "model": "item_flashshiftupgrade",
        "icon": "item_flashshiftupgrade",
        "caption": "Flash Shift Upgrade acquired."
    },
    "Slide": {
        # open-dread-rando schema: ITEM_FLOOR_SLIDE (not ITEM_SPECIAL_SLIDE)
        "resources": [{"item_id": "ITEM_FLOOR_SLIDE", "quantity": 1}],
        "model": "powerup_slide",
        "icon": "powerup_slide",
        "caption": "Slide acquired."
    },
    "Missile Launcher": {
        # No ITEM_* for launcher itself — granting missile capacity unlocks use
        # (same as Randovania starting Missiles / ITEM_WEAPON_MISSILE_MAX).
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 15}],
        "model": "powerup_missilelauncher",
        "icon": "powerup_missilelauncher",
        "caption": "Missile Launcher acquired."
    },
    "Missiles": {
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 15}],
        "model": "powerup_missilelauncher",
        "icon": "powerup_missilelauncher",
        "caption": "Missile Launcher acquired."
    },
    "Pulse Radar": {
        "resources": [{"item_id": "ITEM_SONAR", "quantity": 1}],
        "model": "powerup_sonar",
        "icon": "powerup_sonar",
        "caption": "Pulse Radar acquired."
    },
    "Grapple Beam": {
        "resources": [{"item_id": "ITEM_WEAPON_GRAPPLE_BEAM", "quantity": 1}],
        "model": "powerup_grapple",
        "icon": "powerup_grapple",
        "caption": "Grapple Beam acquired."
    },
    
    # Progressive items — multi-stage resources (matches ODR patcher / Randovania remote pickup)
    "Progressive Charge Beam": {
        "resources": [
            [{"item_id": "ITEM_WEAPON_CHARGE_BEAM", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_DIFFUSION_BEAM", "quantity": 1}],
        ],
        "model": "powerup_chargebeam",
        "icon": "powerup_chargebeam",
        "caption": "Progressive Charge Beam acquired."
    },
    "Progressive Suit": {
        "resources": [
            [{"item_id": "ITEM_VARIA_SUIT", "quantity": 1}],
            [{"item_id": "ITEM_GRAVITY_SUIT", "quantity": 1}],
        ],
        "model": "powerup_variasuit",
        "icon": "powerup_variasuit",
        "caption": "Progressive Suit acquired."
    },
    "Progressive Beam": {
        "resources": [
            [{"item_id": "ITEM_WEAPON_WIDE_BEAM", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_PLASMA_BEAM", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_WAVE_BEAM", "quantity": 1}],
        ],
        "model": "powerup_widebeam",
        "icon": "powerup_widebeam",
        "caption": "Wide Beam acquired."
    },
    "Progressive Missile": {
        "resources": [
            [{"item_id": "ITEM_WEAPON_SUPER_MISSILE", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_ICE_MISSILE", "quantity": 1}],
        ],
        "model": "powerup_supermissile",
        "icon": "powerup_supermissile",
        "caption": "Super Missile acquired."
    },
    "Progressive Missiles": {
        "resources": [
            [{"item_id": "ITEM_WEAPON_SUPER_MISSILE", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_ICE_MISSILE", "quantity": 1}],
        ],
        "model": "powerup_supermissile",
        "icon": "powerup_supermissile",
        "caption": "Super Missile acquired."
    },
    "Progressive Bomb": {
        "resources": [
            [{"item_id": "ITEM_WEAPON_BOMB", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_LINE_BOMB", "quantity": 1}],
        ],
        "model": "powerup_bomb",
        "icon": "powerup_bomb",
        "caption": "Bomb acquired."
    },
    "Progressive Bombs": {  # Plural variant
        "resources": [
            [{"item_id": "ITEM_WEAPON_BOMB", "quantity": 1}],
            [{"item_id": "ITEM_WEAPON_LINE_BOMB", "quantity": 1}],
        ],
        "model": "powerup_bomb",
        "icon": "powerup_bomb",
        "caption": "Bomb acquired."
    },
    "Progressive Spin": {
        "resources": [
            [{"item_id": "ITEM_DOUBLE_JUMP", "quantity": 1}],
            [{"item_id": "ITEM_SPACE_JUMP", "quantity": 1}],
        ],
        "model": "powerup_doublejump",
        "icon": "powerup_doublejump",
        "caption": "Progressive Spin acquired."
    },
}

# Default starting location (vanilla Dread start)
DEFAULT_STARTING_LOCATION = {
    "scenario": "s010_cave",  # Artaria
    "actor": "PRP_CV_SaveStation001_WeightPlate"  # First save station in Artaria
}

# Default starting items (empty - vanilla start)
DEFAULT_STARTING_ITEMS = {}

def normalize_resource_progression(resources) -> list:
    """
    Normalize item resources to ODR progression shape: list of stages, each stage a list of grants.

    Flat single-stage mappings ``[{item_id, quantity}, ...]`` are wrapped as one stage.
    """
    if not resources:
        return []
    if isinstance(resources[0], dict):
        return [list(resources)]
    return [list(stage) for stage in resources]


def get_dread_item_data(item_name: str):
    """Get Dread item data for an AP item name."""
    return DREAD_ITEM_MAPPING.get(item_name)


def get_resource_progression(item_name: str):
    """Return normalized multi-stage progression for an AP item name, or None."""
    data = get_dread_item_data(item_name)
    if not data or not data.get("resources"):
        return None
    return normalize_resource_progression(data["resources"])

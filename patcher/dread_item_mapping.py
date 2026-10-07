"""Dread Item Mappings for Archipelago"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping, Optional

# Use the tank amounts from Options.py and RDV defaults.
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
    """Copy *item_data* and apply YAML ammo / energy-per-tank yields."""
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
        # Grant one ITEM_ENERGY_TANKS item and let IncreaseEnergy add health.
        _set_resource_qty(out["resources"], "ITEM_ENERGY_TANKS", 1)
        out["caption"] = f"Energy Tank acquired.\nEnergy capacity increased by {ept}."
    elif item_name == "Energy Part":
        # Grant one life shard; show the right energy amount for immediate parts.
        out["caption"] = f"Energy Part acquired.\nEnergy capacity increased by {part}."
    return out


# Map AP items to Dread item IDs and models.
DREAD_ITEM_MAPPING = {
    # Energy items.
    "Energy Tank": {
        "resources": [{"item_id": "ITEM_ENERGY_TANKS", "quantity": 1}],
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
    
    # Missile items.
    "Missile Tank": {
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 2}],
        "model": "item_missiletank",
        "icon": "item_missiletank",
        "caption": "Missile Tank acquired.\nMissile capacity increased by 2."
    },
    "Missile+ Tank": {
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 10}],
        "model": "item_missiletankplus",
        "icon": "item_missiletankplus",
        "caption": "Missile+ Tank acquired.\nMissile capacity increased by 10."
    },
    
    # Power Bomb items.
    "Power Bomb Tank": {
        "resources": [{"item_id": "ITEM_WEAPON_POWER_BOMB_MAX", "quantity": 1}],
        "model": "item_powerbombtank",
        "icon": "item_powerbombtank",
        "caption": "Power Bomb Tank acquired.\nPower Bomb capacity increased by 1."
    },
    
    # Beam items.
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
    
    # Charge Beam stages.
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
    
    # Special missile items.
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
    
    # Suit items.
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
    
    # Movement abilities.
    "Morph Ball": {
        "resources": [{"item_id": "ITEM_MORPH_BALL", "quantity": 1}],
        "model": "powerup_morphball",
        "icon": "powerup_morphball",
        "caption": "Morph Ball acquired."
    },
    "Spider Magnet": {
        "resources": [{"item_id": "ITEM_MAGNET_GLOVE", "quantity": 1}],
        "model": "powerup_spidermagnet",
        "icon": "powerup_spidermagnet",
        "caption": "Spider Magnet acquired."
    },
    "Speed Booster": {
        "resources": [{"item_id": "ITEM_SPEED_BOOSTER", "quantity": 1}],
        "model": "powerup_speedbooster",
        "icon": "powerup_speedbooster",
        "caption": "Speed Booster acquired."
    },
    "Speed Booster Upgrade": {
        # Each Speed Booster charge upgrade removes 0.25 seconds.
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
    
    # Bomb items.
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
        # The main Power Bomb item includes two starting shots by default.
        "resources": [
            {"item_id": "ITEM_WEAPON_POWER_BOMB", "quantity": 1},
            {"item_id": "ITEM_WEAPON_POWER_BOMB_MAX", "quantity": 2},
        ],
        "model": "powerup_powerbomb",
        "icon": "powerup_powerbomb",
        "caption": "Power Bomb acquired.\nPower Bomb capacity increased by 2."
    },
    
    # Visor and ability items.
    "Phantom Cloak": {
        "resources": [{"item_id": "ITEM_OPTIC_CAMOUFLAGE", "quantity": 1}],
        "model": "powerup_opticcamo",
        "icon": "powerup_opticcamo",
        "caption": "Phantom Cloak acquired."
    },
    "Flash Shift": {
        # The main Flash Shift item gives Ghost Aura and two chains by default.
        "resources": [
            {"item_id": "ITEM_GHOST_AURA", "quantity": 1},
            {"item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "quantity": 2},
        ],
        "model": "powerup_ghostaura",
        "icon": "powerup_ghostaura",
        "caption": "Flash Shift acquired."
    },
    "Flash Shift Upgrade": {
        # Grant chains here; progressive logic unlocks Ghost Aura when needed.
        "resources": [{"item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "quantity": 1}],
        "model": "item_flashshiftupgrade",
        "icon": "item_flashshiftupgrade",
        "caption": "Flash Shift Upgrade acquired."
    },
    "Slide": {
        # Use ITEM_FLOOR_SLIDE, not the unsupported ITEM_SPECIAL_SLIDE.
        "resources": [{"item_id": "ITEM_FLOOR_SLIDE", "quantity": 1}],
        "model": "powerup_slide",
        "icon": "powerup_slide",
        "caption": "Slide acquired."
    },
    "Missile Launcher": {
        # Missile capacity unlocks the launcher; there is no separate launcher item ID.
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 15}],
        "model": "powerup_missile",
        "icon": "powerup_missile",
        "caption": "Missile Launcher acquired."
    },
    "Missiles": {
        "resources": [{"item_id": "ITEM_WEAPON_MISSILE_MAX", "quantity": 15}],
        "model": "powerup_missile",
        "icon": "powerup_missile",
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
        "model": "powerup_grapplebeam",
        "icon": "powerup_grapplebeam",
        "caption": "Grapple Beam acquired."
    },
    
    # Grant progressive items in stages, like ODR and RDV.
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
    "Progressive Bombs": {  # Also accept the plural name.
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

# Use Dread's normal start by default.
DEFAULT_STARTING_LOCATION = {
    "scenario": "s010_cave",  # Artaria starting locations.
    "actor": "PRP_CV_SaveStation001_WeightPlate"  # Use the first Artaria Save Station.
}

# Start with no extra items by default.
DEFAULT_STARTING_ITEMS = {}

def normalize_resource_progression(resources) -> list:
    """Normalize item resources to ODR progression shape: list of stages, each stage a list of grants."""
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

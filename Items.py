"""Metroid Bread items for Archipelago"""

from BaseClasses import Item, ItemClassification
from typing import Dict, NamedTuple, Optional


class ItemData(NamedTuple):
    id: int
    classification: ItemClassification
    count: int = 1


class MetroidBreadItem(Item):
    game: str = "Metroid Bread"


# Use 84000 as the base item ID to avoid other worlds' IDs.
base_id = 84000

# Main progression items.
item_table: Dict[str, ItemData] = {
    # Beam items.
    "Wide Beam": ItemData(base_id + 0, ItemClassification.progression),
    "Plasma Beam": ItemData(base_id + 1, ItemClassification.progression),
    "Wave Beam": ItemData(base_id + 2, ItemClassification.progression),
    "Progressive Beam": ItemData(base_id + 3, ItemClassification.progression, 3),
    "Charge Beam": ItemData(base_id + 4, ItemClassification.progression),
    "Diffusion Beam": ItemData(base_id + 5, ItemClassification.progression),
    "Progressive Charge Beam": ItemData(base_id + 6, ItemClassification.progression, 2),
    "Grapple Beam": ItemData(base_id + 7, ItemClassification.progression),
    
    # Missile items.
    "Missile Launcher": ItemData(base_id + 10, ItemClassification.progression),
    "Super Missile": ItemData(base_id + 11, ItemClassification.progression),
    "Ice Missile": ItemData(base_id + 12, ItemClassification.progression),
    "Progressive Missiles": ItemData(base_id + 13, ItemClassification.progression, 2),
    "Storm Missile": ItemData(base_id + 14, ItemClassification.progression),
    
    # Weapons gained from EMMIs.
    "Omega Cannon": ItemData(base_id + 15, ItemClassification.progression),
    "Omega Stream Beam": ItemData(base_id + 16, ItemClassification.progression),
    
    # Aeion ability items.
    "Phantom Cloak": ItemData(base_id + 20, ItemClassification.progression),
    # Main Flash Shift item, or its progressive alias when upgrades unlock it.
    "Flash Shift": ItemData(base_id + 21, ItemClassification.progression),
    "Pulse Radar": ItemData(base_id + 22, ItemClassification.progression),
    
    # Suit items.
    "Varia Suit": ItemData(base_id + 30, ItemClassification.progression),
    "Gravity Suit": ItemData(base_id + 31, ItemClassification.progression),
    "Progressive Suit": ItemData(base_id + 32, ItemClassification.progression, 2),
    
    # Morph Ball ability items.
    "Morph Ball": ItemData(base_id + 40, ItemClassification.progression),
    "Bomb": ItemData(base_id + 41, ItemClassification.progression),
    "Cross Bomb": ItemData(base_id + 42, ItemClassification.progression),
    "Progressive Bombs": ItemData(base_id + 43, ItemClassification.progression, 2),
    "Power Bomb": ItemData(base_id + 44, ItemClassification.progression),
    
    # Movement ability items.
    "Slide": ItemData(base_id + 50, ItemClassification.progression),
    "Spider Magnet": ItemData(base_id + 51, ItemClassification.progression),
    "Speed Booster": ItemData(base_id + 52, ItemClassification.progression),
    "Spin Boost": ItemData(base_id + 53, ItemClassification.progression),
    "Space Jump": ItemData(base_id + 54, ItemClassification.progression),
    "Progressive Spin": ItemData(base_id + 55, ItemClassification.progression, 2),
    "Screw Attack": ItemData(base_id + 56, ItemClassification.progression),
    
    # Energy upgrade items.
    "Energy Tank": ItemData(base_id + 60, ItemClassification.useful, 8),
    "Energy Part": ItemData(base_id + 61, ItemClassification.useful, 16),
    
    # Speed Booster upgrade item.
    "Speed Booster Upgrade": ItemData(base_id + 70, ItemClassification.useful, 4),
    
    # Ammo capacity items.
    "Missile Tank": ItemData(base_id + 100, ItemClassification.filler, 35),
    "Missile+ Tank": ItemData(base_id + 101, ItemClassification.useful, 10),
    "Power Bomb Tank": ItemData(base_id + 102, ItemClassification.filler, 12),
    # Flash Shift Upgrades add chain ammo, like Missile Tanks add missiles.
    "Flash Shift Upgrade": ItemData(base_id + 103, ItemClassification.filler, 5),
    
    # DNA artifact items.
    "Metroid DNA": ItemData(base_id + 200, ItemClassification.progression_skip_balancing, 12),
    
    # Victory event item.
    "Raven Beak Defeated": ItemData(None, ItemClassification.progression),
}

# Add fixed RDV story events outside the shuffled item pool.
try:
    from .Events import event_item_table
    item_table.update(event_item_table)
except ImportError:
    pass

# Item groups players can refer to in settings.
item_name_groups: Dict[str, set[str]] = {
    "Beams": {
        "Wide Beam", "Plasma Beam", "Wave Beam", "Progressive Beam",
        "Charge Beam", "Diffusion Beam", "Progressive Charge Beam", "Grapple Beam",
        "Omega Cannon", "Omega Stream Beam"
    },
    "Missiles": {
        "Missile Launcher", "Super Missile", "Ice Missile", "Progressive Missiles", "Storm Missile",
        "Missile Tank", "Missile+ Tank"
    },
    "Aeion": {
        "Phantom Cloak", "Flash Shift Upgrade", "Pulse Radar", "Flash Shift"
    },
    "Suits": {
        "Varia Suit", "Gravity Suit", "Progressive Suit"
    },
    "Morph Ball": {
        "Morph Ball", "Bomb", "Cross Bomb", "Progressive Bombs", "Power Bomb", "Power Bomb Tank"
    },
    "Movement": {
        "Slide", "Spider Magnet", "Speed Booster", "Spin Boost", "Space Jump",
        "Progressive Spin", "Screw Attack", "Speed Booster Upgrade"
    },
    "Energy": {
        "Energy Tank", "Energy Part"
    },
    "Expansions": {
        "Missile Tank", "Missile+ Tank", "Power Bomb Tank", "Flash Shift Upgrade",
    },
    # !hint DNA or !hint Metroid DNA finds the next unchecked DNA location.
    "DNA": {
        "Metroid DNA",
    },
    "Metroid DNA": {
        "Metroid DNA",
    },
    "Events": set(),  # Fill this from the event item table when available.
}

try:
    from .Events import event_item_table
    item_name_groups["Events"] = set(event_item_table.keys())
except ImportError:
    pass

# Find item names by ID.
lookup_id_to_name: Dict[int, str] = {data.id: item_name for item_name, data in item_table.items()}

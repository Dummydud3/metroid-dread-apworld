# Map Hollow Knight items to Metroid Bread items.

HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP = {
    
    "Abyss_Shriek": "Energy Tank",          # Final spell upgrade.
    "Isma's_Tear": "Progressive Suit",      # Use Gravity Suit for acid swimming.
    "Crystal_Heart": "Speed Booster",       # Long dash ability.
    "Monomon": "Energy Tank",               # Dreamer boss key.
    "Void_Heart": "Progressive Suit",       # Final charm upgrade.
    "King_Fragment": "Energy Tank",          # Parts of King's Brand.
    "Queen_Fragment": "Energy Tank",         # Parts of White Fragment.
    
    
    
    
    "Greenpath_Stag": "Energy Part",
    "Queen's_Station_Stag": "Energy Part",
    "City_Storerooms_Stag": "Energy Part",
    "Hidden_Station_Stag": "Energy Part",
    "Distant_Village_Stag": "Energy Part",
    
    
    "City_Crest": "Missile+ Tank",           # Unlock City of Tears.
    "Love_Key": "Missile+ Tank",             # Unlock Tower of Love.
    "Shopkeeper's_Key": "Missile+ Tank",     # Unlock the Elegant Key door.
    "Tram_Pass": "Missile+ Tank",            # Unlock trams.
    "Simple_Key": "Missile+ Tank",           # Open the eight locked doors.
    
    
    "Mask_Shard": "Energy Part",             # Four pieces give one health upgrade.
    "Vessel_Fragment": "Energy Part",        # Three pieces give one soul vessel upgrade.
    "Lifeblood_Cocoon_Large": "Energy Part", # Give temporary health.
    
    
    "Charm_Notch": "Power Bomb Tank",        # Increase charm capacity.
    
    
    "Sharp_Shadow": "Missile+ Tank",         # Deal damage while dashing.
    "Dashmaster": "Missile+ Tank",           # Improve the dash.
    "Soul_Eater": "Missile+ Tank",           # Gain more soul.
    "Spell_Twister": "Missile+ Tank",        # Reduce spell cost.
    "Dream_Wielder": "Missile+ Tank",        # Gain more dream essence.
    "Longnail": "Missile+ Tank",             # Increase reach.
    
    
    "Thorns_of_Agony": "Missile Tank",       # Deal damage on a hit.
    "Fury_of_the_Fallen": "Missile Tank",    # Increase damage at low health.
    "Steady_Body": "Missile Tank",           # Prevent knockback.
    "Defender's_Crest": "Missile Tank",      # Create a dung cloud.
    "Dreamshield": "Missile Tank",           # Add a shield that circles the player.
    "Fragile_Heart": "Missile Tank",         # Add temporary health.
    "Fragile_Greed": "Missile Tank",         # Gain more geo.
    
    
    "Dream_Gate": "Power Bomb Tank",         # Unlock warping.
    "Godtuner": "Power Bomb Tank",           # Unlock Godhome.
    
    
    "Grimmchild2": "Progressive Charge Beam", # Upgrade the charm.
    
    
    "Wanderer's_Journal": "Missile Tank",    # Common story collectible.
    "Hallownest_Seal": "Missile Tank",       # Uncommon story collectible.
    "King's_Idol": "Missile Tank",           # Rare story collectible.
    "Arcane_Egg": "Missile Tank",            # Very rare story collectible.
    "Rancid_Egg": "Missile Tank",            # Money for shops.
    "Pale_Ore": "Missile Tank",              # Material for upgrades.
    
    
    "_default": "Missile Tank",
}


def map_hk_item_to_dread(hk_item_name):
    """Map a Hollow Knight item name to an equivalent Metroid Bread item."""
    # Use the exact item mapping.
    if hk_item_name in HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP:
        return HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP[hk_item_name]
    
    # Use the default item if no mapping exists.
    return HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP["_default"]


# Valid Metroid Bread items for reference.
VALID_DREAD_ITEMS = [
    "Energy Part",
    "Energy Tank",
    "Ice Missile",
    "Missile Tank",
    "Missile+ Tank",
    "Morph Ball",
    "Power Bomb",
    "Power Bomb Tank",
    "Progressive Charge Beam",
    "Progressive Spin",
    "Progressive Suit",
    "Screw Attack",
    "Super Missile",
]

# Hollow Knight → Metroid Bread Item Mapping
# 
# This mapping translates Hollow Knight items to equivalent Metroid Bread items
# for Randovania .rdvgame file generation. The mapping is based on item function,
# progression importance, and rarity.

HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP = {
    # ============================================================================
    # MAJOR PROGRESSION ITEMS (map to Energy Tanks - rare, important)
    # ============================================================================
    "Abyss_Shriek": "Energy Tank",          # Ultimate spell upgrade
    "Isma's_Tear": "Progressive Suit",      # Swim in acid = Gravity Suit
    "Crystal_Heart": "Speed Booster",       # Super dash ability
    "Monomon": "Energy Tank",               # Dreamer (major boss key)
    "Void_Heart": "Progressive Suit",       # Ultimate charm, endgame
    "King_Fragment": "Energy Tank",          # King's Brand pieces
    "Queen_Fragment": "Energy Tank",         # White Fragment pieces
    
    # ============================================================================
    # MOVEMENT/TRAVERSAL (map to movement items)
    # ============================================================================
    # Note: Major movement like Mantis Claw, Mothwing Cloak, Monarch Wings
    # should already be in our AP item mapping, these are duplicates/extras
    
    # ============================================================================
    # STAG STATIONS (map to Energy Parts - useful but not critical)
    # ============================================================================
    "Greenpath_Stag": "Energy Part",
    "Queen's_Station_Stag": "Energy Part",
    "City_Storerooms_Stag": "Energy Part",
    "Hidden_Station_Stag": "Energy Part",
    "Distant_Village_Stag": "Energy Part",
    
    # ============================================================================
    # KEYS AND PASSES (map to Missile+ Tanks - rare, unlock new areas)
    # ============================================================================
    "City_Crest": "Missile+ Tank",           # Opens City of Tears
    "Love_Key": "Missile+ Tank",             # Opens Tower of Love
    "Shopkeeper's_Key": "Missile+ Tank",     # Opens Elegant Key door
    "Tram_Pass": "Missile+ Tank",            # Opens tram system
    "Simple_Key": "Missile+ Tank",           # Opens locked doors (8 in game)
    
    # ============================================================================
    # HEALTH UPGRADES (map to Energy Parts)
    # ============================================================================
    "Mask_Shard": "Energy Part",             # 4 = 1 health upgrade
    "Vessel_Fragment": "Energy Part",        # 3 = 1 soul vessel upgrade
    "Lifeblood_Cocoon_Large": "Energy Part", # Temporary health
    
    # ============================================================================
    # CHARM NOTCHES (map to Power Bomb Tanks - expand capacity)
    # ============================================================================
    "Charm_Notch": "Power Bomb Tank",        # Increases charm capacity
    
    # ============================================================================
    # POWERFUL CHARMS (map to Missile+ Tanks)
    # ============================================================================
    "Sharp_Shadow": "Missile+ Tank",         # Damage on dash
    "Dashmaster": "Missile+ Tank",           # Better dash
    "Soul_Eater": "Missile+ Tank",           # More soul
    "Spell_Twister": "Missile+ Tank",        # Cheaper spells
    "Dream_Wielder": "Missile+ Tank",        # More dream essence
    "Longnail": "Missile+ Tank",             # Extended range
    
    # ============================================================================
    # UTILITY CHARMS (map to Missile Tanks)
    # ============================================================================
    "Thorns_of_Agony": "Missile Tank",       # Damage on hit
    "Fury_of_the_Fallen": "Missile Tank",    # Damage when low health
    "Steady_Body": "Missile Tank",           # No knockback
    "Defender's_Crest": "Missile Tank",      # Dung cloud
    "Dreamshield": "Missile Tank",           # Orbiting shield
    "Fragile_Heart": "Missile Tank",         # Temporary health boost
    "Fragile_Greed": "Missile Tank",         # More geo
    
    # ============================================================================
    # DREAM ABILITIES (map to Power Bomb Tanks - rare, powerful)
    # ============================================================================
    "Dream_Gate": "Power Bomb Tank",         # Warp ability
    "Godtuner": "Power Bomb Tank",           # Access to Godhome
    
    # ============================================================================
    # GRIMMCHILD UPGRADES (map to Progressive items)
    # ============================================================================
    "Grimmchild2": "Progressive Charge Beam", # Charm upgrade
    
    # ============================================================================
    # LORE ITEMS / COLLECTIBLES (map to Missile Tanks - common filler)
    # ============================================================================
    "Wanderer's_Journal": "Missile Tank",    # Lore item (common)
    "Hallownest_Seal": "Missile Tank",       # Lore item (uncommon)
    "King's_Idol": "Missile Tank",           # Lore item (rare)
    "Arcane_Egg": "Missile Tank",            # Lore item (very rare)
    "Rancid_Egg": "Missile Tank",            # Shop currency
    "Pale_Ore": "Missile Tank",              # Upgrade material
    
    # ============================================================================
    # DEFAULT FALLBACK
    # ============================================================================
    # Any HK item not explicitly mapped will use this
    "_default": "Missile Tank",
}


def map_hk_item_to_dread(hk_item_name):
    """
    Map a Hollow Knight item name to an equivalent Metroid Bread item.
    
    Args:
        hk_item_name: The Hollow Knight item name (e.g., "Rancid_Egg")
    
    Returns:
        A valid Metroid Bread item name
    """
    # Direct mapping
    if hk_item_name in HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP:
        return HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP[hk_item_name]
    
    # Fallback to default
    return HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP["_default"]


# For reference: Valid Metroid Bread items
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

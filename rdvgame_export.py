#!/usr/bin/env python3
"""
Convert an Archipelago Metroid Bread spoiler.txt into a Randovania .rdvgame file.

Features
--------
• Parses AP spoiler (not JSON)
• Matches template locations by region/area/pickup name
• Replaces pickups correctly (NOT by order)
• Counts items and updates rdvgame config automatically
• Handles unique upgrades (only one allowed)
• Supports multiworld: detects items from other players/games
• Optional debug logging
"""

import argparse
import json
import re
import sys
import os
import zipfile
import tempfile
from pathlib import Path
from collections import defaultdict

# Import HK item mapping
try:
    from .hk_item_mapping import map_hk_item_to_dread, HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP
except ImportError:
    # Fallback if running as script
    try:
        from hk_item_mapping import map_hk_item_to_dread, HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP
    except ImportError:
        # If mapping file doesn't exist, use simple fallback
        def map_hk_item_to_dread(item_name):
            return "Missile Tank"
        HOLLOW_KNIGHT_TO_DREAD_ITEM_MAP = {"_default": "Missile Tank"}


# -----------------------------
# Pickup Index Mapping (from Randovania's database)
# -----------------------------
# Complete location name mapping: AP location -> (Randovania name, index)
# These indices are immutable and come from Randovania's logic database.
# Each pickup location has a specific PickupIndex that must match exactly.
# Generated from actual Randovania multiworld file - all 149 locations verified.

AP_TO_RANDOVANIA_LOCATION_MAP = {
    "Artaria/Arbitrary Enky Room/Pickup (Missile Tank)": ("Artaria/Arbitrary Enky Room/Pickup (Missile Tank)", 1),
    "Artaria/Central Unit Access/Pickup (Spider Magnet)": ("Artaria/Central Unit Access/Pickup (Spider Magnet)", 139),
    "Artaria/Charge Beam Access/Pickup (Missile Tank)": ("Artaria/Charge Beam Access/Pickup (Missile Tank)", 29),
    "Artaria/Charge Beam Room/Pickup (Charge Beam)": ("Artaria/Charge Beam Room/Pickup (Charge Beam)", 0),
    "Artaria/Charge Tutorial/Pickup (Energy Tank)": ("Artaria/Charge Tutorial/Pickup (Energy Tank)", 3),
    "Artaria/Corpius Arena/Pickup (Phantom Cloak)": ("Artaria/Corpius Arena/Pickup (Phantom Cloak)", 138),
    "Artaria/David Jaffe Room/Pickup (Missile Tank)": ("Artaria/David Jaffe Room/Pickup (Missile Tank)", 9),
    "Artaria/EMMI Zone Exit North/Pickup (Missile Tank)": ("Artaria/EMMI Zone Exit North/Pickup (Missile Tank)", 17),
    "Artaria/EMMI Zone Exit Northwest/Pickup (Missile Tank)": ("Artaria/EMMI Zone Exit Northwest/Pickup (Missile Tank)", 21),
    "Artaria/EMMI Zone First Entrance/Pickup (Missile Tank)": ("Artaria/EMMI Zone First Entrance/Pickup (Missile Tank)", 4),
    "Artaria/EMMI Zone Hub/Pickup (Power Bomb Tank)": ("Artaria/EMMI Zone Hub/Pickup (Power Bomb Tank)", 19),
    "Artaria/EMMI Zone Spinner/Pickup (Missile Tank)": ("Artaria/EMMI Zone Spinner/Pickup (Missile Tank)", 5),
    "Artaria/East Lava Missile Room/Pickup (Missile Tank)": ("Artaria/East Lava Missile Room/Pickup (Missile Tank)", 11),
    "Artaria/Energy Recharge Station South/Pickup (Missile Tank)": ("Artaria/Energy Recharge Station South/Pickup (Missile Tank)", 22),
    "Artaria/Freezer/Pickup (Missile Tank)": ("Artaria/Freezer/Pickup (Missile Tank)", 28),
    "Artaria/Grapple Beam Room/Pickup (Grapple Beam)": ("Artaria/Grapple Beam Room/Pickup (Grapple Beam)", 25),
    "Artaria/Hot Cataris Shortcut/Pickup (Missile Tank)": ("Artaria/Hot Cataris Shortcut/Pickup (Missile Tank)", 2),
    "Artaria/Invisible Corpius Room/Pickup (Missile Tank)": ("Artaria/Invisible Corpius Room/Pickup (Missile Tank)", 6),
    "Artaria/Melee Tutorial Room/Pickup (Missile Tank 1)": ("Artaria/Melee Tutorial Room/Pickup (Missile Tank 1)", 12),
    "Artaria/Melee Tutorial Room/Pickup (Missile Tank 2)": ("Artaria/Melee Tutorial Room/Pickup (Missile Tank 2)", 31),
    "Artaria/Proto EMMI Introduction/Pickup (Missile Tank)": ("Artaria/Proto EMMI Introduction/Pickup (Missile Tank)", 13),
    "Artaria/Screw Attack Room/Pickup (Missile Tank, Top)": ("Artaria/Screw Attack Room/Pickup (Missile Tank, Top)", 24),
    "Artaria/Screw Attack Room/Pickup (Missile Tank, Underwater)": ("Artaria/Screw Attack Room/Pickup (Missile Tank, Underwater)", 26),
    "Artaria/Screw Attack Room/Pickup (Screw Attack)": ("Artaria/Screw Attack Room/Pickup (Screw Attack)", 27),
    "Artaria/Shutter Platform Puzzle/Pickup (Energy Tank)": ("Artaria/Shutter Platform Puzzle/Pickup (Energy Tank)", 14),
    "Artaria/Speed Hallway/Pickup (Energy Part)": ("Artaria/Speed Hallway/Pickup (Energy Part)", 18),
    "Artaria/Speed Hallway/Pickup (Missile+ Tank)": ("Artaria/Speed Hallway/Pickup (Missile+ Tank)", 15),
    "Artaria/Teleport to Cataris/Pickup (Missile Tank, Supers-locked)": ("Artaria/Teleport to Cataris/Pickup (Missile Tank, Supers-locked)", 20),
    "Artaria/Teleport to Cataris/Pickup (Missile Tank, Underwater)": ("Artaria/Teleport to Cataris/Pickup (Missile Tank, Underwater)", 8),
    "Artaria/Thermal Device/Pickup (Missile Tank)": ("Artaria/Thermal Device/Pickup (Missile Tank)", 10),
    "Artaria/Transport to Burenia/Pickup (Missile Tank)": ("Artaria/Transport to Burenia/Pickup (Missile Tank)", 32),
    "Artaria/Varia Suit Room/Pickup (Varia Suit)": ("Artaria/Varia Suit Room/Pickup (Varia Suit)", 23),
    "Artaria/Varia Suit Tutorial North/Pickup (Missile+ Tank)": ("Artaria/Varia Suit Tutorial North/Pickup (Missile+ Tank)", 30),
    "Artaria/Waterfall/Pickup (Energy Part)": ("Artaria/Waterfall/Pickup (Energy Part)", 16),
    "Artaria/Waterfall/Pickup (Missile Tank)": ("Artaria/Waterfall/Pickup (Missile Tank)", 7),
    "Burenia/Burenia Hub to Dairon/Pickup (Energy Part)": ("Burenia/Burenia Hub to Dairon/Pickup (Energy Part)", 90),
    "Burenia/Burenia Hub to Dairon/Pickup (Missile Tank)": ("Burenia/Burenia Hub to Dairon/Pickup (Missile Tank)", 81),
    "Burenia/Drogyga Arena/Pickup (Drogyga)": ("Burenia/Drogyga Arena/Pickup (Drogyga)", 140),
    "Burenia/Early Gravity Speedboost Room 1/Pickup (Energy Part)": ("Burenia/Early Gravity Speedboost Room 1/Pickup (Energy Part)", 86),
    "Burenia/Early Gravity Speedboost Room 1/Pickup (Missile+ Tank)": ("Burenia/Early Gravity Speedboost Room 1/Pickup (Missile+ Tank)", 87),
    "Burenia/Energy Recharge South/Pickup (Missile Tank)": ("Burenia/Energy Recharge South/Pickup (Missile Tank)", 77),
    "Burenia/Flash Shift Room/Pickup (Flash Shift)": ("Burenia/Flash Shift Room/Pickup (Flash Shift)", 78),
    "Burenia/Gravity Suit Room/Pickup (Gravity Suit)": ("Burenia/Gravity Suit Room/Pickup (Gravity Suit)", 79),
    "Burenia/Gravity Suit Room/Pickup (Power Bomb Tank)": ("Burenia/Gravity Suit Room/Pickup (Power Bomb Tank)", 85),
    "Burenia/Gravity Suit Tower/Pickup (Missile Tank)": ("Burenia/Gravity Suit Tower/Pickup (Missile Tank)", 93),
    "Burenia/Gravity Suit Tower/Pickup (Missile+ Tank)": ("Burenia/Gravity Suit Tower/Pickup (Missile+ Tank)", 88),
    "Burenia/Main Hub Tower Middle/Pickup (Missile Tank)": ("Burenia/Main Hub Tower Middle/Pickup (Missile Tank)", 94),
    "Burenia/Main Hub Tower Middle/Pickup (Missile+ Tank)": ("Burenia/Main Hub Tower Middle/Pickup (Missile+ Tank)", 89),
    "Burenia/Main Hub Tower Top/Pickup (Energy Tank)": ("Burenia/Main Hub Tower Top/Pickup (Energy Tank)", 82),
    "Burenia/Main Hub Tower Top/Pickup (Missile Tank)": ("Burenia/Main Hub Tower Top/Pickup (Missile Tank)", 84),
    "Burenia/Storm Missile Gate Room/Pickup (Energy Tank)": ("Burenia/Storm Missile Gate Room/Pickup (Energy Tank)", 95),
    "Burenia/Teleport to Ferenia/Pickup (Missile+ Tank)": ("Burenia/Teleport to Ferenia/Pickup (Missile+ Tank)", 91),
    "Burenia/Transport to Artaria/Pickup (Missile Tank)": ("Burenia/Transport to Artaria/Pickup (Missile Tank)", 83),
    "Burenia/Underneath Drogyga/Pickup (Missile Tank)": ("Burenia/Underneath Drogyga/Pickup (Missile Tank)", 80),
    "Burenia/Upper Burenia Hub/Pickup (Missile Tank)": ("Burenia/Upper Burenia Hub/Pickup (Missile Tank)", 92),
    "Cataris/Above Z-57 Fight/Pickup (Missile Tank)": ("Cataris/Above Z-57 Fight/Pickup (Missile Tank)", 37),
    "Cataris/Above Z-57 Fight/Pickup (Z-57)": ("Cataris/Above Z-57 Fight/Pickup (Z-57)", 141),
    "Cataris/Central Unit Access/Pickup (Morph Ball)": ("Cataris/Central Unit Access/Pickup (Morph Ball)", 144),
    "Cataris/Dairon Transport Access/Pickup (Missile Tank)": ("Cataris/Dairon Transport Access/Pickup (Missile Tank)", 54),
    "Cataris/Diffusion Beam Room/Pickup (Diffusion Beam)": ("Cataris/Diffusion Beam Room/Pickup (Diffusion Beam)", 35),
    "Cataris/Diffusion Beam Room/Pickup (Power Bomb Tank)": ("Cataris/Diffusion Beam Room/Pickup (Power Bomb Tank)", 51),
    "Cataris/Double Obsydomithon Room/Pickup (Missile Tank)": ("Cataris/Double Obsydomithon Room/Pickup (Missile Tank)", 43),
    "Cataris/EMMI Zone Exits West/Pickup (Missile Tank)": ("Cataris/EMMI Zone Exits West/Pickup (Missile Tank)", 40),
    "Cataris/EMMI Zone Hidden Missile Room/Pickup (Missile Tank)": ("Cataris/EMMI Zone Hidden Missile Room/Pickup (Missile Tank)", 47),
    "Cataris/EMMI Zone Item Tunnel/Pickup (Power Bomb Tank)": ("Cataris/EMMI Zone Item Tunnel/Pickup (Power Bomb Tank)", 33),
    "Cataris/Kraid Arena/Pickup (Kraid)": ("Cataris/Kraid Arena/Pickup (Kraid)", 148),
    "Cataris/Kraid Eyedoor Room/Pickup (Missile Tank)": ("Cataris/Kraid Eyedoor Room/Pickup (Missile Tank)", 34),
    "Cataris/Lava Button East Access/Pickup (Missile Tank)": ("Cataris/Lava Button East Access/Pickup (Missile Tank)", 46),
    "Cataris/Teleport to Artaria (Blue)/Pickup (Missile Tank)": ("Cataris/Teleport to Artaria (Blue)/Pickup (Missile Tank)", 45),
    "Cataris/Teleport to Artaria (Blue)/Pickup (Power Bomb Tank)": ("Cataris/Teleport to Artaria (Blue)/Pickup (Power Bomb Tank)", 48),
    "Cataris/Teleport to Artaria (Red)/Pickup (Missile+ Tank)": ("Cataris/Teleport to Artaria (Red)/Pickup (Missile+ Tank)", 50),
    "Cataris/Teleport to Dairon/Pickup (Missile Tank)": ("Cataris/Teleport to Dairon/Pickup (Missile Tank)", 39),
    "Cataris/Teleport to Ghavoran/Pickup (Missile Tank - Bottom)": ("Cataris/Teleport to Ghavoran/Pickup (Missile Tank - Bottom)", 53),
    "Cataris/Teleport to Ghavoran/Pickup (Missile Tank - Top)": ("Cataris/Teleport to Ghavoran/Pickup (Missile Tank - Top)", 41),
    "Cataris/Thermal Device Room North/Pickup (Energy Part)": ("Cataris/Thermal Device Room North/Pickup (Energy Part)", 42),
    "Cataris/Thermal Device Room North/Pickup (Energy Tank)": ("Cataris/Thermal Device Room North/Pickup (Energy Tank)", 49),
    "Cataris/Transport to Artaria/Pickup (Missile Tank)": ("Cataris/Transport to Artaria/Pickup (Missile Tank)", 36),
    "Cataris/Underlava Puzzle Room 2/Pickup (Energy Part)": ("Cataris/Underlava Puzzle Room 2/Pickup (Energy Part)", 44),
    "Cataris/Z-57 Heat Room East/Pickup (Missile Tank)": ("Cataris/Z-57 Heat Room East/Pickup (Missile Tank)", 52),
    "Cataris/Z-57 Heat Room West (Right)/Pickup (Missile Tank)": ("Cataris/Z-57 Heat Room West (Right)/Pickup (Missile Tank)", 38),
    "Dairon/Big Hub/Pickup (Missile Tank)": ("Dairon/Big Hub/Pickup (Missile Tank)", 59),
    "Dairon/Bomb Room/Pickup (Bomb)": ("Dairon/Bomb Room/Pickup (Bomb)", 58),
    "Dairon/Bomb Room/Pickup (Missile Tank)": ("Dairon/Bomb Room/Pickup (Missile Tank)", 62),
    "Dairon/Central Unit Access/Pickup (Energy Part)": ("Dairon/Central Unit Access/Pickup (Energy Part)", 72),
    "Dairon/Central Unit Access/Pickup (Speed Booster)": ("Dairon/Central Unit Access/Pickup (Speed Booster)", 147),
    "Dairon/Cross Bomb Puzzle Room/Pickup (Missile Tank)": ("Dairon/Cross Bomb Puzzle Room/Pickup (Missile Tank)", 75),
    "Dairon/EMMI Zone Exit North/Pickup (Power Bomb Tank)": ("Dairon/EMMI Zone Exit North/Pickup (Power Bomb Tank)", 73),
    "Dairon/EMMI Zone Exit Northwest/Pickup (Missile Tank)": ("Dairon/EMMI Zone Exit Northwest/Pickup (Missile Tank)", 66),
    "Dairon/Early Grapple Access/Pickup (Energy Part)": ("Dairon/Early Grapple Access/Pickup (Energy Part)", 64),
    "Dairon/Early Grapple Room/Pickup (Missile Tank Speedboost)": ("Dairon/Early Grapple Room/Pickup (Missile Tank Speedboost)", 55),
    "Dairon/Early Grapple Room/Pickup (Missile Tank Tunnel)": ("Dairon/Early Grapple Room/Pickup (Missile Tank Tunnel)", 56),
    "Dairon/Energy Recharge Station West/Pickup (Energy Part)": ("Dairon/Energy Recharge Station West/Pickup (Energy Part)", 70),
    "Dairon/Freezer/Pickup (Missile Tank - Lower)": ("Dairon/Freezer/Pickup (Missile Tank - Lower)", 67),
    "Dairon/Freezer/Pickup (Missile Tank - Upper)": ("Dairon/Freezer/Pickup (Missile Tank - Upper)", 76),
    "Dairon/Hidden Grapple Shortcut Room/Pickup (Missile Tank)": ("Dairon/Hidden Grapple Shortcut Room/Pickup (Missile Tank)", 74),
    "Dairon/Lake Puzzle Room/Pickup (Power Bomb Tank)": ("Dairon/Lake Puzzle Room/Pickup (Power Bomb Tank)", 65),
    "Dairon/Save Station West Tunnels/Pickup (Missile Tank)": ("Dairon/Save Station West Tunnels/Pickup (Missile Tank)", 69),
    "Dairon/Shinespark Tutorial/Pickup (Energy Tank)": ("Dairon/Shinespark Tutorial/Pickup (Energy Tank)", 71),
    "Dairon/Storm Missile Gate Room/Pickup (Missile+ Tank)": ("Dairon/Storm Missile Gate Room/Pickup (Missile+ Tank)", 68),
    "Dairon/Teleport to Artaria/Pickup (Missile Tank)": ("Dairon/Teleport to Artaria/Pickup (Missile Tank)", 60),
    "Dairon/Transport to Artaria/Pickup (Power Bomb Tank)": ("Dairon/Transport to Artaria/Pickup (Power Bomb Tank)", 61),
    "Dairon/Wide Beam Room/Pickup (Wide Beam)": ("Dairon/Wide Beam Room/Pickup (Wide Beam)", 57),
    "Dairon/Yellow EMMI Introduction/Pickup (Energy Part)": ("Dairon/Yellow EMMI Introduction/Pickup (Energy Part)", 63),
    "Elun/Ammo Recharge Station/Pickup (Energy Tank)": ("Elun/Ammo Recharge Station/Pickup (Energy Tank)", 114),
    "Elun/Fan Room/Pickup (Missile Tank)": ("Elun/Fan Room/Pickup (Missile Tank)", 117),
    "Elun/Horizontal Bomb Maze/Pickup (Missile Tank)": ("Elun/Horizontal Bomb Maze/Pickup (Missile Tank)", 118),
    "Elun/Plasma Beam Room/Pickup (Plasma Beam)": ("Elun/Plasma Beam Room/Pickup (Plasma Beam)", 115),
    "Elun/Vertical Bomb Maze/Pickup (Power Bomb Tank)": ("Elun/Vertical Bomb Maze/Pickup (Power Bomb Tank)", 116),
    "Ferenia/Cold Room (Storm Missile Gate)/Pickup (Missile Tank)": ("Ferenia/Cold Room (Storm Missile Gate)/Pickup (Missile Tank)", 125),
    "Ferenia/Energy Recharge Station Secret/Pickup (Energy Part)": ("Ferenia/Energy Recharge Station Secret/Pickup (Energy Part)", 124),
    "Ferenia/Escue Arena/Pickup (Storm Missile)": ("Ferenia/Escue Arena/Pickup (Storm Missile)", 142),
    "Ferenia/Escue Eyedoor Room/Pickup (Missile Tank)": ("Ferenia/Escue Eyedoor Room/Pickup (Missile Tank)", 122),
    "Ferenia/Fan Room/Pickup (Missile+ Tank)": ("Ferenia/Fan Room/Pickup (Missile+ Tank)", 128),
    "Ferenia/Path to Escue/Pickup (Energy Part)": ("Ferenia/Path to Escue/Pickup (Energy Part)", 133),
    "Ferenia/Pitfall Puzzle Room/Pickup (Missile Tank)": ("Ferenia/Pitfall Puzzle Room/Pickup (Missile Tank)", 121),
    "Ferenia/Purple EMMI Arena/Pickup (Wave Beam)": ("Ferenia/Purple EMMI Arena/Pickup (Wave Beam)", 143),
    "Ferenia/Purple EMMI Introduction/Pickup (Power Bomb Tank)": ("Ferenia/Purple EMMI Introduction/Pickup (Power Bomb Tank)", 127),
    "Ferenia/Separate Tunnels Room/Pickup (Missile Tank - Left)": ("Ferenia/Separate Tunnels Room/Pickup (Missile Tank - Left)", 120),
    "Ferenia/Separate Tunnels Room/Pickup (Missile Tank - Right)": ("Ferenia/Separate Tunnels Room/Pickup (Missile Tank - Right)", 132),
    "Ferenia/Space Jump Room/Pickup (Missile Tank)": ("Ferenia/Space Jump Room/Pickup (Missile Tank)", 129),
    "Ferenia/Space Jump Room/Pickup (Missile+ Tank)": ("Ferenia/Space Jump Room/Pickup (Missile+ Tank)", 130),
    "Ferenia/Space Jump Room/Pickup (Space Jump)": ("Ferenia/Space Jump Room/Pickup (Space Jump)", 119),
    "Ferenia/Speedboost Slopes Maze/Pickup (Energy Part)": ("Ferenia/Speedboost Slopes Maze/Pickup (Energy Part)", 131),
    "Ferenia/Total Recharge Station/Pickup (Energy Part)": ("Ferenia/Total Recharge Station/Pickup (Energy Part)", 123),
    "Ferenia/Twin Robot Arena/Pickup (Power Bomb Tank)": ("Ferenia/Twin Robot Arena/Pickup (Power Bomb Tank)", 126),
    "Ghavoran/Above Pulse Radar/Pickup (Missile Tank)": ("Ghavoran/Above Pulse Radar/Pickup (Missile Tank)", 106),
    "Ghavoran/Central Unit Access/Pickup (Ice Missile)": ("Ghavoran/Central Unit Access/Pickup (Ice Missile)", 146),
    "Ghavoran/Cross Bomb Tutorial/Pickup (Missile Tank)": ("Ghavoran/Cross Bomb Tutorial/Pickup (Missile Tank)", 98),
    "Ghavoran/Dairon Transport Access/Pickup (Missile Tank)": ("Ghavoran/Dairon Transport Access/Pickup (Missile Tank)", 99),
    "Ghavoran/Elun Transport Access/Pickup (Missile Tank)": ("Ghavoran/Elun Transport Access/Pickup (Missile Tank)", 111),
    "Ghavoran/Golzuna Arena/Pickup (Cross Bomb)": ("Ghavoran/Golzuna Arena/Pickup (Cross Bomb)", 145),
    "Ghavoran/Golzuna Tower/Pickup (Energy Part)": ("Ghavoran/Golzuna Tower/Pickup (Energy Part)", 112),
    "Ghavoran/Golzuna Tower/Pickup (Missile Tank)": ("Ghavoran/Golzuna Tower/Pickup (Missile Tank)", 113),
    "Ghavoran/Left Entrance/Pickup (Missile Tank)": ("Ghavoran/Left Entrance/Pickup (Missile Tank)", 108),
    "Ghavoran/Map Station Access Secret/Pickup (Missile Tank)": ("Ghavoran/Map Station Access Secret/Pickup (Missile Tank)", 101),
    "Ghavoran/Pulse Radar Room/Pickup (Pulse Radar)": ("Ghavoran/Pulse Radar Room/Pickup (Pulse Radar)", 110),
    "Ghavoran/Right Entrance/Pickup (Missile Tank)": ("Ghavoran/Right Entrance/Pickup (Missile Tank)", 97),
    "Ghavoran/Spin Boost Room/Pickup (Spin Boost)": ("Ghavoran/Spin Boost Room/Pickup (Spin Boost)", 104),
    "Ghavoran/Spin Boost Tower/Pickup (Energy Part)": ("Ghavoran/Spin Boost Tower/Pickup (Energy Part)", 105),
    "Ghavoran/Spin Boost Tower/Pickup (Energy Tank)": ("Ghavoran/Spin Boost Tower/Pickup (Energy Tank)", 109),
    "Ghavoran/Spin Boost Tower/Pickup (Power Bomb Tank)": ("Ghavoran/Spin Boost Tower/Pickup (Power Bomb Tank)", 96),
    "Ghavoran/Super Missile Room Access/Pickup (Missile+ Tank)": ("Ghavoran/Super Missile Room Access/Pickup (Missile+ Tank)", 102),
    "Ghavoran/Super Missile Room/Pickup (Super Missile)": ("Ghavoran/Super Missile Room/Pickup (Super Missile)", 100),
    "Ghavoran/Teleport to Burenia/Pickup (Missile Tank)": ("Ghavoran/Teleport to Burenia/Pickup (Missile Tank)", 103),
    "Ghavoran/Total Recharge Station North/Pickup (Missile Tank)": ("Ghavoran/Total Recharge Station North/Pickup (Missile Tank)", 107),
    "Hanubia/Ferenia Shortcut/Pickup (Missile Tank)": ("Hanubia/Ferenia Shortcut/Pickup (Missile Tank)", 136),
    "Hanubia/Orange EMMI Introduction/Pickup (Power Bomb)": ("Hanubia/Orange EMMI Introduction/Pickup (Power Bomb)", 137),
    "Hanubia/Speedboost Puzzle Room/Pickup (Power Bomb Tank)": ("Hanubia/Speedboost Puzzle Room/Pickup (Power Bomb Tank)", 135),
    "Hanubia/Total Recharge Station North/Pickup (Missile Tank)": ("Hanubia/Total Recharge Station North/Pickup (Missile Tank)", 134),
}


# -----------------------------
# Utilities
# -----------------------------

def debug(msg, enabled):
    if enabled:
        print("[debug]", msg)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# -----------------------------
# Item name mapping (AP -> Randovania)
# -----------------------------

AP_TO_RANDOVANIA_ITEMS = {
    # Missiles - "Missile Launcher" doesn't exist in Dread, missiles are always available
    # Map to Missile Tank instead
    "Missile Launcher": "Missile Tank",
    
    # Progressive items - these should match Randovania
    "Progressive Beam": "Progressive Beam",
    "Progressive Charge Beam": "Progressive Charge Beam", 
    "Progressive Bomb": "Progressive Bomb",
    "Progressive Bombs": "Progressive Bomb",  # Alternate name
    "Progressive Spin": "Progressive Spin",
    "Progressive Suit": "Progressive Suit",
    "Progressive Missiles": "Progressive Missile",  # Note: Randovania uses singular "Missile"
    
    # Beams - most match, but check these
    "Wide Beam": "Wide Beam",
    "Plasma Beam": "Plasma Beam",
    "Wave Beam": "Wave Beam",
    "Charge Beam": "Progressive Charge Beam",  # Charge Beam is progressive in Randovania
    "Diffusion Beam": "Progressive Charge Beam",  # Diffusion is the 2nd charge upgrade
    "Grapple Beam": "Grapple Beam",
    
    # Missiles - these are separate pickups in Randovania, not progressive!
    "Super Missile": "Super Missile",  # Keep as-is
    "Ice Missile": "Ice Missile",      # Keep as-is
    "Storm Missile": "Storm Missile",  # Keep as-is
    
    # Morph Ball items
    "Morph Ball": "Morph Ball",
    "Bomb": "Progressive Bomb",  # Bomb is progressive in Randovania
    "Cross Bomb": "Progressive Bomb",  # Cross Bomb is the 2nd bomb
    "Power Bomb": "Power Bomb",  # This might not exist as pickup, need to check
    
    # Aeion abilities - these might not all be in Randovania
    "Phantom Cloak": "Phantom Cloak",  # Need to verify
    "Flash Shift": "Flash Shift",  # Need to verify
    "Pulse Radar": "Pulse Radar",  # Need to verify
    
    # Suits
    "Varia Suit": "Progressive Suit",  # Varia is progressive
    "Gravity Suit": "Progressive Suit",  # Gravity is the 2nd suit
    
    # Movement items - need to check which are progressive
    "Slide": "Missile Tank",  # Slide is always available, map to filler
    "Spider Magnet": "Spider Magnet",  # Need to verify
    "Speed Booster": "Speed Booster",
    "Spin Boost": "Progressive Spin",  # Spin Boost is progressive
    "Space Jump": "Progressive Spin",  # Space Jump is the 2nd spin
    "Screw Attack": "Screw Attack",  # Need to verify
    
    # EMMI weapons - these probably don't exist in Randovania
    "Omega Cannon": "Energy Tank",  # Fallback to energy tank
    "Omega Stream Beam": "Energy Tank",  # Fallback to energy tank
    
    # Ammo and energy - these should match
    "Missile Tank": "Missile Tank",
    "Missile+ Tank": "Missile+ Tank",
    "Power Bomb Tank": "Power Bomb Tank",
    "Energy Tank": "Energy Tank",
    "Energy Part": "Energy Part",
    
    # Upgrades - these might not exist
    "Speed Booster Upgrade": "Energy Part",  # Fallback
    "Flash Shift Upgrade": "Energy Part",  # Fallback
    
    # DNA - check if this exists
    "Metroid DNA": "Metroid DNA 2",  # Randovania has numbered DNA
    
    # Victory - skip this, it's an event
    "Raven Beak Defeated": None,  # Don't include in rdvgame
}


def map_ap_item_to_randovania(ap_item_name):
    """Convert AP item name to Randovania item name"""
    mapped = AP_TO_RANDOVANIA_ITEMS.get(ap_item_name, ap_item_name)
    # Skip None items (events)
    return mapped if mapped is not None else None


# -----------------------------
# Spoiler parsing with Multiworld support
# -----------------------------

# Updated regex to capture player information in AP 0.6.7+ format:
# Format: "Region - Area - Node (Player): Item (Player)"
# IMPORTANT: Node can contain parentheses, e.g. "Pickup (Energy Tank)"
# So we need to match everything from last " - " to the LAST "(" before ":"
LOCATION_RE = re.compile(
    r"^(?P<region>.+?) - (?P<area>.+?) - (?P<node>.+) \((?P<location_player>[^)]+)\): (?P<item>.+) \((?P<item_player>[^)]+)\)$"
)


def parse_spoiler(spoiler_path, our_player_name=None, debug_enabled=False):
    """
    Parse AP spoiler with multiworld support.
    
    Args:
        spoiler_path: Path to spoiler.txt
        our_player_name: Our player's name (e.g. "DreadPlayer")
        debug_enabled: Enable debug output
    
    Returns:
        List of (region, area, node, item, player_name, is_ours)
    """
    placements = []
    in_locations_section = False
    line_num = 0

    with open(spoiler_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line_num += 1
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Start parsing when we see "Locations:" header
            if line_stripped == "Locations:":
                in_locations_section = True
                if debug_enabled:
                    debug(f"Line {line_num}: Started Locations section", True)
                continue
            
            # Stop parsing when we hit other sections (Paths, Playthrough, etc.)
            if in_locations_section and line_stripped.endswith(":") and not " - " in line_stripped and not "(" in line_stripped:
                # This is a section header, stop parsing
                if debug_enabled:
                    debug(f"Line {line_num}: Found section header '{line_stripped}', stopping parse", True)
                break
            
            # Only parse if we're in the locations section
            if not in_locations_section:
                continue

            m = LOCATION_RE.match(line_stripped)
            if not m:
                if debug_enabled and in_locations_section and ":" in line_stripped:
                    debug(f"Line {line_num}: Failed regex match: '{line_stripped}'", True)
                continue

            region = m.group("region").strip()
            area = m.group("area").strip()
            node = m.group("node").strip()
            item = m.group("item").strip()
            item_player = m.group("item_player").strip()  # Player who owns the item
            
            # Determine if this item is for us or another player
            is_ours = (item_player == our_player_name) if our_player_name else True
            
            # Map AP item name to Randovania item name
            mapped_item = map_ap_item_to_randovania(item)
            
            # Skip items that don't have a Randovania equivalent (like events)
            if mapped_item is None:
                debug(f"Skipping event item at {region} - {area} - {node}", debug_enabled)
                continue

            placements.append((region, area, node, mapped_item, item_player, is_ours))

    debug(f"Parsed {len(placements)} placements from spoiler.", debug_enabled)

    if debug_enabled:
        for p in placements[:10]:
            debug(f"  {p}", True)

    return placements


# -----------------------------
# Template location mapping (for single-player dict format)
# -----------------------------

def build_template_map(template_data):
    """
    Build mapping for single-player dict format:
    (region, area, node) -> reference to location entry
    """
    locations = template_data["game_modifications"][0]["locations"]
    
    # Check if already multiworld format (list)
    if isinstance(locations, list):
        # Already multiworld, build from list
        mapping = {}
        for loc in locations:
            node_id = loc["node_identifier"]
            key = (node_id["region"], node_id["area"], node_id["node"])
            mapping[key] = loc
        return mapping
    
    # Single-player dict format
    mapping = {}
    for region, area_dict in locations.items():
        for area_key, item in area_dict.items():
            # area_key example: "Charge Tutorial/Pickup (Energy Tank)"
            if "/" not in area_key:
                continue
            area, node = area_key.split("/", 1)
            mapping[(region, area, node)] = (area_dict, area_key)
    
    return mapping


# -----------------------------
# Multiworld detection and conversion
# -----------------------------

def is_multiworld(placements):
    """Check if this is a multiworld seed"""
    for region, area, node, item, player, is_ours in placements:
        if not is_ours:
            return True
    return False


def build_solo_locations(placements, debug_enabled=False):
    """
    Build schema-40 locations list for a *solo* Dread .rdvgame.

    Always uses owner=0 (the only world). Foreign Archipelago items become
    "Nothing" — real cross-game sync stays in the AP client, not Randovania.
    """
    locations = []

    for region, area, node, item, player_name, is_ours in placements:
        location_key = f"{region}/{area}/{node}"
        mapping_result = AP_TO_RANDOVANIA_LOCATION_MAP.get(location_key)

        if mapping_result:
            _randovania_name, index = mapping_result
        else:
            print(f"[ERROR] No mapping found for {location_key}")
            index = 0

        pickup_name = item if is_ours else "Nothing"

        locations.append({
            "node_identifier": {
                "region": region,
                "area": area,
                "node": node,
            },
            "index": index,
            "pickup": pickup_name,
            "owner": 0,
        })

        if debug_enabled and not is_ours:
            debug(
                f"Foreign item: {region}/{area} -> {item} exported as Nothing (owner=0)",
                True,
            )

    return locations


# Back-compat alias (older callers / docs)
def build_multiworld_locations(placements, template_map=None, our_player_slot=1, player_names=None, debug_enabled=False):
    return build_solo_locations(placements, debug_enabled=debug_enabled)


def _extract_dread_world(template_data):
    """
    Return (dread_preset, dread_game_mod) from a template that may contain
    extra placeholder worlds. Prefer an explicit dread entry; fall back to [0].
    """
    presets = template_data.get("info", {}).get("presets") or []
    mods = template_data.get("game_modifications") or []

    dread_preset = None
    for preset in presets:
        if preset.get("game") == "dread":
            dread_preset = preset
            break
    if dread_preset is None and presets:
        dread_preset = presets[0]

    dread_mod = None
    for mod in mods:
        if mod.get("game") == "dread":
            dread_mod = mod
            break
    if dread_mod is None and mods:
        dread_mod = mods[0]

    if dread_preset is None or dread_mod is None:
        raise ValueError("Template has no Dread preset/game_modifications entry")

    return dread_preset, dread_mod


# -----------------------------
# Placement application with Multiworld support
# -----------------------------

def apply_placements(template_data, placements, our_player_slot=1, require_full_match=False, debug_enabled=False):
    """
    Apply item placements to template.
    
    Supports both single-player (dict) and multiworld (list) formats.
    Automatically detects multiworld and uses appropriate format.
    
    Args:
        template_data: The .rdvgame template
        placements: List of (region, area, node, item, player, is_ours)
        our_player_slot: Our AP slot number (1-indexed)
        require_full_match: Require all locations to be matched
        debug_enabled: Enable debug output
    
    Returns:
        (counts, multiworld_items) tuple
    """
    
    # Build template mapping
    template_map = build_template_map(template_data)
    
    # Detect if multiworld
    is_mw = is_multiworld(placements)
    
    # Archipelago multiworld still exports a *solo* Dread .rdvgame.
    # Randovania only allows Export Game from Game Details when world_count == 1
    # (frozen builds). Cross-game sync is handled by MetroidBreadClient, not RDV.
    if is_mw:
        print("[INFO] Archipelago multiworld detected")
        print("[INFO] Exporting solo Dread .rdvgame (foreign items as Nothing)")
        return apply_placements_multiworld(
            template_data,
            placements,
            template_map,
            our_player_slot,
            debug_enabled,
        )
    else:
        print(f"[INFO] Single-player detected - using dict format")
        
        # Use single-player dict format
        return apply_placements_singleplayer(
            template_data,
            placements,
            template_map,
            require_full_match,
            debug_enabled
        )


def apply_placements_singleplayer(template_data, placements, template_map, require_full_match, debug_enabled):
    """Apply placements using single-player dict format."""
    matched = 0
    counts = defaultdict(int)
    
    for region, area, node, item, player_name, is_ours in placements:
        key = (region, area, node)
        
        if key not in template_map:
            if debug_enabled:
                debug(f"[WARNING] Location not in template: {region} - {area} - {node}", True)
            continue
        
        area_dict, area_key = template_map[key]
        area_dict[area_key] = item
        counts[item] += 1
        matched += 1
    
    if require_full_match and matched != len(template_map):
        print("[error] Not all template locations were matched.")
        print(f"        matched: {matched} / template: {len(template_map)}")
        sys.exit(1)
    
    return counts, []


def apply_placements_multiworld(template_data, placements, template_map, our_player_slot, debug_enabled):
    """
    Apply AP multiworld placements into a *solo* Dread .rdvgame.

    Why solo: frozen Randovania disables "Export Game" when world_count > 1
    ("Multiworld games can only be exported from a game session"). Archipelago
    already owns cross-game sync, so placeholder foreign worlds only block export.

    Result:
    - Exactly one dread preset + one dread game_modifications
    - Schema-40 locations list; foreign AP items -> "Nothing", owner=0
    """
    foreign_players = sorted({
        player_name
        for _r, _a, _n, _i, player_name, is_ours in placements
        if player_name and not is_ours
    })
    if foreign_players:
        print(f"[INFO] Foreign AP players (not written into .rdvgame): {', '.join(foreign_players)}")

    dread_preset, dread_mod = _extract_dread_world(template_data)
    locations_list = build_solo_locations(placements, debug_enabled=debug_enabled)

    dread_mod = dict(dread_mod)
    dread_mod["game"] = "dread"
    dread_mod["locations"] = locations_list

    template_data["info"]["presets"] = [dread_preset]
    template_data["game_modifications"] = [dread_mod]
    template_data["schema_version"] = 40
    print("[INFO] Solo Dread layout: 1 preset, 1 game_modifications, schema 40")

    counts = defaultdict(int)
    multiworld_items = []
    for _region, _area, _node, item, player_name, is_ours in placements:
        if is_ours:
            counts[item] += 1
        else:
            multiworld_items.append({"item": item, "player": player_name})

    print(f"[OK] Placed {len(placements)} total locations")
    print(f"     - {sum(counts.values())} Dread items")
    print(f"     - {len(multiworld_items)} foreign items as Nothing")
    print("[INFO] Randovania Game Details -> Export Game should be enabled (world_count=1)")

    if debug_enabled and multiworld_items:
        print("\nForeign items sample (exported as Nothing for Randovania):")
        from collections import Counter
        item_counts = Counter(mi["item"] for mi in multiworld_items)
        for item, count in sorted(item_counts.items())[:10]:
            print(f"  {item}: {count}x")

    return counts, multiworld_items


# -----------------------------
# Config updates
# -----------------------------

UNIQUE_UPGRADES = {
    "Morph Ball",
    "Charge Beam",
    "Wide Beam",
    "Wave Beam",
    "Plasma Beam",
    "Diffusion Beam",
    "Grapple Beam",
    "Super Missile",
    "Ice Missile",
    "Storm Missile",
    "Phantom Cloak",
    "Flash Shift",
    "Pulse Radar",
    "Varia Suit",
    "Gravity Suit",
    "Bomb",
    "Cross Bomb",
    "Power Bomb",
    "Spider Magnet",
    "Speed Booster",
    "Spin Boost",
    "Space Jump",
    "Screw Attack",
}


def update_config_counts(template_data, counts, debug_enabled=False):

    config = template_data["info"]["presets"][0]["configuration"]

    standard = config["standard_pickup_configuration"]["pickups_state"]
    ammo = config["ammo_pickup_configuration"]["pickups_state"]
    
    # FIRST: Zero out all standard pickups to start fresh
    # This prevents double-counting from template + spoiler
    for item_name in list(standard.keys()):
        if "num_shuffled_pickups" in standard[item_name]:
            standard[item_name]["num_shuffled_pickups"] = 0
    
    # Update artifacts configuration based on DNA items
    # If we don't have any Metroid DNA items, set required_artifacts to 0
    # This prevents Randovania from trying to create hints for non-existent DNA items
    dna_count = sum(count for item, count in counts.items() if "Metroid DNA" in item)
    
    # Handle artifacts config safely (might not exist in all templates)
    try:
        if dna_count == 0:
            config["artifacts"]["required_artifacts"] = 0
            debug("artifacts: -> 0 (no DNA items in seed)", debug_enabled)
        else:
            # Set required artifacts to the number of DNA items we actually have
            config["artifacts"]["required_artifacts"] = dna_count
            debug(f"artifacts: -> {dna_count} (DNA items present)", debug_enabled)
    except (KeyError, TypeError) as e:
        debug(f"Warning: Could not update artifacts config: {e}", debug_enabled)
    
    # Special handling for progressive items
    # If we're using Progressive Beam, zero out individual beam counts
    if "Progressive Beam" in counts and counts["Progressive Beam"] > 0:
        for beam in ["Wide Beam", "Plasma Beam", "Wave Beam"]:
            if beam in standard:
                standard[beam]["num_shuffled_pickups"] = 0
                debug(f"standard '{beam}': -> 0 (progressive beam active)", debug_enabled)
    
    # If we're using Progressive Spin, zero out individual spin counts
    if "Progressive Spin" in counts and counts["Progressive Spin"] > 0:
        for spin in ["Spin Boost", "Space Jump"]:
            if spin in standard:
                standard[spin]["num_shuffled_pickups"] = 0
                debug(f"standard '{spin}': -> 0 (progressive spin active)", debug_enabled)
    
    # If we're using Progressive Charge Beam, zero out individual charge counts
    if "Progressive Charge Beam" in counts and counts["Progressive Charge Beam"] > 0:
        for charge in ["Charge Beam", "Diffusion Beam"]:
            if charge in standard:
                standard[charge]["num_shuffled_pickups"] = 0
                debug(f"standard '{charge}': -> 0 (progressive charge active)", debug_enabled)
    
    # If we're using Progressive Suit, zero out individual suit counts
    if "Progressive Suit" in counts and counts["Progressive Suit"] > 0:
        for suit in ["Varia Suit", "Gravity Suit"]:
            if suit in standard:
                standard[suit]["num_shuffled_pickups"] = 0
                debug(f"standard '{suit}': -> 0 (progressive suit active)", debug_enabled)
    
    # If we're using Progressive Bomb, zero out individual bomb counts
    if "Progressive Bomb" in counts and counts["Progressive Bomb"] > 0:
        for bomb in ["Bomb", "Cross Bomb"]:
            if bomb in standard:
                standard[bomb]["num_shuffled_pickups"] = 0
                debug(f"standard '{bomb}': -> 0 (progressive bomb active)", debug_enabled)
    
    # If we're using Progressive Missile, zero out individual missile counts
    if "Progressive Missile" in counts and counts["Progressive Missile"] > 0:
        for missile in ["Super Missile", "Ice Missile", "Storm Missile"]:
            if missile in standard:
                standard[missile]["num_shuffled_pickups"] = 0
                debug(f"standard '{missile}': -> 0 (progressive missile active)", debug_enabled)

    # Update major item counts (these REPLACE template values, not add to them)
    for item, count in counts.items():

        if item in UNIQUE_UPGRADES:
            count = 1

        if item in standard:
            standard[item]["num_shuffled_pickups"] = count
            debug(f"standard '{item}': -> {count}", debug_enabled)

        elif item in ammo:
            ammo[item]["pickup_count"] = count
            debug(f"ammo '{item}': -> {count}", debug_enabled)

        else:
            # handle upgrades missing from config
            standard[item] = {"num_shuffled_pickups": count}
            debug(f"added config entry for '{item}' = {count}", debug_enabled)
    
    # IMPORTANT: Print final consumable counts for verification
    print("\n[OK] Final consumable counts in rdvgame:")
    if "Energy Tank" in counts:
        print(f"  Energy Tank: {counts['Energy Tank']}")
    if "Energy Part" in counts:
        print(f"  Energy Part: {counts['Energy Part']}")
    if "Missile Tank" in counts:
        print(f"  Missile Tank: {counts['Missile Tank']}")
    if "Missile+ Tank" in counts:
        print(f"  Missile+ Tank: {counts['Missile+ Tank']}")
    if "Power Bomb Tank" in counts:
        print(f"  Power Bomb Tank: {counts['Power Bomb Tank']}")


# -----------------------------
# GUI Integration Helper
# -----------------------------

def extract_from_ap_output(ap_output_folder: str, player_name: str, player_slot: int = 1, template_path: str = None, debug_enabled: bool = False):
    """
    Extract data from Archipelago output and create .rdvgame file
    
    Args:
        ap_output_folder: Path to AP's output folder (with .zip file)
        player_name: Name of the player (used to detect multiworld items)
        player_slot: Player's slot number in AP (1-indexed, default 1)
        template_path: Path to template .rdvgame file (optional)
        debug_enabled: Enable debug output
    
    Returns:
        Path to created .rdvgame file, or None on failure
    """
    print(f"Searching for spoiler log in: {ap_output_folder}")
    
    # Check if folder exists
    if not os.path.exists(ap_output_folder):
        print(f"Error: Folder does not exist: {ap_output_folder}")
        return None
    
    # Find the spoiler log or zip file
    spoiler_file = None
    zip_file = None
    
    for file in os.listdir(ap_output_folder):
        if file.endswith('_Spoiler.txt'):
            spoiler_file = os.path.join(ap_output_folder, file)
            print(f"Found spoiler log: {file}")
            break
        elif file.endswith('.zip') and file.startswith('AP_'):
            zip_file = os.path.join(ap_output_folder, file)
            print(f"Found zip file: {file}")
    
    # If no direct spoiler but we have a zip, extract it
    temp_dir = None
    if not spoiler_file and zip_file:
        print(f"No direct spoiler found. Checking inside zip file...")
        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                # List files in zip
                zip_contents = zf.namelist()
                print(f"Files in zip: {zip_contents}")
                
                # Find spoiler file in zip
                spoiler_in_zip = None
                for name in zip_contents:
                    if '_Spoiler.txt' in name:
                        spoiler_in_zip = name
                        break
                
                if spoiler_in_zip:
                    # Extract to temp directory
                    temp_dir = tempfile.mkdtemp()
                    zf.extractall(temp_dir)
                    spoiler_file = os.path.join(temp_dir, spoiler_in_zip)
                    print(f"Extracted spoiler from zip: {spoiler_in_zip}")
                else:
                    print("Error: No spoiler file found in zip")
                    return None
        except Exception as e:
            print(f"Error extracting zip: {e}")
            return None
    
    if not spoiler_file:
        print("Error: No spoiler file found")
        print("Available files:")
        for file in os.listdir(ap_output_folder):
            print(f"  - {file}")
        return None
    
    # Find template file
    if template_path is None:
        # Look for template in the Metroid Bread world directory
        script_dir = Path(__file__).parent
        template_path = script_dir / "dread_template.rdvgame"
        
        if not template_path.exists():
            print(f"Error: Template file not found: {template_path}")
            print("Please provide a template .rdvgame file or create dread_template.rdvgame")
            return None
    
    print(f"Using template: {template_path}")
    
    # Load template
    try:
        template_data = load_json(template_path)
    except Exception as e:
        print(f"Error loading template: {e}")
        return None
    
    # Determine our player name for multiworld detection
    # Use the actual player name from the YAML (e.g., "DreadPlayer")
    our_player_name = player_name
    print(f"Our player: {our_player_name} (slot {player_slot})")
    
    # Parse spoiler
    try:
        placements = parse_spoiler(spoiler_file, our_player_name=our_player_name, debug_enabled=debug_enabled)
        print(f"Parsed {len(placements)} item placements")
    except Exception as e:
        print(f"Error parsing spoiler: {e}")
        return None
    
    # Apply placements
    try:
        counts, multiworld_items = apply_placements(
            template_data, 
            placements, 
            our_player_slot=player_slot,
            require_full_match=False, 
            debug_enabled=debug_enabled
        )
        own_items = sum(counts.values())
        print(f"Applied {own_items} items for our player")
        if multiworld_items:
            print(f"Applied {len(multiworld_items)} items from other players")
    except Exception as e:
        print(f"Error applying placements: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # Update config
    try:
        update_config_counts(template_data, counts, debug_enabled)
    except Exception as e:
        print(f"Error updating config: {e}")
        return None
    
    # Write output
    output_path = os.path.join(ap_output_folder, f"AP_{player_name}_Dread.rdvgame")
    try:
        write_json(output_path, template_data)
        print(f"[OK] Successfully created: {output_path}")
        print_remote_lua_export_reminder()
    except Exception as e:
        print(f"Error writing output: {e}")
        return None
    
    # Cleanup temp directory
    if temp_dir and os.path.exists(temp_dir):
        import shutil
        shutil.rmtree(temp_dir)
    
    return output_path


def print_remote_lua_export_reminder():
    """Remind the user how TCP :6969 gets enabled after Randovania export."""
    print()
    print("=" * 72)
    print("REMOTE LUA / ARCHIPELAGO CLIENT (TCP 6969)")
    print("=" * 72)
    print("This .rdvgame is a solo Dread layout. The listening socket is NOT stored")
    print("in the file — Randovania enables it at Export Game time via:")
    print("  enable_remote_lua = enable_auto_tracker OR multiworld")
    print()
    print("Before Export Game in Randovania:")
    print("  1. Open Dread cosmetic options")
    print("  2. Keep 'Enable automatic item tracker' CHECKED")
    print("     (required for solo AP seeds — otherwise Ryujinx never listens on 6969)")
    print("  3. Export with exlaunch/romfs (Ryujinx tab) so exefs/subsdk9 is installed")
    print()
    print("After export, confirm the mod has:")
    print("  - patcher.json with \"enable_remote_lua\": true")
    print("  - DreadRandovania/exefs/subsdk9")
    print("  - DreadRandovania/romfs/system/scripts/init.lc")
    print()
    print("Then: start Ryujinx + modded Dread, wait for title/boot, then")
    print("  /connect_dread  (and disconnect Randovania's Game Connection first —")
    print("   only one TCP client can hold :6969 at a time)")
    print("Or run:  python verify_dread_remote_connection.py")
    print("=" * 72)


# -----------------------------
# Main (CLI)
# -----------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Convert Archipelago Metroid Bread spoiler to .rdvgame file (with multiworld support)"
    )

    parser.add_argument("--template", help="Path to template .rdvgame file")
    parser.add_argument("--spoiler", help="Path to spoiler.txt file")
    parser.add_argument("--out", help="Output .rdvgame file path")
    parser.add_argument("--player", help="Player name/number (for multiworld detection)", default="Player 1")
    parser.add_argument("--slot", type=int, help="Player slot number (1-indexed, for multiworld)", default=1)
    
    # GUI integration arguments
    parser.add_argument("output_folder", nargs="?", help="AP output folder (GUI mode)")
    parser.add_argument("player_name", nargs="?", help="Player name (GUI mode)")

    parser.add_argument("--require-full-match", action="store_true")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    # GUI mode: called with output_folder and player_name
    if args.output_folder and args.player_name:
        result = extract_from_ap_output(
            args.output_folder,
            args.player_name,
            player_slot=args.slot,
            template_path=args.template,
            debug_enabled=args.debug
        )
        sys.exit(0 if result else 1)
    
    # CLI mode: requires --template, --spoiler, --out
    if not all([args.template, args.spoiler, args.out]):
        print("Error: CLI mode requires --template, --spoiler, and --out")
        print("   or: Provide output_folder and player_name for GUI mode")
        parser.print_help()
        sys.exit(1)

    template_path = Path(args.template)
    spoiler_path = Path(args.spoiler)
    out_path = Path(args.out)

    template_data = load_json(template_path)

    placements = parse_spoiler(spoiler_path, our_player_name=args.player, debug_enabled=args.debug)

    counts, multiworld_items = apply_placements(
        template_data,
        placements,
        our_player_slot=args.slot,
        require_full_match=args.require_full_match,
        debug_enabled=args.debug,
    )

    update_config_counts(template_data, counts, args.debug)

    write_json(out_path, template_data)

    print(f"[convert] Wrote: {out_path}")
    if multiworld_items:
        print(f"[convert] Included {len(multiworld_items)} multiworld items from other players")
    print_remote_lua_export_reminder()


if __name__ == "__main__":
    main()

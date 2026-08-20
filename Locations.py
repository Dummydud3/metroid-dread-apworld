"""
Metroid Bread locations for Archipelago
Extracted from Randovania's logic database
"""

from BaseClasses import Location
from typing import Dict, NamedTuple


class LocationData(NamedTuple):
    id: int
    region: str


class MetroidBreadLocation(Location):
    game: str = "Metroid Bread"


# All 149 pickup locations from Metroid Bread
location_table: Dict[str, LocationData] = {
    "Artaria - Charge Tutorial - Pickup (Energy Tank)": LocationData(84000, "Artaria"),
    "Artaria - Melee Tutorial Room - Pickup (Missile Tank 1)": LocationData(84001, "Artaria"),
    "Artaria - Melee Tutorial Room - Pickup (Missile Tank 2)": LocationData(84002, "Artaria"),
    "Artaria - EMMI Zone First Entrance - Pickup (Missile Tank)": LocationData(84003, "Artaria"),
    "Artaria - EMMI Zone Exit North - Pickup (Missile Tank)": LocationData(84004, "Artaria"),
    "Artaria - EMMI Zone Hub - Pickup (Power Bomb Tank)": LocationData(84005, "Artaria"),
    "Artaria - Teleport to Cataris - Pickup (Missile Tank, Underwater)": LocationData(84006, "Artaria"),
    "Artaria - Teleport to Cataris - Pickup (Missile Tank, Supers-locked)": LocationData(84007, "Artaria"),
    "Artaria - Charge Beam Access - Pickup (Missile Tank)": LocationData(84008, "Artaria"),
    "Artaria - Charge Beam Room - Pickup (Charge Beam)": LocationData(84009, "Artaria"),
    "Artaria - EMMI Zone Spinner - Pickup (Missile Tank)": LocationData(84010, "Artaria"),
    "Artaria - Proto EMMI Introduction - Pickup (Missile Tank)": LocationData(84011, "Artaria"),
    "Artaria - Corpius Arena - Pickup (Phantom Cloak)": LocationData(84012, "Artaria"),
    "Artaria - David Jaffe Room - Pickup (Missile Tank)": LocationData(84013, "Artaria"),
    "Artaria - East Lava Missile Room - Pickup (Missile Tank)": LocationData(84014, "Artaria"),
    "Artaria - Varia Suit Tutorial North - Pickup (Missile+ Tank)": LocationData(84015, "Artaria"),
    "Artaria - Shutter Platform Puzzle - Pickup (Energy Tank)": LocationData(84016, "Artaria"),
    "Artaria - Varia Suit Room - Pickup (Varia Suit)": LocationData(84017, "Artaria"),
    "Artaria - Grapple Beam Room - Pickup (Grapple Beam)": LocationData(84018, "Artaria"),
    "Artaria - Central Unit Access - Pickup (Spider Magnet)": LocationData(84019, "Artaria"),
    "Artaria - Invisible Corpius Room - Pickup (Missile Tank)": LocationData(84020, "Artaria"),
    "Artaria - EMMI Zone Exit Northwest - Pickup (Missile Tank)": LocationData(84021, "Artaria"),
    "Artaria - Energy Recharge Station South - Pickup (Missile Tank)": LocationData(84022, "Artaria"),
    "Artaria - Waterfall - Pickup (Missile Tank)": LocationData(84023, "Artaria"),
    "Artaria - Waterfall - Pickup (Energy Part)": LocationData(84024, "Artaria"),
    "Artaria - Thermal Device - Pickup (Missile Tank)": LocationData(84025, "Artaria"),
    "Artaria - Arbitrary Enky Room - Pickup (Missile Tank)": LocationData(84026, "Artaria"),
    "Artaria - Hot Cataris Shortcut - Pickup (Missile Tank)": LocationData(84027, "Artaria"),
    "Artaria - Transport to Burenia - Pickup (Missile Tank)": LocationData(84028, "Artaria"),
    "Artaria - Screw Attack Room - Pickup (Missile Tank, Top)": LocationData(84029, "Artaria"),
    "Artaria - Screw Attack Room - Pickup (Missile Tank, Underwater)": LocationData(84030, "Artaria"),
    "Artaria - Screw Attack Room - Pickup (Screw Attack)": LocationData(84031, "Artaria"),
    "Artaria - Freezer - Pickup (Missile Tank)": LocationData(84032, "Artaria"),
    "Artaria - Speed Hallway - Pickup (Missile+ Tank)": LocationData(84033, "Artaria"),
    "Artaria - Speed Hallway - Pickup (Energy Part)": LocationData(84034, "Artaria"),
    "Cataris - Transport to Artaria - Pickup (Missile Tank)": LocationData(84035, "Cataris"),
    "Cataris - Above Z-57 Fight - Pickup (Missile Tank)": LocationData(84036, "Cataris"),
    "Cataris - Above Z-57 Fight - Pickup (Z-57)": LocationData(84037, "Cataris"),
    "Cataris - Teleport to Artaria (Blue) - Pickup (Missile Tank)": LocationData(84038, "Cataris"),
    "Cataris - Teleport to Artaria (Blue) - Pickup (Power Bomb Tank)": LocationData(84039, "Cataris"),
    "Cataris - Z-57 Heat Room West (Right) - Pickup (Missile Tank)": LocationData(84040, "Cataris"),
    "Cataris - Teleport to Artaria (Red) - Pickup (Missile+ Tank)": LocationData(84041, "Cataris"),
    "Cataris - Teleport to Ghavoran - Pickup (Missile Tank - Top)": LocationData(84042, "Cataris"),
    "Cataris - Teleport to Ghavoran - Pickup (Missile Tank - Bottom)": LocationData(84043, "Cataris"),
    "Cataris - EMMI Zone Exits West - Pickup (Missile Tank)": LocationData(84044, "Cataris"),
    "Cataris - EMMI Zone Item Tunnel - Pickup (Power Bomb Tank)": LocationData(84045, "Cataris"),
    "Cataris - Central Unit Access - Pickup (Morph Ball)": LocationData(84046, "Cataris"),
    "Cataris - Dairon Transport Access - Pickup (Missile Tank)": LocationData(84047, "Cataris"),
    "Cataris - Thermal Device Room North - Pickup (Energy Part)": LocationData(84048, "Cataris"),
    "Cataris - Thermal Device Room North - Pickup (Energy Tank)": LocationData(84049, "Cataris"),
    "Cataris - Diffusion Beam Room - Pickup (Diffusion Beam)": LocationData(84050, "Cataris"),
    "Cataris - Diffusion Beam Room - Pickup (Power Bomb Tank)": LocationData(84051, "Cataris"),
    "Cataris - Lava Button East Access - Pickup (Missile Tank)": LocationData(84052, "Cataris"),
    "Cataris - Double Obsydomithon Room - Pickup (Missile Tank)": LocationData(84053, "Cataris"),
    "Cataris - Z-57 Heat Room East - Pickup (Missile Tank)": LocationData(84054, "Cataris"),
    "Cataris - Teleport to Dairon - Pickup (Missile Tank)": LocationData(84055, "Cataris"),
    "Cataris - Underlava Puzzle Room 2 - Pickup (Energy Part)": LocationData(84056, "Cataris"),
    "Cataris - EMMI Zone Hidden Missile Room - Pickup (Missile Tank)": LocationData(84057, "Cataris"),
    "Cataris - Kraid Eyedoor Room - Pickup (Missile Tank)": LocationData(84058, "Cataris"),
    "Cataris - Kraid Arena - Pickup (Kraid)": LocationData(84059, "Cataris"),
    "Dairon - Teleport to Artaria - Pickup (Missile Tank)": LocationData(84060, "Dairon"),
    "Dairon - Big Hub - Pickup (Missile Tank)": LocationData(84061, "Dairon"),
    "Dairon - Wide Beam Room - Pickup (Wide Beam)": LocationData(84062, "Dairon"),
    "Dairon - Early Grapple Access - Pickup (Energy Part)": LocationData(84063, "Dairon"),
    "Dairon - Transport to Artaria - Pickup (Power Bomb Tank)": LocationData(84064, "Dairon"),
    "Dairon - Early Grapple Room - Pickup (Missile Tank Speedboost)": LocationData(84065, "Dairon"),
    "Dairon - Early Grapple Room - Pickup (Missile Tank Tunnel)": LocationData(84066, "Dairon"),
    "Dairon - Shinespark Tutorial - Pickup (Energy Tank)": LocationData(84067, "Dairon"),
    "Dairon - EMMI Zone Exit North - Pickup (Power Bomb Tank)": LocationData(84068, "Dairon"),
    "Dairon - Yellow EMMI Introduction - Pickup (Energy Part)": LocationData(84069, "Dairon"),
    "Dairon - Cross Bomb Puzzle Room - Pickup (Missile Tank)": LocationData(84070, "Dairon"),
    "Dairon - Bomb Room - Pickup (Bomb)": LocationData(84071, "Dairon"),
    "Dairon - Bomb Room - Pickup (Missile Tank)": LocationData(84072, "Dairon"),
    "Dairon - Freezer - Pickup (Missile Tank - Lower)": LocationData(84073, "Dairon"),
    "Dairon - Freezer - Pickup (Missile Tank - Upper)": LocationData(84074, "Dairon"),
    "Dairon - EMMI Zone Exit Northwest - Pickup (Missile Tank)": LocationData(84075, "Dairon"),
    "Dairon - Hidden Grapple Shortcut Room - Pickup (Missile Tank)": LocationData(84076, "Dairon"),
    "Dairon - Save Station West Tunnels - Pickup (Missile Tank)": LocationData(84077, "Dairon"),
    "Dairon - Storm Missile Gate Room - Pickup (Missile+ Tank)": LocationData(84078, "Dairon"),
    "Dairon - Lake Puzzle Room - Pickup (Power Bomb Tank)": LocationData(84079, "Dairon"),
    "Dairon - Central Unit Access - Pickup (Energy Part)": LocationData(84080, "Dairon"),
    "Dairon - Central Unit Access - Pickup (Speed Booster)": LocationData(84081, "Dairon"),
    "Dairon - Energy Recharge Station West - Pickup (Energy Part)": LocationData(84082, "Dairon"),
    "Burenia - Upper Burenia Hub - Pickup (Missile Tank)": LocationData(84083, "Burenia"),
    "Burenia - Burenia Hub to Dairon - Pickup (Missile Tank)": LocationData(84084, "Burenia"),
    "Burenia - Burenia Hub to Dairon - Pickup (Energy Part)": LocationData(84085, "Burenia"),
    "Burenia - Underneath Drogyga - Pickup (Missile Tank)": LocationData(84086, "Burenia"),
    "Burenia - Teleport to Ferenia - Pickup (Missile+ Tank)": LocationData(84087, "Burenia"),
    "Burenia - Main Hub Tower Top - Pickup (Energy Tank)": LocationData(84088, "Burenia"),
    "Burenia - Main Hub Tower Top - Pickup (Missile Tank)": LocationData(84089, "Burenia"),
    "Burenia - Main Hub Tower Middle - Pickup (Missile+ Tank)": LocationData(84090, "Burenia"),
    "Burenia - Main Hub Tower Middle - Pickup (Missile Tank)": LocationData(84091, "Burenia"),
    "Burenia - Energy Recharge South - Pickup (Missile Tank)": LocationData(84092, "Burenia"),
    "Burenia - Flash Shift Room - Pickup (Flash Shift)": LocationData(84093, "Burenia"),
    "Burenia - Transport to Artaria - Pickup (Missile Tank)": LocationData(84094, "Burenia"),
    "Burenia - Early Gravity Speedboost Room 1 - Pickup (Energy Part)": LocationData(84095, "Burenia"),
    "Burenia - Early Gravity Speedboost Room 1 - Pickup (Missile+ Tank)": LocationData(84096, "Burenia"),
    "Burenia - Gravity Suit Tower - Pickup (Missile+ Tank)": LocationData(84097, "Burenia"),
    "Burenia - Gravity Suit Tower - Pickup (Missile Tank)": LocationData(84098, "Burenia"),
    "Burenia - Gravity Suit Room - Pickup (Gravity Suit)": LocationData(84099, "Burenia"),
    "Burenia - Gravity Suit Room - Pickup (Power Bomb Tank)": LocationData(84100, "Burenia"),
    "Burenia - Storm Missile Gate Room - Pickup (Energy Tank)": LocationData(84101, "Burenia"),
    "Burenia - Drogyga Arena - Pickup (Drogyga)": LocationData(84102, "Burenia"),
    "Ghavoran - Right Entrance - Pickup (Missile Tank)": LocationData(84103, "Ghavoran"),
    "Ghavoran - Left Entrance - Pickup (Missile Tank)": LocationData(84104, "Ghavoran"),
    "Ghavoran - Dairon Transport Access - Pickup (Missile Tank)": LocationData(84105, "Ghavoran"),
    "Ghavoran - Super Missile Room Access - Pickup (Missile+ Tank)": LocationData(84106, "Ghavoran"),
    "Ghavoran - Super Missile Room - Pickup (Super Missile)": LocationData(84107, "Ghavoran"),
    "Ghavoran - Central Unit Access - Pickup (Ice Missile)": LocationData(84108, "Ghavoran"),
    "Ghavoran - Spin Boost Tower - Pickup (Power Bomb Tank)": LocationData(84109, "Ghavoran"),
    "Ghavoran - Spin Boost Tower - Pickup (Energy Part)": LocationData(84110, "Ghavoran"),
    "Ghavoran - Spin Boost Tower - Pickup (Energy Tank)": LocationData(84111, "Ghavoran"),
    "Ghavoran - Golzuna Tower - Pickup (Energy Part)": LocationData(84112, "Ghavoran"),
    "Ghavoran - Golzuna Tower - Pickup (Missile Tank)": LocationData(84113, "Ghavoran"),
    "Ghavoran - Teleport to Burenia - Pickup (Missile Tank)": LocationData(84114, "Ghavoran"),
    "Ghavoran - Total Recharge Station North - Pickup (Missile Tank)": LocationData(84115, "Ghavoran"),
    "Ghavoran - Golzuna Arena - Pickup (Cross Bomb)": LocationData(84116, "Ghavoran"),
    "Ghavoran - Map Station Access Secret - Pickup (Missile Tank)": LocationData(84117, "Ghavoran"),
    "Ghavoran - Elun Transport Access - Pickup (Missile Tank)": LocationData(84118, "Ghavoran"),
    "Ghavoran - Spin Boost Room - Pickup (Spin Boost)": LocationData(84119, "Ghavoran"),
    "Ghavoran - Pulse Radar Room - Pickup (Pulse Radar)": LocationData(84120, "Ghavoran"),
    "Ghavoran - Cross Bomb Tutorial - Pickup (Missile Tank)": LocationData(84121, "Ghavoran"),
    "Ghavoran - Above Pulse Radar - Pickup (Missile Tank)": LocationData(84122, "Ghavoran"),
    "Ferenia - Total Recharge Station - Pickup (Energy Part)": LocationData(84123, "Ferenia"),
    "Ferenia - Fan Room - Pickup (Missile+ Tank)": LocationData(84124, "Ferenia"),
    "Ferenia - Speedboost Slopes Maze - Pickup (Energy Part)": LocationData(84125, "Ferenia"),
    "Ferenia - Separate Tunnels Room - Pickup (Missile Tank - Left)": LocationData(84126, "Ferenia"),
    "Ferenia - Separate Tunnels Room - Pickup (Missile Tank - Right)": LocationData(84127, "Ferenia"),
    "Ferenia - Space Jump Room - Pickup (Space Jump)": LocationData(84128, "Ferenia"),
    "Ferenia - Space Jump Room - Pickup (Missile Tank)": LocationData(84129, "Ferenia"),
    "Ferenia - Space Jump Room - Pickup (Missile+ Tank)": LocationData(84130, "Ferenia"),
    "Ferenia - Pitfall Puzzle Room - Pickup (Missile Tank)": LocationData(84131, "Ferenia"),
    "Ferenia - Twin Robot Arena - Pickup (Power Bomb Tank)": LocationData(84132, "Ferenia"),
    "Ferenia - Energy Recharge Station Secret - Pickup (Energy Part)": LocationData(84133, "Ferenia"),
    "Ferenia - Path to Escue - Pickup (Energy Part)": LocationData(84134, "Ferenia"),
    "Ferenia - Escue Eyedoor Room - Pickup (Missile Tank)": LocationData(84135, "Ferenia"),
    "Ferenia - Escue Arena - Pickup (Storm Missile)": LocationData(84136, "Ferenia"),
    "Ferenia - Cold Room (Storm Missile Gate) - Pickup (Missile Tank)": LocationData(84137, "Ferenia"),
    "Ferenia - Purple EMMI Arena - Pickup (Wave Beam)": LocationData(84138, "Ferenia"),
    "Ferenia - Purple EMMI Introduction - Pickup (Power Bomb Tank)": LocationData(84139, "Ferenia"),
    "Hanubia - Ferenia Shortcut - Pickup (Missile Tank)": LocationData(84140, "Hanubia"),
    "Hanubia - Total Recharge Station North - Pickup (Missile Tank)": LocationData(84141, "Hanubia"),
    "Hanubia - Speedboost Puzzle Room - Pickup (Power Bomb Tank)": LocationData(84142, "Hanubia"),
    "Hanubia - Orange EMMI Introduction - Pickup (Power Bomb)": LocationData(84143, "Hanubia"),
    "Elun - Ammo Recharge Station - Pickup (Energy Tank)": LocationData(84144, "Elun"),
    "Elun - Plasma Beam Room - Pickup (Plasma Beam)": LocationData(84145, "Elun"),
    "Elun - Fan Room - Pickup (Missile Tank)": LocationData(84146, "Elun"),
    "Elun - Vertical Bomb Maze - Pickup (Power Bomb Tank)": LocationData(84147, "Elun"),
    "Elun - Horizontal Bomb Maze - Pickup (Missile Tank)": LocationData(84148, "Elun"),
}

# Location name groups for player convenience
location_name_groups: Dict[str, set[str]] = {
    "Artaria": {
        "Artaria - Charge Tutorial - Pickup (Energy Tank)",
        "Artaria - Melee Tutorial Room - Pickup (Missile Tank 1)",
        "Artaria - Melee Tutorial Room - Pickup (Missile Tank 2)",
        "Artaria - EMMI Zone First Entrance - Pickup (Missile Tank)",
        "Artaria - EMMI Zone Exit North - Pickup (Missile Tank)",
        "Artaria - EMMI Zone Hub - Pickup (Power Bomb Tank)",
        "Artaria - Teleport to Cataris - Pickup (Missile Tank, Underwater)",
        "Artaria - Teleport to Cataris - Pickup (Missile Tank, Supers-locked)",
        "Artaria - Charge Beam Access - Pickup (Missile Tank)",
        "Artaria - Charge Beam Room - Pickup (Charge Beam)",
        "Artaria - EMMI Zone Spinner - Pickup (Missile Tank)",
        "Artaria - Proto EMMI Introduction - Pickup (Missile Tank)",
        "Artaria - Corpius Arena - Pickup (Phantom Cloak)",
        "Artaria - David Jaffe Room - Pickup (Missile Tank)",
        "Artaria - East Lava Missile Room - Pickup (Missile Tank)",
        "Artaria - Varia Suit Tutorial North - Pickup (Missile+ Tank)",
        "Artaria - Shutter Platform Puzzle - Pickup (Energy Tank)",
        "Artaria - Varia Suit Room - Pickup (Varia Suit)",
        "Artaria - Grapple Beam Room - Pickup (Grapple Beam)",
        "Artaria - Central Unit Access - Pickup (Spider Magnet)",
        "Artaria - Invisible Corpius Room - Pickup (Missile Tank)",
        "Artaria - EMMI Zone Exit Northwest - Pickup (Missile Tank)",
        "Artaria - Energy Recharge Station South - Pickup (Missile Tank)",
        "Artaria - Waterfall - Pickup (Missile Tank)",
        "Artaria - Waterfall - Pickup (Energy Part)",
        "Artaria - Thermal Device - Pickup (Missile Tank)",
        "Artaria - Arbitrary Enky Room - Pickup (Missile Tank)",
        "Artaria - Hot Cataris Shortcut - Pickup (Missile Tank)",
        "Artaria - Transport to Burenia - Pickup (Missile Tank)",
        "Artaria - Screw Attack Room - Pickup (Missile Tank, Top)",
        "Artaria - Screw Attack Room - Pickup (Missile Tank, Underwater)",
        "Artaria - Screw Attack Room - Pickup (Screw Attack)",
        "Artaria - Freezer - Pickup (Missile Tank)",
        "Artaria - Speed Hallway - Pickup (Missile+ Tank)",
        "Artaria - Speed Hallway - Pickup (Energy Part)",
    },
    "Burenia": {
        "Burenia - Upper Burenia Hub - Pickup (Missile Tank)",
        "Burenia - Burenia Hub to Dairon - Pickup (Missile Tank)",
        "Burenia - Burenia Hub to Dairon - Pickup (Energy Part)",
        "Burenia - Underneath Drogyga - Pickup (Missile Tank)",
        "Burenia - Teleport to Ferenia - Pickup (Missile+ Tank)",
        "Burenia - Main Hub Tower Top - Pickup (Energy Tank)",
        "Burenia - Main Hub Tower Top - Pickup (Missile Tank)",
        "Burenia - Main Hub Tower Middle - Pickup (Missile+ Tank)",
        "Burenia - Main Hub Tower Middle - Pickup (Missile Tank)",
        "Burenia - Energy Recharge South - Pickup (Missile Tank)",
        "Burenia - Flash Shift Room - Pickup (Flash Shift)",
        "Burenia - Transport to Artaria - Pickup (Missile Tank)",
        "Burenia - Early Gravity Speedboost Room 1 - Pickup (Energy Part)",
        "Burenia - Early Gravity Speedboost Room 1 - Pickup (Missile+ Tank)",
        "Burenia - Gravity Suit Tower - Pickup (Missile+ Tank)",
        "Burenia - Gravity Suit Tower - Pickup (Missile Tank)",
        "Burenia - Gravity Suit Room - Pickup (Gravity Suit)",
        "Burenia - Gravity Suit Room - Pickup (Power Bomb Tank)",
        "Burenia - Storm Missile Gate Room - Pickup (Energy Tank)",
        "Burenia - Drogyga Arena - Pickup (Drogyga)",
    },
    "Cataris": {
        "Cataris - Transport to Artaria - Pickup (Missile Tank)",
        "Cataris - Above Z-57 Fight - Pickup (Missile Tank)",
        "Cataris - Above Z-57 Fight - Pickup (Z-57)",
        "Cataris - Teleport to Artaria (Blue) - Pickup (Missile Tank)",
        "Cataris - Teleport to Artaria (Blue) - Pickup (Power Bomb Tank)",
        "Cataris - Z-57 Heat Room West (Right) - Pickup (Missile Tank)",
        "Cataris - Teleport to Artaria (Red) - Pickup (Missile+ Tank)",
        "Cataris - Teleport to Ghavoran - Pickup (Missile Tank - Top)",
        "Cataris - Teleport to Ghavoran - Pickup (Missile Tank - Bottom)",
        "Cataris - EMMI Zone Exits West - Pickup (Missile Tank)",
        "Cataris - EMMI Zone Item Tunnel - Pickup (Power Bomb Tank)",
        "Cataris - Central Unit Access - Pickup (Morph Ball)",
        "Cataris - Dairon Transport Access - Pickup (Missile Tank)",
        "Cataris - Thermal Device Room North - Pickup (Energy Part)",
        "Cataris - Thermal Device Room North - Pickup (Energy Tank)",
        "Cataris - Diffusion Beam Room - Pickup (Diffusion Beam)",
        "Cataris - Diffusion Beam Room - Pickup (Power Bomb Tank)",
        "Cataris - Lava Button East Access - Pickup (Missile Tank)",
        "Cataris - Double Obsydomithon Room - Pickup (Missile Tank)",
        "Cataris - Z-57 Heat Room East - Pickup (Missile Tank)",
        "Cataris - Teleport to Dairon - Pickup (Missile Tank)",
        "Cataris - Underlava Puzzle Room 2 - Pickup (Energy Part)",
        "Cataris - EMMI Zone Hidden Missile Room - Pickup (Missile Tank)",
        "Cataris - Kraid Eyedoor Room - Pickup (Missile Tank)",
        "Cataris - Kraid Arena - Pickup (Kraid)",
    },
    "Dairon": {
        "Dairon - Teleport to Artaria - Pickup (Missile Tank)",
        "Dairon - Big Hub - Pickup (Missile Tank)",
        "Dairon - Wide Beam Room - Pickup (Wide Beam)",
        "Dairon - Early Grapple Access - Pickup (Energy Part)",
        "Dairon - Transport to Artaria - Pickup (Power Bomb Tank)",
        "Dairon - Early Grapple Room - Pickup (Missile Tank Speedboost)",
        "Dairon - Early Grapple Room - Pickup (Missile Tank Tunnel)",
        "Dairon - Shinespark Tutorial - Pickup (Energy Tank)",
        "Dairon - EMMI Zone Exit North - Pickup (Power Bomb Tank)",
        "Dairon - Yellow EMMI Introduction - Pickup (Energy Part)",
        "Dairon - Cross Bomb Puzzle Room - Pickup (Missile Tank)",
        "Dairon - Bomb Room - Pickup (Bomb)",
        "Dairon - Bomb Room - Pickup (Missile Tank)",
        "Dairon - Freezer - Pickup (Missile Tank - Lower)",
        "Dairon - Freezer - Pickup (Missile Tank - Upper)",
        "Dairon - EMMI Zone Exit Northwest - Pickup (Missile Tank)",
        "Dairon - Hidden Grapple Shortcut Room - Pickup (Missile Tank)",
        "Dairon - Save Station West Tunnels - Pickup (Missile Tank)",
        "Dairon - Storm Missile Gate Room - Pickup (Missile+ Tank)",
        "Dairon - Lake Puzzle Room - Pickup (Power Bomb Tank)",
        "Dairon - Central Unit Access - Pickup (Energy Part)",
        "Dairon - Central Unit Access - Pickup (Speed Booster)",
        "Dairon - Energy Recharge Station West - Pickup (Energy Part)",
    },
    "Elun": {
        "Elun - Ammo Recharge Station - Pickup (Energy Tank)",
        "Elun - Plasma Beam Room - Pickup (Plasma Beam)",
        "Elun - Fan Room - Pickup (Missile Tank)",
        "Elun - Vertical Bomb Maze - Pickup (Power Bomb Tank)",
        "Elun - Horizontal Bomb Maze - Pickup (Missile Tank)",
    },
    "Ferenia": {
        "Ferenia - Total Recharge Station - Pickup (Energy Part)",
        "Ferenia - Fan Room - Pickup (Missile+ Tank)",
        "Ferenia - Speedboost Slopes Maze - Pickup (Energy Part)",
        "Ferenia - Separate Tunnels Room - Pickup (Missile Tank - Left)",
        "Ferenia - Separate Tunnels Room - Pickup (Missile Tank - Right)",
        "Ferenia - Space Jump Room - Pickup (Space Jump)",
        "Ferenia - Space Jump Room - Pickup (Missile Tank)",
        "Ferenia - Space Jump Room - Pickup (Missile+ Tank)",
        "Ferenia - Pitfall Puzzle Room - Pickup (Missile Tank)",
        "Ferenia - Twin Robot Arena - Pickup (Power Bomb Tank)",
        "Ferenia - Energy Recharge Station Secret - Pickup (Energy Part)",
        "Ferenia - Path to Escue - Pickup (Energy Part)",
        "Ferenia - Escue Eyedoor Room - Pickup (Missile Tank)",
        "Ferenia - Escue Arena - Pickup (Storm Missile)",
        "Ferenia - Cold Room (Storm Missile Gate) - Pickup (Missile Tank)",
        "Ferenia - Purple EMMI Arena - Pickup (Wave Beam)",
        "Ferenia - Purple EMMI Introduction - Pickup (Power Bomb Tank)",
    },
    "Ghavoran": {
        "Ghavoran - Right Entrance - Pickup (Missile Tank)",
        "Ghavoran - Left Entrance - Pickup (Missile Tank)",
        "Ghavoran - Dairon Transport Access - Pickup (Missile Tank)",
        "Ghavoran - Super Missile Room Access - Pickup (Missile+ Tank)",
        "Ghavoran - Super Missile Room - Pickup (Super Missile)",
        "Ghavoran - Central Unit Access - Pickup (Ice Missile)",
        "Ghavoran - Spin Boost Tower - Pickup (Power Bomb Tank)",
        "Ghavoran - Spin Boost Tower - Pickup (Energy Part)",
        "Ghavoran - Spin Boost Tower - Pickup (Energy Tank)",
        "Ghavoran - Golzuna Tower - Pickup (Energy Part)",
        "Ghavoran - Golzuna Tower - Pickup (Missile Tank)",
        "Ghavoran - Teleport to Burenia - Pickup (Missile Tank)",
        "Ghavoran - Total Recharge Station North - Pickup (Missile Tank)",
        "Ghavoran - Golzuna Arena - Pickup (Cross Bomb)",
        "Ghavoran - Map Station Access Secret - Pickup (Missile Tank)",
        "Ghavoran - Elun Transport Access - Pickup (Missile Tank)",
        "Ghavoran - Spin Boost Room - Pickup (Spin Boost)",
        "Ghavoran - Pulse Radar Room - Pickup (Pulse Radar)",
        "Ghavoran - Cross Bomb Tutorial - Pickup (Missile Tank)",
        "Ghavoran - Above Pulse Radar - Pickup (Missile Tank)",
    },
    "Hanubia": {
        "Hanubia - Ferenia Shortcut - Pickup (Missile Tank)",
        "Hanubia - Total Recharge Station North - Pickup (Missile Tank)",
        "Hanubia - Speedboost Puzzle Room - Pickup (Power Bomb Tank)",
        "Hanubia - Orange EMMI Introduction - Pickup (Power Bomb)",
    },
}

# Lookup table for reverse mapping
lookup_id_to_name: Dict[int, str] = {data.id: loc_name for loc_name, data in location_table.items()}

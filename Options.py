"""Complete Metroid Bread player options for Archipelago"""

from dataclasses import dataclass
from Options import (
    Choice, Range, Toggle, DefaultOnToggle, OptionSet,
    PerGameCommonOptions, DeathLink, StartInventoryPool, OptionGroup,
    ItemsAccessibility,
)

from worlds.metroid_bread.logic.DoorRando import DEFAULT_CHANGE_DOORS_TO, DEFAULT_DOORS_TO_CHANGE


class MetroidBreadAccessibility(ItemsAccessibility):
    """Set rules for reachability of your items/locations."""
    default = ItemsAccessibility.option_items

LIGHT_REGIONS = (
    "artaria", "burenia", "cataris", "dairon", "elun",
    "ferenia", "ghavoran", "hanubia", "itorash",
)


# Trick and glitch options.

class TrickDifficulty(Choice):
    """Base class for trick difficulty levels (Randovania LayoutTrickLevel names)."""
    option_disabled = 0
    option_beginner = 1
    option_intermediate = 2
    option_advanced = 3
    option_expert = 4
    option_ludicrous = 5
    # Accept older Hub and Seed Manager YAML names.
    alias_easy = 2
    alias_medium = 3
    alias_hard = 4
    default = 0


class KnowledgeTricks(TrickDifficulty):
    """Some destructible objects have vulnerabilities other than those which the player is informed of."""
    display_name = "Knowledge"


class MovementTricks(TrickDifficulty):
    """Non-obvious movement which can't easily be classified using other tricks."""
    display_name = "Movement"


class CombatTricks(TrickDifficulty):
    """If enabled, the player may be expected to defeat enemies and bosses with fewer items and less hea..."""
    display_name = "Combat"
    default = 1


class PseudoWave(TrickDifficulty):
    """It's possible to fire through solid walls without obtaining Wave Beam."""
    display_name = "Pseudo-Wave Beam"


class InfiniteBombJump(TrickDifficulty):
    """By chaining and timing bomb jumps it's possible to reach the top of a room."""
    display_name = "Infinite Bomb Jump"


class WaterBombJump(TrickDifficulty):
    """Performing a WBJ will make higher bomb jumps underwater possible."""
    display_name = "Water Bomb Jump"


class WaterSpaceJump(TrickDifficulty):
    """Used to gain height underwater in certain places without Gravity Suit."""
    display_name = "Water Space Jump"


class SingleWallWallJump(TrickDifficulty):
    """With this technique it is possible to jump up a single wall all the way up. Requires Morph Ball."""
    display_name = "Single-wall Wall Jump"


class SlideJump(TrickDifficulty):
    """By sliding off a cliff and jumping right before you fall you'll jump further."""
    display_name = "Slide Jump"


class SpeedBoosterConservation(TrickDifficulty):
    """Maintaining and chaining Speed Booster through complex and otherwise unintended situations."""
    display_name = "Speed Booster Conservation"


class WallJumpTricks(TrickDifficulty):
    """Basic movement ability which can be abused in unintended ways."""
    display_name = "Wall Jump"


class HeatColdRuns(TrickDifficulty):
    """You can run through heat and cold rooms without a suit. It depends on your health how long you ca..."""
    display_name = "Heat/Cold Runs"


class ReverseGrappleBlock(Toggle):
    """Opening up grapple blocks from the "wrong" side is possible."""
    display_name = "Reverse Grapple Block"


class DamageBoost(TrickDifficulty):
    """Most enemies will knock you away when Samus gets damaged. This can be used to get momentum over l..."""
    display_name = "Damage Boost"


class StandOnFrozenEnemy(TrickDifficulty):
    """After you receive the ice missiles you'll be able to freeze some enemies in place allowing you to..."""
    display_name = "Stand on Frozen Enemy"


class GrappleMovement(TrickDifficulty):
    """Using Grapple Beam for magnets without Spider Magnet, jumping from the tether, or Grapple Boost."""
    display_name = "Grapple Movement"


class CrossBombSkip(TrickDifficulty):
    """There are sets of crumble blocks that you must use Cross Bomb to roll across. All can be skipped..."""
    display_name = "Cross Bomb Skip"


class ClimbSlopedTunnels(TrickDifficulty):
    """Various tunnels that contain slopes in the game can be ascended with bombs or good movement."""
    display_name = "Climb Sloped Tunnels"


class ShortBoost(TrickDifficulty):
    """Flash Shift can be manipulated to allow you to charge Speed Booster in a smaller area than intended."""
    display_name = "Short Boost"


class DiffusionAbuse(TrickDifficulty):
    """Using Diffusion Beam in certain situations can bypass the usual requirements for some objects."""
    display_name = "Diffusion Abuse"


class FlashShiftSkip(TrickDifficulty):
    """With certain items or movement techniques, the Shutter Platforms can be bypassed without Flash Sh..."""
    display_name = "Flash Shift Skip"


class DiagonalBombJump(TrickDifficulty):
    """A special kind of bomb jump where you gain diagonal momentum from bombs that explode slightly to..."""
    display_name = "Diagonal Bomb Jump"


class LedgeWarp(TrickDifficulty):
    """A frame perfect trick that allows you to warp to a ledge you have previously been at."""
    display_name = "Ledge Warp"


class CrossBombLaunch(TrickDifficulty):
    """By sliding and morphing as the Cross Bomb is exploding, Samus gains a lot of horizontal momentum."""
    display_name = "Cross Bomb Launch"


class FloorClip(TrickDifficulty):
    """Many floors can be clipped through with Speed Booster, Flash Shift, and/or Grapple Beam."""
    display_name = "Floor Clip"


class ClimbSlopedSurfaces(TrickDifficulty):
    """It is possible to gain height on sloped surfaces with good movement (free-aim, Flash Shift, Spin..."""
    display_name = "Climb Sloped Surfaces"


# DNA and goal options.

class GameGoal(Choice):
    """How to complete your Metroid Bread slot."""
    display_name = "Game Goal"
    option_defeat_raven_beak = 0
    option_one_hundred_percent = 1
    option_all_bosses = 2
    default = 0

    @classmethod
    def get_option_name(cls, value) -> str:
        if value == cls.option_one_hundred_percent:
            return "100%"
        if value == cls.option_all_bosses:
            return "All Bosses"
        name = cls.name_lookup[value]
        return name.replace("_", " ").title()


class RequiredDNA(Range):
    """How many Metroid DNA must be collected before Raven Beak is logically /"""
    display_name = "Required Metroid DNA"
    range_start = 0
    range_end = 12
    default = 0


class DNAPlacement(Choice):
    """Where Metroid DNA may be placed when Required Metroid DNA > 0."""
    display_name = "Metroid DNA Placement"
    option_prefer_emmi = 0
    option_prefer_bosses = 1
    option_anywhere = 2
    default = 0


class HintAllDNA(DefaultOnToggle):
    """When Required Metroid DNA > 0, Adam / Network Stations reveal where all"""
    display_name = "Hint All Metroid DNA"


# Door and transport options.

class DoorLockRando(Choice):
    """Randomize the weapon needed to open eligible doors. Both sides of a door"""
    display_name = "Door Lock Randomizer"
    option_vanilla = 0
    option_individual_doors = 1
    alias_off = 0
    alias_randomized = 1
    default = 0


class RandovaniaDoorRando(Toggle):
    """Place locks with Randovania's Individual Doors algorithm.

    When on, eligible doors are opened to Power Beam before items are placed,
    then about 60% of those connections are locked from the inventory that can
    already reach either side. Uses Doors to Change and Change Doors To.
    When off, Door Lock Randomizer keeps Bread's current placer.
    """
    display_name = "Randovania Door Rando Algorithm"
    default = 0


class DoorsToChange(OptionSet):
    """Which vanilla door types may be randomized.

    Used when Door Lock Randomizer is Individual Doors, and when Randovania
    Door Rando Algorithm is on.
    """
    display_name = "Doors to Change"
    valid_keys = sorted(DEFAULT_DOORS_TO_CHANGE)
    default = frozenset(DEFAULT_DOORS_TO_CHANGE)


class ChangeDoorsTo(OptionSet):
    """Pool of lock types a randomized door may become."""
    display_name = "Change Doors To"
    valid_keys = sorted(DEFAULT_CHANGE_DOORS_TO)
    default = frozenset(DEFAULT_CHANGE_DOORS_TO)


class TransportRando(Choice):
    """Shuffle elevator and shuttle destinations (two-way within type)."""
    display_name = "Transport Randomizer"
    option_off = 0
    option_randomized = 1
    default = 0


class IncludeBossPickups(DefaultOnToggle):
    """Whether boss and EMMI defeat pickups are AP checks (on by default)."""
    display_name = "Include Boss & EMMI Pickups"


class StartWithPulseRadar(DefaultOnToggle):
    """Start with Pulse Radar. When off, Pulse Radar is shuffled into the pool."""
    display_name = "Start With Pulse Radar"


# Appearance and combat options.

class ShowBossLifebar(DefaultOnToggle):
    display_name = "Show Boss Lifebar"


class ShowEnemyLife(Toggle):
    display_name = "Show Enemy Life"


class ShowEnemyDamage(Toggle):
    display_name = "Show Enemy Damage"


class ShowPlayerDamage(DefaultOnToggle):
    """Show floating damage numbers when Samus takes damage (ODR config.ini"""
    display_name = "Show Player Damage"


class ImmediateEnergyParts(DefaultOnToggle):
    """When enabled, each Energy Part immediately raises max energy by 1/4 of"""
    display_name = "Immediate Energy Parts"


class ConstantHeatDamage(Range):
    """Constant heated-room damage per second (ODR ``constant_environment_damage.heat``)."""
    display_name = "Constant Heat Damage"
    range_start = 0
    range_end = 1000
    default = 20


class ConstantColdDamage(Range):
    """Constant cold-room damage per second (ODR ``constant_environment_damage.cold``)."""
    display_name = "Constant Cold Damage"
    range_start = 0
    range_end = 1000
    default = 20


class ConstantLavaDamage(Range):
    """Constant lava damage per second (ODR ``constant_environment_damage.lava``)."""
    display_name = "Constant Lava Damage"
    range_start = 0
    range_end = 1000
    default = 20


class EnableDeathCounter(DefaultOnToggle):
    display_name = "Death Counter"


class ShowDnaInHud(DefaultOnToggle):
    """Show collected Metroid DNA count on the HUD when Required DNA > 0."""
    display_name = "Show DNA In HUD"


class RoomNameDisplay(Choice):
    display_name = "Room Name Display"
    option_never = 0
    option_always = 1
    option_with_fade = 2
    default = 0


class RavenBeakDamageTable(Choice):
    display_name = "Raven Beak Damage Table"
    option_unmodified = 0
    option_consistent_low = 1
    option_consistent_high = 2
    default = 1


class NerfPowerBombs(Toggle):
    """Power Bomb Limitations (RDV / ODR): Power Bombs no longer open Charge Beam"""
    display_name = "Nerf Power Bombs"


class SkipItemPopups(Toggle):
    """Skip the item-get dialogue. The item is granted immediately and its
    collection line is queued on the bottom-right received-item bar (YAML
    ``skip_item_popups``). Off: the normal acquisition popup still plays.
    """
    display_name = "Skip Item Acquisition Popups"


class DisabledLights(OptionSet):
    """Regions whose light actors are mass-deleted (darker rooms)."""
    display_name = "Disabled Lights"
    valid_keys = sorted(LIGHT_REGIONS)
    default = frozenset()


class StationMapWarp(Toggle):
    """Master switch for pause-map station warps (YAML ``station_map_warp``).

    On the pause map, A still navigates the world map and places markers.
    Y on a locked Save, Map, or Network station opens the warp prompt instead
    of cycling icon highlights, and only while that map page is actually open
    (Enabled and Visible). Y during gameplay does nothing. Y off a station
    still highlights icons. Which stations Y can target is set by Pause Map
    Warp Requirement and Pause Map Warp Reach. Off: the prompt is not in the
    game. Existing yamls that only set this option keep warping; the new
    options are not required.
    """
    display_name = "Pause Map Station Warp"
    default = 0


class StationWarpRequirement(Choice):
    """Which locked stations Y may warp to when Pause Map Station Warp is on.

    Visited (default, current behavior): only a Save, Map, or Network station
    you have already used. An unused station shows "You haven't saved here
    yet" and A closes that notice. It does not warp.
    Visible: any station icon the pause-map cursor has locked, including one
    you have not used, when the catalog has a spawn point for it. A confirms
    that warp and B cancels. An unused station with no spawn still shows the
    unused notice instead of loading a bad target.
    Y only opens a prompt while the pause map is open. Ignored while Pause
    Map Station Warp is off.
    """
    display_name = "Pause Map Warp Requirement"
    option_visible = 0
    option_visited = 1
    default = 1


class StationWarpReach(Choice):
    """Which regions Y may warp to when Pause Map Station Warp is on.

    The pause-map lock already follows the region named in the map header, and
    that header can be a region other than the one Samus is standing in. A
    warp loads the catalog station's own scenario and start point. That is
    global, so the default stays global and existing seeds do not shrink to
    the current region.
    Local: only a station in the scenario you are currently in. A station in
    another region is ignored even when the cursor distance matches it.
    Global: any Save, Map, or Network station in the game, still limited by
    Pause Map Warp Requirement.
    Y only opens a prompt while the pause map is open. Ignored while Pause
    Map Station Warp is off.
    """
    display_name = "Pause Map Warp Reach"
    option_local = 0
    option_global = 1
    default = 1


class XStartsReleased(Toggle):
    """Start with X parasites already released (Elun / freeroam flavor)."""
    display_name = "X Starts Released"


# Ammo and energy amounts.

class EnergyPerTank(Range):
    display_name = "Energy Per Tank"
    range_start = 1
    range_end = 1000
    default = 100


class StartingMissiles(Range):
    display_name = "Starting Missiles"
    range_start = 0
    range_end = 255
    default = 15


class StartingPowerBombs(Range):
    display_name = "Starting Power Bombs"
    range_start = 0
    range_end = 10
    default = 0


class MissileTankAmmo(Range):
    display_name = "Missile Tank Ammo"
    range_start = 1
    range_end = 50
    default = 2


class MissilePlusTankAmmo(Range):
    display_name = "Missile+ Tank Ammo"
    range_start = 1
    range_end = 100
    default = 10


class PowerBombTankAmmo(Range):
    display_name = "Power Bomb Tank Ammo"
    range_start = 1
    range_end = 10
    default = 1


class VanillaFlashShiftBehaviour(DefaultOnToggle):
    """When enabled, the pool contains a single **Flash Shift** item that grants the"""
    display_name = "Vanilla Flash Shift Behaviour"


class FlashShiftUpgradeAmount(Range):
    """How many chain dashes each Flash Shift Upgrade pickup grants (after the base flash)."""
    display_name = "Flash Shift Upgrade Amount"
    range_start = 1
    range_end = 10
    default = 1


class FlashShiftUpgradeCount(Range):
    """Number of Flash Shift Upgrade pickups in the pool (1–5)."""
    display_name = "Flash Shift Upgrade Count"
    range_start = 1
    range_end = 5
    default = 3


class SpeedBoosterUpgradeCount(Range):
    display_name = "Speed Booster Upgrade Count"
    range_start = 0
    range_end = 10
    default = 0


class FlashShiftIncludedAmmo(Range):
    """Chain dashes bundled with the main Flash Shift item (vanilla is 2)."""
    display_name = "Flash Shift Included Ammo"
    range_start = 0
    range_end = 10
    default = 2


class FlashShiftUpgradeRequiresMainItem(DefaultOnToggle):
    """Only used when Vanilla Flash Shift Behaviour is off."""
    display_name = "Require Main Item"


# Item pool options.

class EnergyTanks(Range):
    """Number of Energy Tanks in the item pool."""
    display_name = "Energy Tanks"
    range_start = 0
    range_end = 12
    default = 8


class EnergyParts(Range):
    """Number of Energy Parts in the item pool. Four Energy Parts equal one Energy Tank."""
    display_name = "Energy Parts"
    range_start = 0
    range_end = 20
    default = 16


class MissileTanks(Range):
    """Number of Missile Tanks (+2 missiles each) in the item pool."""
    display_name = "Missile Tanks"
    range_start = 10
    range_end = 50
    default = 35


class MissilePlusTanks(Range):
    """Number of Missile+ Tanks (+10 missiles each) in the item pool."""
    display_name = "Missile+ Tanks"
    range_start = 0
    range_end = 15
    default = 10


class PowerBombTanks(Range):
    """Number of Power Bomb Tanks (+1 power bomb each) in the item pool."""
    display_name = "Power Bomb Tanks"
    range_start = 0
    range_end = 15
    default = 12


# Progressive item options.

class ProgressiveBeams(Toggle):
    """If enabled, individual beam upgrades (Wide, Plasma, Wave) are replaced with Progressive Beams."""
    display_name = "Progressive Beams"
    default = 1


class ProgressiveCharge(Toggle):
    """If enabled, Charge Beam and Diffusion Beam are replaced with Progressive Charge Beam."""
    display_name = "Progressive Charge Beam"
    default = 1


class ProgressiveMissiles(Toggle):
    """If enabled, Super Missile and Ice Missile are replaced with Progressive Missiles."""
    display_name = "Progressive Missiles"
    default = 0


class ProgressiveBombs(Toggle):
    """If enabled, Bomb and Cross Bomb are replaced with Progressive Bombs."""
    display_name = "Progressive Bombs"
    default = 1


class ProgressiveSuit(Toggle):
    """If enabled, Varia Suit and Gravity Suit are replaced with Progressive Suits."""
    display_name = "Progressive Suit"
    default = 1


class ProgressiveSpin(Toggle):
    """If enabled, Spin Boost and Space Jump are replaced with Progressive Spins."""
    display_name = "Progressive Spin"
    default = 1


# Logic settings.

def _build_starting_location_option():
    """Choice: default (Artaria Intro), random_save_station (any RDV-valid start),"""
    from worlds.metroid_bread.logic.starting_locations import load_starting_locations

    starts = load_starting_locations()
    attrs = {
        "__module__": __name__,
        "__doc__": (
            "Where Samus begins a new save. "
            "default = Artaria Intro Room (vanilla). "
            "random_save_station = pick a random Randovania-valid start "
            "(save / map / nav platforms and the intro start). "
            "Or choose a specific location."
        ),
        "display_name": "Starting Location",
        "option_default": 0,
        "option_random_save_station": 1,
        "default": 0,
        "auto_display_name": True,
    }
    next_id = 2
    for start in starts:
        if start.is_default:
            continue
        attrs[f"option_{start.option_key}"] = next_id
        next_id += 1
    return type("StartingLocation", (Choice,), attrs)


StartingLocation = _build_starting_location_option()


class EarlyMorphBall(Toggle):
    """If enabled, Morph Ball will be guaranteed early in the seed."""
    display_name = "Early Morph Ball"
    default = 0


class DangerousLogic(Toggle):
    """Off: a check is only in logic if it is reachable AND you can leave back toward the start (or otherwise escape). On: reachable is enough, even if the room softlocks you."""
    display_name = "Dangerous Logic"
    default = 0


class StartingKitItems(Range):
    """Max progression items the generator may precollect as a Start Kit so the"""
    display_name = "Starting Items"
    range_start = 0
    range_end = 5
    default = 0


@dataclass
class MetroidBreadOptions(PerGameCommonOptions):
    """Complete options for Metroid Bread with all tricks and glitches"""
    # Require 90% access before victory, or all checks for 100%.
    accessibility: MetroidBreadAccessibility
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink

    # Goal and DNA requirement.
    game_goal: GameGoal
    required_dna: RequiredDNA
    dna_placement: DNAPlacement
    hint_all_dna: HintAllDNA

    # Door and transport settings.
    door_lock_rando: DoorLockRando
    randovania_door_rando: RandovaniaDoorRando
    doors_to_change: DoorsToChange
    change_doors_to: ChangeDoorsTo
    transport_rando: TransportRando

    # Item pool and starting settings.
    include_boss_pickups: IncludeBossPickups
    start_with_pulse_radar: StartWithPulseRadar

    # Appearance and combat settings.
    show_boss_lifebar: ShowBossLifebar
    show_enemy_life: ShowEnemyLife
    show_enemy_damage: ShowEnemyDamage
    show_player_damage: ShowPlayerDamage
    immediate_energy_parts: ImmediateEnergyParts
    constant_heat_damage: ConstantHeatDamage
    constant_cold_damage: ConstantColdDamage
    constant_lava_damage: ConstantLavaDamage
    enable_death_counter: EnableDeathCounter
    show_dna_in_hud: ShowDnaInHud
    room_name_display: RoomNameDisplay
    raven_beak_damage_table: RavenBeakDamageTable
    nerf_power_bombs: NerfPowerBombs
    skip_item_popups: SkipItemPopups
    disabled_lights: DisabledLights
    x_starts_released: XStartsReleased
    station_map_warp: StationMapWarp
    warp_requirement: StationWarpRequirement
    warp_reach: StationWarpReach

    # Item pool counts.
    energy_tanks: EnergyTanks
    energy_parts: EnergyParts
    missile_tanks: MissileTanks
    missile_plus_tanks: MissilePlusTanks
    power_bomb_tanks: PowerBombTanks

    # Ammo and energy amounts.
    energy_per_tank: EnergyPerTank
    starting_missiles: StartingMissiles
    starting_power_bombs: StartingPowerBombs
    missile_tank_ammo: MissileTankAmmo
    missile_plus_tank_ammo: MissilePlusTankAmmo
    power_bomb_tank_ammo: PowerBombTankAmmo
    vanilla_flash_shift_behaviour: VanillaFlashShiftBehaviour
    flash_shift_upgrade_amount: FlashShiftUpgradeAmount
    flash_shift_upgrade_count: FlashShiftUpgradeCount
    speed_booster_upgrade_count: SpeedBoosterUpgradeCount
    flash_shift_included_ammo: FlashShiftIncludedAmmo
    flash_shift_upgrade_requires_main_item: FlashShiftUpgradeRequiresMainItem

    # Progressive item settings.
    progressive_beams: ProgressiveBeams
    progressive_charge: ProgressiveCharge
    progressive_missiles: ProgressiveMissiles
    progressive_bombs: ProgressiveBombs
    progressive_suit: ProgressiveSuit
    progressive_spin: ProgressiveSpin

    # Logic settings.
    starting_location: StartingLocation
    starting_kit_items: StartingKitItems
    early_morph_ball: EarlyMorphBall
    dangerous_logic: DangerousLogic

    # Trick and glitch settings.
    knowledge_tricks: KnowledgeTricks
    movement_tricks: MovementTricks
    combat_tricks: CombatTricks
    pseudo_wave: PseudoWave
    infinite_bomb_jump: InfiniteBombJump
    water_bomb_jump: WaterBombJump
    water_space_jump: WaterSpaceJump
    single_wall_wall_jump: SingleWallWallJump
    slide_jump: SlideJump
    speedbooster_conservation: SpeedBoosterConservation
    wall_jump_tricks: WallJumpTricks
    heat_cold_runs: HeatColdRuns
    reverse_grapple_block: ReverseGrappleBlock
    damage_boost: DamageBoost
    stand_on_frozen_enemy: StandOnFrozenEnemy
    grapple_movement: GrappleMovement
    cross_bomb_skip: CrossBombSkip
    climb_sloped_tunnels: ClimbSlopedTunnels
    short_boost: ShortBoost
    diffusion_abuse: DiffusionAbuse
    flash_shift_skip: FlashShiftSkip
    diagonal_bomb_jump: DiagonalBombJump
    ledge_warp: LedgeWarp
    cross_bomb_launch: CrossBombLaunch
    floor_clip: FloorClip
    climb_sloped_surfaces: ClimbSlopedSurfaces


# Group options on the website.
metroid_bread_option_groups = [
    OptionGroup("Goal & DNA", [
        GameGoal,
        RequiredDNA,
        DNAPlacement,
        HintAllDNA,
        ShowDnaInHud,
    ]),
    OptionGroup("Door & Transport Rando", [
        DoorLockRando,
        RandovaniaDoorRando,
        DoorsToChange,
        ChangeDoorsTo,
        TransportRando,
    ]),
    OptionGroup("Cosmetics & Combat", [
        ShowBossLifebar,
        ShowEnemyLife,
        ShowEnemyDamage,
        ShowPlayerDamage,
        ImmediateEnergyParts,
        ConstantHeatDamage,
        ConstantColdDamage,
        ConstantLavaDamage,
        EnableDeathCounter,
        RoomNameDisplay,
        RavenBeakDamageTable,
        NerfPowerBombs,
        DisabledLights,
        XStartsReleased,
        StationMapWarp,
        StationWarpRequirement,
        StationWarpReach,
    ]),
    OptionGroup("Starting Location", [
        StartingLocation,
        StartingKitItems,
        EarlyMorphBall,
        StartWithPulseRadar,
        IncludeBossPickups,
    ]),
    OptionGroup("Item Pool", [
        EnergyTanks,
        EnergyParts,
        MissileTanks,
        MissilePlusTanks,
        PowerBombTanks,
        SpeedBoosterUpgradeCount,
    ]),
    OptionGroup("Flash Shift", [
        VanillaFlashShiftBehaviour,
        FlashShiftUpgradeCount,
        FlashShiftUpgradeRequiresMainItem,
        FlashShiftIncludedAmmo,
        FlashShiftUpgradeAmount,
    ]),
    OptionGroup("Ammo & Energy Yields", [
        EnergyPerTank,
        StartingMissiles,
        StartingPowerBombs,
        MissileTankAmmo,
        MissilePlusTankAmmo,
        PowerBombTankAmmo,
    ]),
    OptionGroup("Progressive Items", [
        ProgressiveBeams,
        ProgressiveCharge,
        ProgressiveMissiles,
        ProgressiveBombs,
        ProgressiveSuit,
        ProgressiveSpin,
    ]),
    OptionGroup("Logic", [
        DangerousLogic,
    ]),
    OptionGroup("Basic Tricks", [
        KnowledgeTricks,
        MovementTricks,
        CombatTricks,
        SlideJump,
        WallJumpTricks,
    ]),
    OptionGroup("Advanced Movement Tricks", [
        InfiniteBombJump,
        WaterBombJump,
        WaterSpaceJump,
        SingleWallWallJump,
        DiagonalBombJump,
        CrossBombLaunch,
        GrappleMovement,
    ]),
    OptionGroup("Speed Booster Tricks", [
        SpeedBoosterConservation,
        ShortBoost,
        FlashShiftSkip,
    ]),
    OptionGroup("Environmental Tricks", [
        HeatColdRuns,
        ClimbSlopedTunnels,
        ClimbSlopedSurfaces,
        FloorClip,
        DamageBoost,
    ]),
    OptionGroup("Combat & Item Tricks", [
        PseudoWave,
        DiffusionAbuse,
        StandOnFrozenEnemy,
        CrossBombSkip,
    ]),
    OptionGroup("Expert Tricks", [
        LedgeWarp,
        ReverseGrappleBlock,
    ]),
]

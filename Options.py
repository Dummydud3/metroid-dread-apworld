"""
Complete Metroid Dread player options for Archipelago
Includes all tricks and glitches from Randovania
"""

from dataclasses import dataclass
from Options import (
    Choice, Range, Toggle, DefaultOnToggle, OptionSet,
    PerGameCommonOptions, DeathLink, StartInventoryPool, OptionGroup,
    ItemsAccessibility,
)

from .DoorRando import (
    ALL_DOOR_WEAKNESS_NAMES,
    DEFAULT_CHANGE_DOORS_TO,
    DEFAULT_DOORS_TO_CHANGE,
)


class MetroidDreadAccessibility(ItemsAccessibility):
    """
    Set rules for reachability of your items/locations.

    **Full:** ensure everything can be reached and acquired.

    **Minimal:** ensure what is needed to reach your goal can be acquired.

    **Items:** ensure all logically relevant items can be acquired. Some items, such as keys, may be self-locking, and
    some locations may be inaccessible.

    Metroid Dread always enforces a stronger world rule regardless of this setting:
    when Raven Beak becomes reachable, at least 90% of clearable pickup checks must
    already be reachable with that same collection state (100% when Game Goal is
    100%).

    During generation, Minimal is upgraded to Items. Full is kept only when every
    AP pickup/event is in logic under the rolled tricks; otherwise it is
    downgraded to Items (Speedbooster Conservation / Knowledge / etc. gate several
    checks that would otherwise fail fulfills_accessibility on every seed).
    """
    default = ItemsAccessibility.option_items

LIGHT_REGIONS = (
    "artaria", "burenia", "cataris", "dairon", "elun",
    "ferenia", "ghavoran", "hanubia", "itorash",
)


# ===== TRICK/GLITCH OPTIONS =====

class TrickDifficulty(Choice):
    """
    Base class for trick difficulty levels (Randovania LayoutTrickLevel names).

    Numeric values match RDV ``LayoutTrickLevel.as_number`` so logic database
    requirements compare correctly:

    Disabled=0, Beginner=1, Intermediate=2, Advanced=3, Expert=4, Ludicrous=5.

    Legacy YAML aliases (easy/medium/hard) map to Intermediate/Advanced/Expert.
    Pre-rename ``expert`` meant value 5; prefer ``ludicrous`` for that level now.
    """
    option_disabled = 0
    option_beginner = 1
    option_intermediate = 2
    option_advanced = 3
    option_expert = 4
    option_ludicrous = 5
    # Back-compat with older Hub / Seed Manager YAML wording
    alias_easy = 2
    alias_medium = 3
    alias_hard = 4
    default = 0


class KnowledgeTricks(TrickDifficulty):
    """
    Some destructible objects have vulnerabilities other than those which the player is informed of.
    For example, Power Bomb can be used to destroy Enkys or open charge beam doors.
    """
    display_name = "Knowledge"


class MovementTricks(TrickDifficulty):
    """
    Non-obvious movement which can't easily be classified using other tricks.
    Players may be expected to perform precise jumps and other niche movement optimizations.
    """
    display_name = "Movement"


class CombatTricks(TrickDifficulty):
    """
    If enabled, the player may be expected to defeat enemies and bosses with fewer items and less health.
    Defaults to Beginner so early bosses (e.g. Corpius) are logically clearable without
    collecting Energy Tanks during accessibility checks.
    """
    display_name = "Combat"
    default = 1


class PseudoWave(TrickDifficulty):
    """
    It's possible to fire through solid walls without obtaining Wave Beam.
    """
    display_name = "Pseudo-Wave Beam"


class InfiniteBombJump(TrickDifficulty):
    """
    By chaining and timing bomb jumps it's possible to reach the top of a room.
    """
    display_name = "Infinite Bomb Jump"


class WaterBombJump(TrickDifficulty):
    """
    Performing a WBJ will make higher bomb jumps underwater possible.
    """
    display_name = "Water Bomb Jump"


class WaterSpaceJump(TrickDifficulty):
    """
    Used to gain height underwater in certain places without Gravity Suit.
    """
    display_name = "Water Space Jump"


class SingleWallWallJump(TrickDifficulty):
    """
    With this technique it is possible to jump up a single wall all the way up. Requires Morph Ball.
    """
    display_name = "Single-wall Wall Jump"


class SlideJump(TrickDifficulty):
    """
    By sliding off a cliff and jumping right before you fall you'll jump further.
    """
    display_name = "Slide Jump"


class SpeedBoosterConservation(TrickDifficulty):
    """
    Maintaining and chaining Speed Booster through complex and otherwise unintended situations.
    """
    display_name = "Speed Booster Conservation"


class WallJumpTricks(TrickDifficulty):
    """
    Basic movement ability which can be abused in unintended ways.
    """
    display_name = "Wall Jump"


class HeatColdRuns(TrickDifficulty):
    """
    You can run through heat and cold rooms without a suit. It depends on your health how long you can stay.
    """
    display_name = "Heat/Cold Runs"


class ReverseGrappleBlock(Toggle):
    """
    Opening up grapple blocks from the "wrong" side is possible.
    """
    display_name = "Reverse Grapple Block"


class DamageBoost(TrickDifficulty):
    """
    Most enemies will knock you away when Samus gets damaged. This can be used to get momentum over ledges.
    """
    display_name = "Damage Boost"


class StandOnFrozenEnemy(TrickDifficulty):
    """
    After you receive the ice missiles you'll be able to freeze some enemies in place allowing you to reach certain spots.
    """
    display_name = "Stand on Frozen Enemy"


class GrappleMovement(TrickDifficulty):
    """
    Using Grapple Beam for magnets without Spider Magnet, jumping from the tether, or Grapple Boost.
    """
    display_name = "Grapple Movement"


class CrossBombSkip(TrickDifficulty):
    """
    There are sets of crumble blocks that you must use Cross Bomb to roll across. All can be skipped with the right tools.
    """
    display_name = "Cross Bomb Skip"


class ClimbSlopedTunnels(TrickDifficulty):
    """
    Various tunnels that contain slopes in the game can be ascended with bombs or good movement.
    """
    display_name = "Climb Sloped Tunnels"


class ShortBoost(TrickDifficulty):
    """
    Flash Shift can be manipulated to allow you to charge Speed Booster in a smaller area than intended.
    """
    display_name = "Short Boost"


class DiffusionAbuse(TrickDifficulty):
    """
    Using Diffusion Beam in certain situations can bypass the usual requirements for some objects.
    """
    display_name = "Diffusion Abuse"


class FlashShiftSkip(TrickDifficulty):
    """
    With certain items or movement techniques, the Shutter Platforms can be bypassed without Flash Shift.
    """
    display_name = "Flash Shift Skip"


class DiagonalBombJump(TrickDifficulty):
    """
    A special kind of bomb jump where you gain diagonal momentum from bombs that explode slightly to the side.
    """
    display_name = "Diagonal Bomb Jump"


class LedgeWarp(TrickDifficulty):
    """
    A frame perfect trick that allows you to warp to a ledge you have previously been at.
    """
    display_name = "Ledge Warp"


class CrossBombLaunch(TrickDifficulty):
    """
    By sliding and morphing as the Cross Bomb is exploding, Samus gains a lot of horizontal momentum.
    """
    display_name = "Cross Bomb Launch"


class FloorClip(TrickDifficulty):
    """
    Many floors can be clipped through with Speed Booster, Flash Shift, and/or Grapple Beam.
    """
    display_name = "Floor Clip"


class ClimbSlopedSurfaces(TrickDifficulty):
    """
    It is possible to gain height on sloped surfaces with good movement (free-aim, Flash Shift, Spin Boost, or Phantom Cloak).
    """
    display_name = "Climb Sloped Surfaces"


# ===== DNA / GOAL OPTIONS =====
# Required DNA gates the Itorash artifact door. Game Goal chooses the win condition.

class GameGoal(Choice):
    """
    How to complete your Metroid Dread slot.

    **Defeat Raven Beak:** kill Raven Beak (Itorash). Generation still requires
    >=90% of clearable pickup checks in logic when Raven Beak opens.

    **100%:** collect every check in your slot, then kill Raven Beak. Generation
    requires 100% of clearable checks in logic before Raven Beak opens; the
    client only sends goal when all checks are collected and Raven Beak is beaten.

    **All Bosses:** defeat every combat/story boss (see bosses.py), including
    Z-57 via its pickup check, then kill Raven Beak. Generation keeps the 90%
    clearance gate and also requires every boss node in logic when Raven Beak
    opens; the client only sends goal when all bosses are beaten and the game
    beaten flag is set.
    """
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
    """
    How many Metroid DNA must be collected before Raven Beak is logically /
    in-game accessible. 0 disables the DNA gate (vanilla-style open artifacts).
    """
    display_name = "Required Metroid DNA"
    range_start = 0
    range_end = 12
    default = 0


class DNAPlacement(Choice):
    """
    Where Metroid DNA may be placed when Required Metroid DNA > 0.
    prefer_emmi locks DNA onto Central Unit / EMMI-defeat pickups when possible.
    """
    display_name = "Metroid DNA Placement"
    option_prefer_emmi = 0
    option_prefer_bosses = 1
    option_anywhere = 2
    default = 0


class HintAllDNA(DefaultOnToggle):
    """
    When Required Metroid DNA > 0, Adam / Network Stations reveal where all
    required DNA are located.
    """
    display_name = "Hint All Metroid DNA"


# ===== DOOR / TRANSPORT =====

class DoorLockRando(Choice):
    """
    Randomize the weapon needed to open eligible doors. Both sides of a door
    always match. Only basic lock types are used (safe for open-dread-rando).
    """
    display_name = "Door Lock Randomizer"
    option_vanilla = 0
    option_individual_doors = 1
    alias_off = 0
    alias_randomized = 1
    default = 0


class DoorsToChange(OptionSet):
    """Which vanilla door types may be randomized (when Door Lock Rando is on)."""
    display_name = "Doors to Change"
    valid_keys = sorted(ALL_DOOR_WEAKNESS_NAMES)
    default = frozenset(DEFAULT_DOORS_TO_CHANGE)


class ChangeDoorsTo(OptionSet):
    """Pool of lock types a randomized door may become (basic types only)."""
    display_name = "Change Doors To"
    valid_keys = sorted(ALL_DOOR_WEAKNESS_NAMES)
    default = frozenset(DEFAULT_CHANGE_DOORS_TO)


class TransportRando(Choice):
    """
    Shuffle elevator and shuttle destinations (two-way within type).
    Teleporters stay vanilla. The Itorash capsule stays on its vanilla Hanubia
    pairing so transport rando cannot open Raven Beak from a mid-game elevator.
    Falls back to vanilla if a shuffle strands checks.
    """
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


# ===== COSMETICS / COMBAT =====

class ShowBossLifebar(DefaultOnToggle):
    display_name = "Show Boss Lifebar"


class ShowEnemyLife(Toggle):
    display_name = "Show Enemy Life"


class ShowEnemyDamage(Toggle):
    display_name = "Show Enemy Damage"


class ShowPlayerDamage(DefaultOnToggle):
    """Show floating damage numbers when Samus takes damage (ODR config.ini
    ``AIManager.bShowPlayerDamage``). Off = hidden, same as Randovania/ODR."""
    display_name = "Show Player Damage"


class ImmediateEnergyParts(DefaultOnToggle):
    """When enabled, each Energy Part immediately raises max energy by 1/4 of
    Energy Per Tank (ODR ``immediate_energy_parts`` / ``Init.bImmediateEnergyParts``).
    When off, four parts are needed before energy increases (vanilla fragment
    behavior). Matches Randovania's Immediate Energy Part setting."""
    display_name = "Immediate Energy Parts"


class ConstantHeatDamage(Range):
    """Constant heated-room damage per second (ODR ``constant_environment_damage.heat``).
    0 = vanilla scaling damage. Randovania starter uses 20."""
    display_name = "Constant Heat Damage"
    range_start = 0
    range_end = 1000
    default = 20


class ConstantColdDamage(Range):
    """Constant cold-room damage per second (ODR ``constant_environment_damage.cold``).
    0 = vanilla scaling damage. Randovania starter uses 20."""
    display_name = "Constant Cold Damage"
    range_start = 0
    range_end = 1000
    default = 20


class ConstantLavaDamage(Range):
    """Constant lava damage per second (ODR ``constant_environment_damage.lava``).
    0 = vanilla scaling damage. Randovania starter uses 20."""
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
    """
    Power Bomb Limitations (RDV / ODR): Power Bombs no longer open Charge Beam
    doors or destroy Enkys. Generator logic follows the same restriction.
    """
    display_name = "Nerf Power Bombs"


class DisabledLights(OptionSet):
    """Regions whose light actors are mass-deleted (darker rooms)."""
    display_name = "Disabled Lights"
    valid_keys = sorted(LIGHT_REGIONS)
    default = frozenset()


class XStartsReleased(Toggle):
    """Start with X parasites already released (Elun / freeroam flavor)."""
    display_name = "X Starts Released"


# ===== AMMO / ENERGY YIELDS =====

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
    """
    When enabled, the pool contains a single **Flash Shift** item that grants the
    full vanilla ability (Ghost Aura + 2 chain dashes), matching Randovania / ODR.

    When disabled, Flash Shift uses the upgrade-based system controlled by
    Flash Shift Upgrade Count and Require Main Item.
    """
    display_name = "Vanilla Flash Shift Behaviour"


class FlashShiftUpgradeAmount(Range):
    """How many chain dashes each Flash Shift Upgrade pickup grants (after the base flash)."""
    display_name = "Flash Shift Upgrade Amount"
    range_start = 1
    range_end = 10
    default = 1


class FlashShiftUpgradeCount(Range):
    """
    Number of Flash Shift Upgrade pickups in the pool (1–5).

    Only used when Vanilla Flash Shift Behaviour is off.
    All N upgrades are always added to the item pool and displace Missile Tank
    filler 1:1 (same padding bucket), so they are guaranteed placements — not
    optional leftovers that can be dropped when the pool is full.
    Classification is filler (chain ammo) like Missile Tanks; they do not consume
    major progression capacity. When Require Main Item is also off, the first
    upgrade unlocks Flash Shift (progressive) and is promoted to progression;
    later upgrades add chains only.
    """
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
    """
    Chain dashes bundled with the main Flash Shift item (vanilla is 2).
    Used when Vanilla Flash Shift Behaviour is on, or when Require Main Item is on.
    """
    display_name = "Flash Shift Included Ammo"
    range_start = 0
    range_end = 10
    default = 2


class FlashShiftUpgradeRequiresMainItem(DefaultOnToggle):
    """
    Only used when Vanilla Flash Shift Behaviour is off.

    **On:** Flash Shift Upgrades may be collected early and stack chains, but the
    ability does not unlock until the main Flash Shift item is collected.

    **Off:** the first Flash Shift Upgrade unlocks the ability (progressive major);
    later upgrades add chains only.
    """
    display_name = "Require Main Item"


# ===== ITEM POOL OPTIONS =====

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


# ===== PROGRESSIVE ITEM OPTIONS =====

class ProgressiveBeams(Toggle):
    """
    If enabled, individual beam upgrades (Wide, Plasma, Wave) are replaced with Progressive Beams.
    """
    display_name = "Progressive Beams"
    default = 1


class ProgressiveCharge(Toggle):
    """
    If enabled, Charge Beam and Diffusion Beam are replaced with Progressive Charge Beam.
    """
    display_name = "Progressive Charge Beam"
    default = 1


class ProgressiveMissiles(Toggle):
    """
    If enabled, Super Missile and Ice Missile are replaced with Progressive Missiles.
    """
    display_name = "Progressive Missiles"
    default = 0


class ProgressiveBombs(Toggle):
    """
    If enabled, Bomb and Cross Bomb are replaced with Progressive Bombs.
    """
    display_name = "Progressive Bombs"
    default = 1


class ProgressiveSuit(Toggle):
    """
    If enabled, Varia Suit and Gravity Suit are replaced with Progressive Suits.
    """
    display_name = "Progressive Suit"
    default = 1


class ProgressiveSpin(Toggle):
    """
    If enabled, Spin Boost and Space Jump are replaced with Progressive Spins.
    """
    display_name = "Progressive Spin"
    default = 1


# ===== LOGIC OPTIONS =====

def _build_starting_location_option():
    """
    Choice: default (Artaria Intro), random_save_station (any RDV-valid start),
    or a specific Save/Map/Nav station / start point.
    """
    from .starting_locations import load_starting_locations

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
    """
    If enabled, Morph Ball will be guaranteed early in the seed.
    """
    display_name = "Early Morph Ball"
    default = 0


@dataclass
class MetroidDreadOptions(PerGameCommonOptions):
    """
    Complete options for Metroid Dread with all tricks and glitches
    """
    # Victory implies 90% clearance (100% for one_hundred_percent; all bosses
    # adds a boss-node gate on top of 90%).
    accessibility: MetroidDreadAccessibility
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink

    # Goal + DNA gate
    game_goal: GameGoal
    required_dna: RequiredDNA
    dna_placement: DNAPlacement
    hint_all_dna: HintAllDNA

    # Door / transport
    door_lock_rando: DoorLockRando
    doors_to_change: DoorsToChange
    change_doors_to: ChangeDoorsTo
    transport_rando: TransportRando

    # Misc pool / start
    include_boss_pickups: IncludeBossPickups
    start_with_pulse_radar: StartWithPulseRadar

    # Cosmetics / combat
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
    disabled_lights: DisabledLights
    x_starts_released: XStartsReleased

    # Item pool counts
    energy_tanks: EnergyTanks
    energy_parts: EnergyParts
    missile_tanks: MissileTanks
    missile_plus_tanks: MissilePlusTanks
    power_bomb_tanks: PowerBombTanks

    # Ammo / energy yields
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

    # Progressive options
    progressive_beams: ProgressiveBeams
    progressive_charge: ProgressiveCharge
    progressive_missiles: ProgressiveMissiles
    progressive_bombs: ProgressiveBombs
    progressive_suit: ProgressiveSuit
    progressive_spin: ProgressiveSpin

    # Logic options
    starting_location: StartingLocation
    early_morph_ball: EarlyMorphBall

    # Trick/Glitch options
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


# Option groups for better organization on the website
metroid_dread_option_groups = [
    OptionGroup("Goal & DNA", [
        GameGoal,
        RequiredDNA,
        DNAPlacement,
        HintAllDNA,
        ShowDnaInHud,
    ]),
    OptionGroup("Door & Transport Rando", [
        DoorLockRando,
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
    ]),
    OptionGroup("Starting Location", [
        StartingLocation,
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

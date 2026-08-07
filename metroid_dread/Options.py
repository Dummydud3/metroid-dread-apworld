
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

LIGHT_REGIONS = (
    "artaria", "burenia", "cataris", "dairon", "elun",
    "ferenia", "ghavoran", "hanubia", "itorash",
)

class TrickDifficulty(Choice):
    option_disabled = 0
    option_beginner = 1
    option_easy = 2  
    option_medium = 3
    option_hard = 4
    option_expert = 5
    default = 0

class KnowledgeTricks(TrickDifficulty):
    display_name = "Knowledge Tricks"

class MovementTricks(TrickDifficulty):
    display_name = "Movement Tricks"

class CombatTricks(TrickDifficulty):
    display_name = "Combat Tricks"
    default = 1

class PseudoWave(TrickDifficulty):
    display_name = "Pseudo-Wave Beam"

class InfiniteBombJump(TrickDifficulty):
    display_name = "Infinite Bomb Jump (IBJ)"

class WaterBombJump(TrickDifficulty):
    display_name = "Water Bomb Jump (WBJ)"

class WaterSpaceJump(TrickDifficulty):
    display_name = "Water Space Jump (WSJ)"

class SingleWallWallJump(TrickDifficulty):
    display_name = "Single-wall Wall Jump (SWJ)"

class SlideJump(TrickDifficulty):
    display_name = "Slide Jump"

class SpeedBoosterConservation(TrickDifficulty):
    display_name = "Speed Booster Conservation"

class WallJumpTricks(TrickDifficulty):
    display_name = "Wall Jump Tricks"

class HeatColdRuns(TrickDifficulty):
    display_name = "Heat/Cold Runs (Suitless)"

class ReverseGrappleBlock(Toggle):
    display_name = "Reverse Grapple Block"

class DamageBoost(TrickDifficulty):
    display_name = "Damage Boost"

class StandOnFrozenEnemy(TrickDifficulty):
    display_name = "Stand on Frozen Enemy"

class GrappleMovement(TrickDifficulty):
    display_name = "Grapple Movement"

class CrossBombSkip(TrickDifficulty):
    display_name = "Cross Bomb Skip"

class ClimbSlopedTunnels(TrickDifficulty):
    display_name = "Climb Sloped Tunnels"

class ShortBoost(TrickDifficulty):
    display_name = "Short Boost"

class DiffusionAbuse(TrickDifficulty):
    display_name = "Diffusion Abuse"

class FlashShiftSkip(TrickDifficulty):
    display_name = "Flash Shift Skip"

class DiagonalBombJump(TrickDifficulty):
    display_name = "Diagonal Bomb Jump (DBJ)"

class LedgeWarp(TrickDifficulty):
    display_name = "Ledge Warp"

class CrossBombLaunch(TrickDifficulty):
    display_name = "Cross Bomb Launch (CBL)"

class FloorClip(TrickDifficulty):
    display_name = "Floor Clip"

class ClimbSlopedSurfaces(TrickDifficulty):
    display_name = "Climb Sloped Surfaces"

class RequiredDNA(Range):
    display_name = "Required Metroid DNA"
    range_start = 0
    range_end = 12
    default = 0

class DNAPlacement(Choice):
    display_name = "Metroid DNA Placement"
    option_prefer_emmi = 0
    option_prefer_bosses = 1
    option_anywhere = 2
    default = 0

class HintAllDNA(DefaultOnToggle):
    display_name = "Hint All Metroid DNA"

class DoorLockRando(Choice):
    display_name = "Door Lock Randomizer"
    option_vanilla = 0
    option_individual_doors = 1
    alias_off = 0
    alias_randomized = 1
    default = 0

class DoorsToChange(OptionSet):
    display_name = "Doors to Change"
    valid_keys = sorted(ALL_DOOR_WEAKNESS_NAMES)
    default = frozenset(DEFAULT_DOORS_TO_CHANGE)

class ChangeDoorsTo(OptionSet):
    display_name = "Change Doors To"
    valid_keys = sorted(ALL_DOOR_WEAKNESS_NAMES)
    default = frozenset(DEFAULT_CHANGE_DOORS_TO)

class TransportRando(Choice):
    display_name = "Transport Randomizer"
    option_off = 0
    option_randomized = 1
    default = 0

class IncludeBossPickups(DefaultOnToggle):
    display_name = "Include Boss & EMMI Pickups"

class StartWithPulseRadar(DefaultOnToggle):
    display_name = "Start With Pulse Radar"

class ShowBossLifebar(DefaultOnToggle):
    display_name = "Show Boss Lifebar"

class ShowEnemyLife(Toggle):
    display_name = "Show Enemy Life"

class ShowEnemyDamage(Toggle):
    display_name = "Show Enemy Damage"

class ShowPlayerDamage(DefaultOnToggle):
    display_name = "Show Player Damage"

class EnableDeathCounter(DefaultOnToggle):
    display_name = "Death Counter"

class ShowDnaInHud(DefaultOnToggle):
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
    display_name = "Nerf Power Bombs"

class DisabledLights(OptionSet):
    display_name = "Disabled Lights"
    valid_keys = sorted(LIGHT_REGIONS)
    default = frozenset()

class XStartsReleased(Toggle):
    display_name = "X Starts Released"

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

class FlashShiftUpgradeAmount(Range):
    display_name = "Flash Shift Upgrade Amount"
    range_start = 1
    range_end = 10
    default = 1

class FlashShiftUpgradeCount(Range):
    display_name = "Flash Shift Upgrade Count"
    range_start = 1
    range_end = 10
    default = 7

class SpeedBoosterUpgradeCount(Range):
    display_name = "Speed Booster Upgrade Count"
    range_start = 0
    range_end = 10
    default = 0

class FlashShiftIncludedAmmo(Range):
    display_name = "Flash Shift Included Ammo"
    range_start = 0
    range_end = 10
    default = 2

class FlashShiftUpgradeRequiresMainItem(DefaultOnToggle):
    display_name = "Flash Shift Upgrade Requires Main Item"

class EnergyTanks(Range):
    display_name = "Energy Tanks"
    range_start = 0
    range_end = 12
    default = 8

class EnergyParts(Range):
    display_name = "Energy Parts"
    range_start = 0
    range_end = 20
    default = 16

class MissileTanks(Range):
    display_name = "Missile Tanks"
    range_start = 10
    range_end = 50
    default = 35

class MissilePlusTanks(Range):
    display_name = "Missile+ Tanks"
    range_start = 0
    range_end = 15
    default = 10

class PowerBombTanks(Range):
    display_name = "Power Bomb Tanks"
    range_start = 0
    range_end = 15
    default = 12

class ProgressiveBeams(Toggle):
    display_name = "Progressive Beams"
    default = 1

class ProgressiveCharge(Toggle):
    display_name = "Progressive Charge Beam"
    default = 1

class ProgressiveMissiles(Toggle):
    display_name = "Progressive Missiles"
    default = 0

class ProgressiveBombs(Toggle):
    display_name = "Progressive Bombs"
    default = 1

class ProgressiveSuit(Toggle):
    display_name = "Progressive Suit"
    default = 1

class ProgressiveSpin(Toggle):
    display_name = "Progressive Spin"
    default = 1

def _build_starting_location_option():
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
    display_name = "Early Morph Ball"
    default = 0

@dataclass
class MetroidDreadOptions(PerGameCommonOptions):
    accessibility: ItemsAccessibility
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink

    required_dna: RequiredDNA
    dna_placement: DNAPlacement
    hint_all_dna: HintAllDNA

    door_lock_rando: DoorLockRando
    doors_to_change: DoorsToChange
    change_doors_to: ChangeDoorsTo
    transport_rando: TransportRando

    include_boss_pickups: IncludeBossPickups
    start_with_pulse_radar: StartWithPulseRadar

    show_boss_lifebar: ShowBossLifebar
    show_enemy_life: ShowEnemyLife
    show_enemy_damage: ShowEnemyDamage
    show_player_damage: ShowPlayerDamage
    enable_death_counter: EnableDeathCounter
    show_dna_in_hud: ShowDnaInHud
    room_name_display: RoomNameDisplay
    raven_beak_damage_table: RavenBeakDamageTable
    nerf_power_bombs: NerfPowerBombs
    disabled_lights: DisabledLights
    x_starts_released: XStartsReleased

    energy_tanks: EnergyTanks
    energy_parts: EnergyParts
    missile_tanks: MissileTanks
    missile_plus_tanks: MissilePlusTanks
    power_bomb_tanks: PowerBombTanks

    energy_per_tank: EnergyPerTank
    starting_missiles: StartingMissiles
    starting_power_bombs: StartingPowerBombs
    missile_tank_ammo: MissileTankAmmo
    missile_plus_tank_ammo: MissilePlusTankAmmo
    power_bomb_tank_ammo: PowerBombTankAmmo
    flash_shift_upgrade_amount: FlashShiftUpgradeAmount
    flash_shift_upgrade_count: FlashShiftUpgradeCount
    speed_booster_upgrade_count: SpeedBoosterUpgradeCount
    flash_shift_included_ammo: FlashShiftIncludedAmmo
    flash_shift_upgrade_requires_main_item: FlashShiftUpgradeRequiresMainItem

    progressive_beams: ProgressiveBeams
    progressive_charge: ProgressiveCharge
    progressive_missiles: ProgressiveMissiles
    progressive_bombs: ProgressiveBombs
    progressive_suit: ProgressiveSuit
    progressive_spin: ProgressiveSpin

    starting_location: StartingLocation
    early_morph_ball: EarlyMorphBall

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

metroid_dread_option_groups = [
    OptionGroup("Goal & DNA", [
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
        FlashShiftUpgradeCount,
        SpeedBoosterUpgradeCount,
    ]),
    OptionGroup("Ammo & Energy Yields", [
        EnergyPerTank,
        StartingMissiles,
        StartingPowerBombs,
        MissileTankAmmo,
        MissilePlusTankAmmo,
        PowerBombTankAmmo,
        FlashShiftUpgradeAmount,
        FlashShiftIncludedAmmo,
        FlashShiftUpgradeRequiresMainItem,
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

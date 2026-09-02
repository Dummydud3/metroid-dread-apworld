"""
Metroid Bread world implementation for Archipelago

Uses Randovania logic_database as the live reachability engine (see dread_logic.py).
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

# Register launcher component before heavy world imports so a later import
# failure cannot hide "Metroid Bread Client" from the Archipelago Launcher.
try:
    from . import launcher  # noqa: F401
except ImportError:
    pass

from BaseClasses import Tutorial, ItemClassification
from Fill import FillError
from worlds.AutoWorld import World, WebWorld
from .Items import MetroidBreadItem, item_table, item_name_groups
from .Locations import MetroidBreadLocation, location_table, location_name_groups
from .Options import MetroidBreadOptions, metroid_bread_option_groups
from .Regions import create_regions
from .Rules import set_rules
from .dread_logic import DreadLogic
from .starting_locations import get_by_option_key, get_default, load_starting_locations
from . import DoorRando
from . import DoorRandoAssigner
from . import StartKit
from . import TransportRando
from . import victory_clearance
from .logic_options import collect_logic_options_from_options

DREAD_PATCH_EXTRAS_MARKER = "DREAD_PATCH_EXTRAS_JSON:"

_GOAL_NODE = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")

# With combat_tricks disabled, RDV fight templates fall back to raw Damage/energy
# gates. Gold Chozo-X and Raven Beak both require 799 energy on the no-Combat path.
_COMBAT_OFF_MIN_ENERGY = 799

# Share of the world a start has to reach with a full inventory to be usable.
_MIN_START_COVERAGE = 0.8

# Checks that have to be in logic on the starting kit alone. The assumed fill
# needs somewhere to put the very first progression item, and a single check
# leaves it no room to manoeuvre. Starts the kit cannot lift this high get
# relocated rather than handed an ever-growing pile of items.
_MIN_START_CHECKS = StartKit.MIN_START_LOCATIONS

# Graph repair ladder: full re-rolls, then density-biased door softening, then vanilla.
_GRAPH_REROLL_ATTEMPTS = 2
_DOOR_SOFTEN_PASSES = 3
_DOOR_SOFTEN_TOP_K = 6

# Openers tried when testing whether sphere-0 can grow under assumed fill.
_SPHERE_OPENERS = (
    "Morph Ball",
    "Bomb",
    "Charge Beam",
    "Spider Magnet",
    "Grapple Beam",
    "Speed Booster",
    "Phantom Cloak",
    "Wide Beam",
    "Power Bomb",
    "Varia Suit",
    "Flash Shift",
    "Screw Attack",
)

# Boss / EMMI defeat-style pickups (for DNA placement + include_boss_pickups).
_BOSS_EMMI_LOCATION_SUBSTR = (
    "Corpius Arena",
    "Kraid Arena",
    "Drogyga Arena",
    "Escue Arena",
    "Golzuna Arena",
    "Central Unit Access",
    "Purple EMMI Arena",
    "Orange EMMI Introduction",
    "Yellow EMMI Introduction",
    "Proto EMMI Introduction",
    "Above Z-57 Fight - Pickup (Z-57)",
)

_EMMI_DNA_SUBSTR = (
    "Central Unit Access",
    "Purple EMMI Arena",
    "Orange EMMI Introduction",
)

_BOSS_DNA_SUBSTR = (
    "Corpius Arena",
    "Kraid Arena",
    "Drogyga Arena",
    "Escue Arena",
    "Golzuna Arena",
    "Above Z-57 Fight - Pickup (Z-57)",
    "Central Unit Access",
    "Purple EMMI Arena",
    "Orange EMMI Introduction",
)

# Arena / EMMI-defeat sinks (true DNA homes). Central Unit Access is preferred
# for DNA theming but also holds Morph / Speed / Magnet — use it after arenas.
_ARENA_DNA_SUBSTR = (
    "Corpius Arena",
    "Kraid Arena",
    "Drogyga Arena",
    "Escue Arena",
    "Golzuna Arena",
    "Above Z-57 Fight - Pickup (Z-57)",
    "Purple EMMI Arena",
    "Orange EMMI Introduction",
)

# Vanilla intro checks that look "late" vs a non-Artaria start kit sphere but
# are terrible locked-DNA sinks (Ferenia start + Artaria tutorials, etc.).
_STALE_INTRO_DNA_SUBSTR = (
    "Charge Tutorial",
    "Melee Tutorial Room",
    "EMMI Zone First Entrance",
    "Proto EMMI Introduction",
    "First Tutorial",
)


class MetroidBreadWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up Metroid Bread for Archipelago multiworld",
        "English",
        "setup_en.md",
        "setup/en",
        ["Contributors"]
    )]
    theme = "ocean"
    bug_report_page = "https://github.com/ArchipelagoMW/Archipelago/issues"


class MetroidBreadWorld(World):
    """
    Metroid Bread is a 2D action-adventure game and the fifth main installment in the Metroid series.
    """
    game = "Metroid Bread"
    options_dataclass = MetroidBreadOptions
    options: MetroidBreadOptions
    option_groups = metroid_bread_option_groups
    web = MetroidBreadWeb()
    logic: DreadLogic

    item_name_to_id = {name: data.id for name, data in item_table.items() if data.id is not None}
    location_name_to_id = {name: data.id for name, data in location_table.items()}

    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    required_client_version = (0, 4, 0)

    # Filled during generate_early / pre_fill for spoiler → patcher.
    door_assignments: dict
    door_patches: list
    # Reroute set: get interesting locks in post_fill.
    door_shuffled_keys: list
    # Force-unlocked for assumed fill; stay Power Beam after post_fill.
    door_fill_assist_keys: list
    # Start-frontier docks left vanilla.
    door_protected_keys: list
    transport_matching: dict
    elevator_patches: list
    patch_extras: dict
    start_kit: list
    recommended_start_kit: list
    # Boss/EMMI checks kept despite include_boss_pickups=false for DNA capacity.
    forced_boss_locations: set

    def generate_early(self):
        self.logic = DreadLogic(self)
        self.door_assignments = {}
        self.door_patches = []
        self.door_shuffled_keys = []
        self.door_fill_assist_keys = []
        self.door_protected_keys = []
        self.transport_matching = {}
        self.elevator_patches = []
        self.patch_extras = {}
        self.start_kit = []
        self.recommended_start_kit: list = []
        self.forced_boss_locations = set()
        self.early_expand_pins: List[str] = []

        # Raven Beak's access rule already requires >=90% of clearable checks
        # (100% when game_goal is one_hundred_percent; see Rules.py /
        # victory_clearance). Do NOT force accessibility:full — several
        # pickup/event nodes are trick-gated (Speedbooster Conservation,
        # Knowledge, etc.) and stay unreachable with default tricks disabled.
        # Full would make fulfills_accessibility demand those nodes and fail
        # every seed. Coerce Minimal→Items so progression cannot hide behind
        # unreachable checks, while filler/trick-only locations may remain out
        # of logic (ItemsAccessibility). Full is re-checked after the graph is
        # final (tricks + start + door/transport) and downgraded if needed.
        # For 100% goal, non-clearable checks are dropped from the pool instead.
        if self.options.accessibility == "minimal":
            self.options.accessibility.value = self.options.accessibility.option_items
            goal_val = int(self.options.game_goal.value)
            if goal_val == 1:
                goal_note = "100% clearance"
            elif goal_val == 2:
                goal_note = "90% clearance + all bosses"
            else:
                goal_note = "90% clearance"
            print(
                f"[Metroid Bread Player {self.player}] accessibility "
                f"'minimal' upgraded to 'items' (victory implies {goal_note})"
            )

        # Combat-off + tiny energy_per_tank leaves Gold Chozo / Raven Beak
        # logically impossible even with every tank collected.
        self._ensure_combat_energy_viable()

        self._resolve_starting_location()

        # Most valid_starting_location nodes have no pickup in logic on an empty
        # inventory, which the assumed fill cannot work with. Roll the kit that
        # reopens the start (see StartKit) before door rando, so the doors it
        # needs are part of the frontier that stays vanilla.
        self._roll_start_kit()
        vanilla_kit = list(self.start_kit)

        want_doors = self.options.door_lock_rando.value == 1
        want_transports = self.options.transport_rando.value == 1
        if want_doors or want_transports:
            accepted, last_preflight = self._try_graph_rerolls(vanilla_kit)
            if (
                not accepted
                and self.door_assignments
                and self._try_door_soften_passes(vanilla_kit)
            ):
                accepted = True
                last_preflight = None
            if not accepted and (self.door_assignments or self.transport_matching):
                self._revert_randomizers(vanilla_kit)
                if last_preflight is not None:
                    print(
                        f"[Metroid Bread Player {self.player}] "
                        f"door/transport preflight failed after re-rolls"
                        f"{' + door soften' if want_doors else ''} "
                        f"({last_preflight}); reverted to vanilla graph"
                    )

        # Final guard: never ship a kit that can already touch Raven Beak,
        # or a start whose sphere 0 cannot expand under the settled graph.
        if self._start_kit_reaches_goal() or not self._kit_is_ok():
            self._roll_start_kit()

        # Cramped sphere-0 (exactly MIN checks): fill can park non-opening
        # progression in every early slot and softlock. Pin the openers that
        # actually expand the start into local_early_items (see create_items).
        self._compute_early_expand_pins()

        self._compute_forced_boss_locations()
        victory_clearance.assert_graph_preflight(self)
        self._downgrade_full_accessibility_if_needed()
        self._build_patch_extras_base()

    def _build_patch_extras_base(self) -> None:
        room_name = ("NEVER", "ALWAYS", "WITH_FADE")[int(self.options.room_name_display.value)]
        rb_table = ("unmodified", "consistent_low", "consistent_high")[
            int(self.options.raven_beak_damage_table.value)
        ]
        required = int(self.options.required_dna.value)
        goal = int(self.options.game_goal.value)
        # ODR installs the Itorash ADAM door only when required_artifacts > 0.
        # All Bosses reuses that door even with DNA=0 (client grants Metroidnization).
        patch_artifacts = max(required, 1) if goal == 2 else required
        self.patch_extras = {
            "door_patches": self.door_patches,
            "elevators": self.elevator_patches,
            "game_goal": goal,
            # Patch/ODR gate count (may be forced ≥1 for All Bosses).
            "required_artifacts": patch_artifacts,
            # Real YAML DNA count for ADAM hints / client combo gate.
            "required_dna": required,
            "hint_all_dna": bool(self.options.hint_all_dna.value) and required > 0,
            "cosmetic_combat": {
                "bShowBossLifebar": bool(self.options.show_boss_lifebar.value),
                "bShowEnemyLife": bool(self.options.show_enemy_life.value),
                "bShowEnemyDamage": bool(self.options.show_enemy_damage.value),
                "bShowPlayerDamage": bool(self.options.show_player_damage.value),
                "immediate_energy_parts": bool(self.options.immediate_energy_parts.value),
                "constant_environment_damage": {
                    "heat": (
                        int(self.options.constant_heat_damage.value)
                        if int(self.options.constant_heat_damage.value) > 0
                        else None
                    ),
                    "cold": (
                        int(self.options.constant_cold_damage.value)
                        if int(self.options.constant_cold_damage.value) > 0
                        else None
                    ),
                    "lava": (
                        int(self.options.constant_lava_damage.value)
                        if int(self.options.constant_lava_damage.value) > 0
                        else None
                    ),
                },
                "enable_death_counter": bool(self.options.enable_death_counter.value),
                "show_dna_in_hud": bool(self.options.show_dna_in_hud.value) and required > 0,
                "enable_room_name_display": room_name,
                "raven_beak_damage_table_handling": rb_table,
                "nerf_power_bombs": bool(self.options.nerf_power_bombs.value),
                "default_x_released": bool(self.options.x_starts_released.value),
                "energy_per_tank": int(self.options.energy_per_tank.value),
            },
            "disabled_lights": sorted(self.options.disabled_lights.value),
            "starting_missiles": int(self.options.starting_missiles.value),
            "starting_power_bombs": int(self.options.starting_power_bombs.value),
            "missile_tank_ammo": int(self.options.missile_tank_ammo.value),
            "missile_plus_tank_ammo": int(self.options.missile_plus_tank_ammo.value),
            "power_bomb_tank_ammo": int(self.options.power_bomb_tank_ammo.value),
            "vanilla_flash_shift_behaviour": bool(self.options.vanilla_flash_shift_behaviour.value),
            "flash_shift_upgrade_amount": int(self.options.flash_shift_upgrade_amount.value),
            "flash_shift_upgrade_count": int(self.options.flash_shift_upgrade_count.value),
            "flash_shift_included_ammo": int(self.options.flash_shift_included_ammo.value),
            "flash_shift_upgrade_requires_main_item": bool(
                self.options.flash_shift_upgrade_requires_main_item.value
            ),
            "start_with_pulse_radar": bool(self.options.start_with_pulse_radar.value),
            "starting_items": StartKit.odr_starting_items(self.start_kit, options=self.options),
            # Logic-graph form for the client tracker (elevators alone use arrival
            # spawn actors, which are awkward to map back to dock nodes).
            "transport_matching": dict(self.transport_matching or {}),
            "door_assignments": [
                {"scenario": scenario, "actor": actor, "weakness": weakness}
                for (scenario, actor), weakness in sorted(
                    (self.door_assignments or {}).items()
                )
            ],
        }

    def _start_checks(self) -> int:
        return StartKit.start_checks(self, StartKit.kit_counts(self.start_kit))

    def _opener_pool_name(self, name: str) -> str:
        """Map a logic opener to the shuffled pool name under progressive options."""
        if name in ("Wide Beam", "Plasma Beam", "Wave Beam") and self.options.progressive_beams:
            return "Progressive Beam"
        if name in ("Charge Beam", "Diffusion Beam") and self.options.progressive_charge:
            return "Progressive Charge Beam"
        if name in ("Bomb", "Cross Bomb") and self.options.progressive_bombs:
            return "Progressive Bombs"
        if name in ("Varia Suit", "Gravity Suit") and self.options.progressive_suit:
            return "Progressive Suit"
        if name in ("Spin Boost", "Space Jump") and self.options.progressive_spin:
            return "Progressive Spin"
        return name

    def _start_sphere_expands(self) -> bool:
        """
        True when assumed fill can grow past sphere 0.

        Some save rooms only expose two local checks; placing Morph (etc.) there
        still leaves the player trapped (one-ways, door locks, transport cuts).
        Artaria Intro expands; Artaria Save East / Burenia South often do not.
        """
        counts = StartKit.kit_counts(self.start_kit)
        early = self.logic.reachable_pickup_names(counts)
        if len(early) < _MIN_START_CHECKS:
            return False
        sim = dict(counts)
        added = 0
        for name in _SPHERE_OPENERS:
            grant = self._opener_pool_name(name)
            if sim.get(grant, 0) > 0:
                continue
            sim[grant] = sim.get(grant, 0) + 1
            added += 1
            if added >= len(early):
                break
        expanded = self.logic.reachable_pickup_names(sim)
        return len(expanded) >= len(early) + _MIN_START_CHECKS

    def _compute_early_expand_pins(self) -> None:
        """
        When sphere-0 has only ``_MIN_START_CHECKS`` slots, pin the openers that
        expand it into ``local_early_items``.

        Assumed fill may otherwise place Progressive Beam / DNA-adjacent junk in
        every early check (fuzz 434 Artaria Save East + Morph; fuzz 53 Burenia
        South + Screw Attack), leaving Morph/Bomb/Charge nowhere to go.
        Spacious starts (> MIN early checks) leave fill enough room to stumble.
        """
        self.early_expand_pins = []
        counts = StartKit.kit_counts(self.start_kit)
        early = self.logic.reachable_pickup_names(counts)
        if len(early) != _MIN_START_CHECKS:
            return
        if not self._start_sphere_expands():
            return

        sim = dict(counts)
        pins: List[str] = []
        for name in _SPHERE_OPENERS:
            grant = self._opener_pool_name(name)
            if sim.get(grant, 0) > 0:
                continue
            sim[grant] = sim.get(grant, 0) + 1
            pins.append(grant)
            if len(self.logic.reachable_pickup_names(sim)) >= len(early) + _MIN_START_CHECKS:
                break
            if len(pins) >= len(early):
                break
        self.early_expand_pins = pins
        if pins:
            print(
                f"[Metroid Bread Player {self.player}] sphere-0 has only "
                f"{len(early)} check(s); pinning early opener(s): {', '.join(pins)}"
            )

    def _start_kit_reaches_goal(self) -> bool:
        """True when the starting kit alone can already reach Raven Beak."""
        counts = StartKit.kit_counts(self.start_kit)
        nodes = self.logic.get_reachable_nodes(
            self.logic.inventory_from_counts(counts)
        )
        return _GOAL_NODE in nodes

    def _kit_is_ok(self) -> bool:
        return (
            self._start_checks() >= _MIN_START_CHECKS
            and self._start_sphere_expands()
            and not self._start_kit_reaches_goal()
        )

    def _start_kit_budget(self) -> int:
        try:
            return max(0, min(StartKit.MAX_START_KIT, int(self.options.starting_kit_items.value)))
        except Exception:
            return 0

    def _starting_location_key(self) -> str:
        try:
            return str(self.options.starting_location.current_key)
        except Exception:
            return "default"

    def _kit_ok_with(self, kit: list) -> bool:
        prev = list(self.start_kit)
        self.start_kit = list(kit)
        try:
            return self._kit_is_ok()
        finally:
            self.start_kit = prev

    def _assign_start_kit(self, *, base_kit: list = ()) -> None:
        """Set recommended (uncapped) + budgeted start_kit from YAML Starting Items."""
        budget = self._start_kit_budget()
        self.recommended_start_kit = StartKit.build_start_kit(
            self, base_kit=base_kit, max_kit=StartKit.MAX_START_KIT
        )
        if budget <= 0:
            self.start_kit = []
        else:
            self.start_kit = StartKit.build_start_kit(
                self, base_kit=base_kit, max_kit=budget
            )

    def _underbudget_message(self, start_path: str) -> str:
        rec = list(self.recommended_start_kit or [])
        budget = self._start_kit_budget()
        items = ", ".join(rec) if rec else "(none)"
        return (
            f"starting_kit_items={budget} but start {start_path} needs "
            f"{len(rec)} Starting Item(s) ({items}); raise Starting Items to at "
            f"least {len(rec)} or change starting location"
        )

    def _roll_start_kit(self) -> None:
        """Pick the starting kit, relocating if this start cannot be opened.

        YAML ``starting_kit_items`` caps how many majors may be precollected.
        When the budget is too low for the chosen start but a full Start Kit
        would work, log clearly (and FillError for a specific start).
        """
        self._assign_start_kit()
        if self._kit_is_ok():
            return

        original = self.logic.starting_node
        original_path = "/".join(original)
        recommended = list(self.recommended_start_kit)
        budget = self._start_kit_budget()
        recommended_ok = self._kit_ok_with(recommended)
        underbudget = (
            recommended_ok
            and budget < len(recommended)
            and not self._kit_ok_with(self.start_kit)
        )

        if underbudget:
            msg = self._underbudget_message(original_path)
            print(f"[Metroid Bread Player {self.player}] {msg}")
            # Specific YAML start: do not silently relocate — surface the budget miss.
            if self._starting_location_key() not in ("default", "random_save_station"):
                raise FillError(msg)

        original_kit = list(self.start_kit)
        original_rec = list(self.recommended_start_kit)
        candidates = list(load_starting_locations())
        self.random.shuffle(candidates)
        for info in candidates:
            if info.node_id == original or not self._start_is_viable(info.node_id):
                continue
            self.logic.set_starting_node(info.node_id)
            self._assign_start_kit()
            if self._kit_is_ok():
                print(
                    f"[Metroid Bread Player {self.player}] starting location "
                    f"{original_path} has too little in logic to fill from; "
                    f"moved to {info.path}"
                )
                return
            if (
                self._kit_ok_with(self.recommended_start_kit)
                and self._start_kit_budget() < len(self.recommended_start_kit)
            ):
                print(
                    f"[Metroid Bread Player {self.player}] skipped start "
                    f"{info.path}: {self._underbudget_message(info.path)}"
                )

        # Last resort: default Artaria Intro usually expands from an empty kit.
        fallback = get_default()
        if fallback.node_id != original and self._start_is_viable(fallback.node_id):
            self.logic.set_starting_node(fallback.node_id)
            self._assign_start_kit()
            if self._kit_is_ok():
                print(
                    f"[Metroid Bread Player {self.player}] starting location "
                    f"{original_path} cannot expand sphere 0; "
                    f"fell back to {fallback.path}"
                )
                return

        self.logic.set_starting_node(original)
        self.start_kit = original_kit
        self.recommended_start_kit = original_rec
        if underbudget and self._starting_location_key() == "random_save_station":
            # Random exhausted alternatives; still under-budget on original.
            raise FillError(self._underbudget_message(original_path))

    def _has_uncleared_logic_locations(self) -> bool:
        """True if any AP pickup/event stays out of logic with full inventory."""
        # Lazy import: Events↔Items circular import if pulled at module load.
        from collections import defaultdict

        from .Events import event_locations

        nodes = self.logic.get_reachable_nodes(
            self.logic.inventory_from_counts(self._full_inventory_counts())
        )
        for name in self.active_location_names():
            node = self.logic.pickup_nodes.get(name)
            if node is not None and node not in nodes:
                return True
        # One event_item may have several nodes (e.g. normal vs Ledge Warp).
        # Full only needs some path to each event item — not every alternate.
        by_item: dict = defaultdict(list)
        for ev in event_locations:
            by_item[ev.event_item].append((ev.game_region, ev.area, ev.node))
        for locs in by_item.values():
            if not any(loc in nodes for loc in locs):
                return True
        return False

    def _downgrade_full_accessibility_if_needed(self) -> None:
        if self.options.accessibility != "full":
            return
        if not self._has_uncleared_logic_locations():
            return
        self.options.accessibility.value = self.options.accessibility.option_items
        print(
            f"[Metroid Bread Player {self.player}] accessibility "
            f"'full' downgraded to 'items' (some checks need tricks that "
            f"are disabled)"
        )

    def _reset_logic_graph(self, kit: list) -> None:
        """Rebuild a vanilla logic graph at the current start (clear rando)."""
        node = self.logic.starting_node
        self.logic = DreadLogic(self)
        self.logic.set_starting_node(node)
        self.door_assignments = {}
        self.door_patches = []
        self.door_shuffled_keys = []
        self.door_fill_assist_keys = []
        self.door_protected_keys = []
        self.transport_matching = {}
        self.elevator_patches = []
        self.start_kit = list(kit)

    def _roll_door_and_transport_rando(self) -> None:
        """Apply one door-lock / transport shuffle onto the current vanilla graph.

        Individual Doors: classify docks → fill-assist unlocks + reroute unlocks;
        interesting locks are assigned in ``post_fill`` on the reroute set only.
        """
        self.door_assignments = {}
        self.door_patches = []
        self.door_shuffled_keys = []
        self.door_fill_assist_keys = []
        self.door_protected_keys = []
        self.transport_matching = {}
        self.elevator_patches = []

        if self.options.door_lock_rando.value == 1:
            active = set(self.active_location_names())
            result = DoorRandoAssigner.pre_fill_roll(
                self.logic,
                self.random,
                doors_to_change=self.options.doors_to_change.value,
                change_doors_to=self.options.change_doors_to.value,
                start_counts=StartKit.kit_counts(self.start_kit),
                active=active,
            )
            self.door_assignments = dict(result.assignments)
            self.door_shuffled_keys = list(result.reroute_keys)
            self.door_fill_assist_keys = list(result.fill_assist_keys)
            self.door_protected_keys = list(result.protected_keys)
            DoorRando.apply_assignments(self.logic.parser, self.door_assignments)
            self.door_patches = DoorRando.assignments_to_door_patches(
                self.door_assignments
            )
            print(
                f"[Metroid Bread Player {self.player}] door pre-fill: "
                f"assist={len(self.door_fill_assist_keys)} "
                f"reroute={len(self.door_shuffled_keys)} "
                f"protected={len(self.door_protected_keys)}"
            )

        if self.options.transport_rando.value == 1:
            matching, transports = TransportRando.roll_connected_matching(
                self.logic, self.random, mode="randomized"
            )
            self.transport_matching = matching
            if matching:
                TransportRando.apply_matching(self.logic.parser, transports, matching)
                self.elevator_patches = TransportRando.matching_to_elevators(
                    matching, transports
                )

    def _reapply_door_and_transport(self, vanilla_kit: list) -> None:
        """Reset to vanilla logic, then re-apply stored transport + door assignments."""
        matching = dict(self.transport_matching or {})
        doors = dict(self.door_assignments or {})
        shuffled = list(self.door_shuffled_keys or [])
        assist = list(self.door_fill_assist_keys or [])
        protected = list(self.door_protected_keys or [])
        self._reset_logic_graph(vanilla_kit)
        self.transport_matching = matching
        self.door_assignments = doors
        self.door_shuffled_keys = shuffled
        self.door_fill_assist_keys = assist
        self.door_protected_keys = protected
        if matching:
            transports = TransportRando.collect_transports(self.logic.parser)
            TransportRando.apply_matching(self.logic.parser, transports, matching)
            self.elevator_patches = TransportRando.matching_to_elevators(
                matching, transports
            )
        else:
            self.elevator_patches = []
        if doors:
            DoorRando.apply_assignments(self.logic.parser, doors)
            self.door_patches = DoorRando.assignments_to_door_patches(doors)
        else:
            self.door_patches = []
        self.logic.rebuild_graph()
        self._assign_start_kit(base_kit=vanilla_kit)

    def _graph_state_acceptable(self) -> Optional[FillError]:
        """None when start kit + preflight are OK; otherwise the failure reason."""
        if self._start_checks() < _MIN_START_CHECKS or self._start_kit_reaches_goal():
            return FillError(
                "start kit too weak or already reaches Raven Beak "
                "under rolled doors/transports"
            )
        if not self._start_sphere_expands():
            return FillError(
                "start sphere 0 does not expand after placing early progression "
                "under rolled doors/transports"
            )
        try:
            victory_clearance.assert_graph_preflight(self)
        except FillError as exc:
            return exc
        return None

    def _try_graph_rerolls(self, vanilla_kit: list) -> tuple:
        """Full door/transport re-rolls. Returns (accepted, last_error)."""
        last_preflight: Optional[FillError] = None
        for attempt in range(_GRAPH_REROLL_ATTEMPTS):
            if attempt > 0:
                self._reset_logic_graph(vanilla_kit)
            self._roll_door_and_transport_rando()
            if not (self.door_assignments or self.transport_matching):
                return False, last_preflight
            self.logic.rebuild_graph()
            self._assign_start_kit(base_kit=vanilla_kit)
            err = self._graph_state_acceptable()
            if err is None:
                if attempt > 0:
                    print(
                        f"[Metroid Bread Player {self.player}] "
                        f"accepted door/transport graph on re-roll "
                        f"{attempt + 1}/{_GRAPH_REROLL_ATTEMPTS}"
                    )
                return True, None
            last_preflight = err
        return False, last_preflight

    def _try_door_soften_passes(self, vanilla_kit: list) -> bool:
        """
        Density-biased door softening after re-rolls failed.

        Softens doors that unlock the most new checks (start-kit inventory first,
        full inventory as tie-break context via goal bonus) then re-applies the
        graph. Returns True when preflight accepts.
        """
        if not self.door_assignments:
            return False

        active = set(self.active_location_names())
        pickup_nodes = {
            name: node
            for name, node in self.logic.pickup_nodes.items()
            if name in active
        }
        protected = DoorRando.start_frontier_keys(
            self.logic, self.logic.inventory_from_counts(StartKit.kit_counts(vanilla_kit))
        )
        # Never soften fill-assist unlocks or protected frontier docks.
        protected |= set(self.door_protected_keys or [])
        protected |= set(self.door_fill_assist_keys or [])

        for pass_i in range(_DOOR_SOFTEN_PASSES):
            # Score with start-kit inventory so early checks open for fill.
            kit_counts = StartKit.kit_counts(self.start_kit or vanilla_kit)
            scored = DoorRando.score_doors_by_new_checks(
                self.logic,
                self.door_assignments,
                pickup_nodes=pickup_nodes,
                active_names=active,
                inventory_counts=kit_counts,
                goal_node=_GOAL_NODE,
                protected=protected,
            )
            # If start-kit scoring is flat, retry scoring with a fuller inventory
            # so we still bias opens toward clearable density / Raven Beak.
            if not scored or all(score <= 0 for score, _key in scored):
                scored = DoorRando.score_doors_by_new_checks(
                    self.logic,
                    self.door_assignments,
                    pickup_nodes=pickup_nodes,
                    active_names=active,
                    inventory_counts=self._full_inventory_counts(),
                    goal_node=_GOAL_NODE,
                    protected=protected,
                )
            keys = DoorRando.pick_doors_to_soften(
                scored,
                top_k=_DOOR_SOFTEN_TOP_K,
                assignments=self.door_assignments,
            )
            if not keys:
                return False
            changed = DoorRando.soften_assignments(self.door_assignments, keys)
            if not changed:
                return False
            self._reapply_door_and_transport(vanilla_kit)
            err = self._graph_state_acceptable()
            print(
                f"[Metroid Bread Player {self.player}] door soften pass "
                f"{pass_i + 1}/{_DOOR_SOFTEN_PASSES}: opened {len(changed)} "
                f"door(s) toward denser checks "
                f"(assist={len(self.door_fill_assist_keys or [])} "
                f"reroute={len(self.door_shuffled_keys or [])} still tracked)"
                f"{'' if err is None else f' (still failing: {err})'}"
            )
            if err is None:
                return True
        return False

    def attempt_fill_with_door_repair(self, distribute_fn) -> None:
        """
        Run assumed fill; on FillError, soften density doors and retry fill.

        `distribute_fn` should be ``lambda: distribute_items_restrictive(mw)``.
        Only safe when this world still owns mutable door assignments and the
        multiworld itempool/locations can be refilled (tests/stress helpers).
        Stock Archipelago Generate relies on generate_early softening instead.
        """
        last_exc: Optional[BaseException] = None
        vanilla_kit = list(self.start_kit)
        for attempt in range(1 + _DOOR_SOFTEN_PASSES):
            try:
                distribute_fn()
                self.post_fill()
                return
            except FillError as exc:
                last_exc = exc
                if not self.door_assignments or attempt >= _DOOR_SOFTEN_PASSES:
                    break
                active = set(self.active_location_names())
                protected = DoorRando.start_frontier_keys(
                    self.logic,
                    self.logic.inventory_from_counts(
                        StartKit.kit_counts(vanilla_kit)
                    ),
                )
                protected |= set(self.door_protected_keys or [])
                protected |= set(self.door_fill_assist_keys or [])
                scored = DoorRando.score_doors_by_new_checks(
                    self.logic,
                    self.door_assignments,
                    pickup_nodes={
                        n: node for n, node in self.logic.pickup_nodes.items()
                        if n in active
                    },
                    active_names=active,
                    inventory_counts=self._full_inventory_counts(),
                    goal_node=_GOAL_NODE,
                    protected=protected,
                )
                keys = DoorRando.pick_doors_to_soften(
                    scored,
                    top_k=_DOOR_SOFTEN_TOP_K,
                    assignments=self.door_assignments,
                )
                if not DoorRando.soften_assignments(self.door_assignments, keys):
                    break
                # Door mutations after regions exist still update logic + patches;
                # fill retry requires the caller to reset placement state.
                DoorRando.apply_assignments(self.logic.parser, self.door_assignments)
                self.door_patches = DoorRando.assignments_to_door_patches(
                    self.door_assignments
                )
                self.logic.rebuild_graph()
                if self.patch_extras is not None:
                    self.patch_extras["door_patches"] = self.door_patches
                print(
                    f"[Metroid Bread Player {self.player}] fill failed "
                    f"({exc}); softened {len(keys)} door(s) for retry "
                    f"{attempt + 1}/{_DOOR_SOFTEN_PASSES}"
                )
        if last_exc is not None:
            raise last_exc

    def _revert_randomizers(self, vanilla_kit: list) -> None:
        """Drop door / transport rando and go back to the vanilla graph."""
        self._reset_logic_graph(vanilla_kit)
        print(
            f"[Metroid Bread Player {self.player}] door / transport rando left "
            f"{'/'.join(self.logic.starting_node)} with too little in logic; "
            f"reverted to vanilla"
        )

    def _compute_forced_boss_locations(self) -> None:
        """
        When boss/EMMI pickups are excluded, still keep enough preferred DNA
        sinks active so prefer_emmi / prefer_bosses can place (any DNA count).
        """
        self.forced_boss_locations = set()
        if self.options.include_boss_pickups:
            return
        needed = int(self.options.required_dna.value)
        mode = int(self.options.dna_placement.value)
        if needed <= 0 or mode == 2:
            return
        substrs = _EMMI_DNA_SUBSTR if mode == 0 else _BOSS_DNA_SUBSTR
        sinks = [n for n in location_table if any(s in n for s in substrs)]
        self.random.shuffle(sinks)
        # Keep at least `needed` sink checks (and a small buffer) available.
        keep = min(len(sinks), max(needed + 2, needed))
        self.forced_boss_locations = set(sinks[:keep])
        if self.forced_boss_locations:
            print(
                f"[Metroid Bread Player {self.player}] keeping "
                f"{len(self.forced_boss_locations)} boss/EMMI check(s) as DNA "
                f"sinks (include_boss_pickups is off)"
            )

    def _max_obtainable_energy(self) -> int:
        """Peak HP from energy_per_tank × tanks/parts in the YAML pool."""
        ept = max(1, int(self.options.energy_per_tank.value))
        tanks = int(self.options.energy_tanks.value)
        parts = int(self.options.energy_parts.value)
        return int((ept - 1) + tanks * ept + parts * (ept / 4.0))

    def _ensure_combat_energy_viable(self) -> None:
        """
        Combat tricks disabled → fights use raw Damage/energy gates.

        Gold Chozo-X and Raven Beak need 799 energy on that path. Raise
        energy_per_tank so *base* HP (no tanks collected) clears the gate —
        otherwise assumed fill can bury every Energy Tank behind those fights
        and softlock. If the option cap still cannot reach the threshold, fall
        back to combat beginner.
        """
        if int(self.options.combat_tricks.value) > 0:
            return
        need = _COMBAT_OFF_MIN_ENERGY
        ept = max(1, int(self.options.energy_per_tank.value))
        if ept - 1 >= need:
            return
        new_ept = min(1000, need + 1)
        if new_ept > ept:
            self.options.energy_per_tank.value = new_ept
            print(
                f"[Metroid Bread Player {self.player}] combat tricks disabled: "
                f"raised energy_per_tank {ept} -> {new_ept} so base HP can clear "
                f"Gold Chozo / Raven Beak (need >={need})"
            )
        if int(self.options.energy_per_tank.value) - 1 < need:
            self.options.combat_tricks.value = 1
            print(
                f"[Metroid Bread Player {self.player}] combat tricks set to "
                f"beginner - energy_per_tank cannot provide >={need} base HP"
            )

    def _full_inventory_counts(self) -> dict:
        """Every real item at quantities past progressive / DNA thresholds.

        Energy tanks/parts use the YAML pool sizes so preflight matches the
        energy the seed can actually obtain (important when combat is off).
        """
        counts = {
            name: 12 for name, data in item_table.items() if data.id is not None
        }
        counts["Energy Tank"] = int(self.options.energy_tanks.value)
        counts["Energy Part"] = int(self.options.energy_parts.value)
        dna = int(self.options.required_dna.value)
        if dna > 0:
            counts["Metroid DNA"] = max(dna, counts.get("Metroid DNA", 0))
        return counts

    def start_coverage(self, node) -> float:
        """Fraction of active checks in logic from `node` with everything collected.

        Returns 0.0 when Raven Beak is unreachable. A few RDV
        valid_starting_location nodes (Elun, Cataris Save Station East, the
        Itorash elevator) sit behind one-way transitions, so a seed started
        there can never be completed no matter how the items fall.
        """
        previous = self.logic.starting_node
        try:
            self.logic.set_starting_node(node)
            nodes = self.logic.get_reachable_nodes(
                self.logic.inventory_from_counts(self._full_inventory_counts())
            )
        finally:
            self.logic.set_starting_node(previous)
        if _GOAL_NODE not in nodes:
            return 0.0
        active = set(self.active_location_names())
        if not active:
            return 0.0
        in_logic = sum(
            1 for name, pickup in self.logic.pickup_nodes.items()
            if pickup in nodes and name in active
        )
        return in_logic / len(active)

    def _start_is_viable(self, node) -> bool:
        return self.start_coverage(node) >= _MIN_START_COVERAGE

    def _resolve_starting_location(self) -> None:
        """Apply YAML starting_location: default | random_save_station | specific."""
        key = self.options.starting_location.current_key
        starts = load_starting_locations()

        if key == "random_save_station":
            if not starts:
                start_nodes = self.logic.parser.get_starting_nodes()
                if start_nodes:
                    self.logic.set_starting_node(self.random.choice(start_nodes))
                return
            shuffled = list(starts)
            self.random.shuffle(shuffled)
            info = next((s for s in shuffled if self._start_is_viable(s.node_id)), shuffled[0])
        elif key == "default":
            info = get_default()
        else:
            info = get_by_option_key(key)
            if info is None:
                raise Exception(
                    f"Unknown Metroid Bread starting_location option: {key!r}"
                )

        if not self._start_is_viable(info.node_id):
            fallback = next(
                (s for s in starts if self._start_is_viable(s.node_id)), None
            ) or get_default()
            print(
                f"[Metroid Bread Player {self.player}] starting location "
                f"{info.path} cannot reach Raven Beak; falling back to {fallback.path}"
            )
            info = fallback

        self.logic.set_starting_node(info.node_id)

    def create_regions(self):
        if not hasattr(self, "logic"):
            self.logic = DreadLogic(self)
        create_regions(self.multiworld, self.player)

    def create_items(self):
        itempool = []
        items_to_create = {}

        if self.options.progressive_beams:
            items_to_create["Progressive Beam"] = 3
        else:
            items_to_create["Wide Beam"] = 1
            items_to_create["Plasma Beam"] = 1
            items_to_create["Wave Beam"] = 1

        if self.options.progressive_charge:
            items_to_create["Progressive Charge Beam"] = 2
        else:
            items_to_create["Charge Beam"] = 1
            items_to_create["Diffusion Beam"] = 1

        if self.options.progressive_missiles:
            items_to_create["Progressive Missiles"] = 2
        else:
            items_to_create["Super Missile"] = 1
            items_to_create["Ice Missile"] = 1
        items_to_create["Storm Missile"] = 1

        if self.options.progressive_bombs:
            items_to_create["Progressive Bombs"] = 2
        else:
            items_to_create["Bomb"] = 1
            items_to_create["Cross Bomb"] = 1

        if self.options.progressive_suit:
            items_to_create["Progressive Suit"] = 2
        else:
            items_to_create["Varia Suit"] = 1
            items_to_create["Gravity Suit"] = 1

        if self.options.progressive_spin:
            items_to_create["Progressive Spin"] = 2
        else:
            items_to_create["Spin Boost"] = 1
            items_to_create["Space Jump"] = 1

        major_items = [
            "Grapple Beam", "Phantom Cloak",
            "Morph Ball", "Power Bomb", "Spider Magnet",
            "Speed Booster", "Screw Attack",
        ]
        if self.options.start_with_pulse_radar:
            self.multiworld.push_precollected(self.create_item("Pulse Radar"))
        else:
            major_items.append("Pulse Radar")
        for item_name in major_items:
            if item_name not in items_to_create:
                items_to_create[item_name] = 1

        from .flash_shift import plan_from_options

        fs_plan = plan_from_options(self.options)
        if fs_plan["main_count"] > 0:
            items_to_create["Flash Shift"] = int(fs_plan["main_count"])
        # Vanilla OFF: always schedule all N upgrades (guaranteed pool members).
        fs_upgrade_planned = int(fs_plan["upgrade_count"] or 0)
        if fs_upgrade_planned > 0:
            items_to_create["Flash Shift Upgrade"] = fs_upgrade_planned
        sb_up = int(self.options.speed_booster_upgrade_count.value)
        if sb_up > 0:
            items_to_create["Speed Booster Upgrade"] = sb_up

        items_to_create["Energy Tank"] = self.options.energy_tanks.value
        items_to_create["Energy Part"] = self.options.energy_parts.value
        items_to_create["Missile Tank"] = self.options.missile_tanks.value
        items_to_create["Missile+ Tank"] = self.options.missile_plus_tanks.value
        items_to_create["Power Bomb Tank"] = self.options.power_bomb_tanks.value

        required_dna = int(self.options.required_dna.value)
        if required_dna > 0:
            items_to_create["Metroid DNA"] = required_dna

        # The start kit is handed to the player instead of being shuffled; the
        # filler top-up below refills the freed locations.
        granted = []
        for pool_item in self.start_kit:
            if items_to_create.get(pool_item, 0) <= 0:
                continue
            items_to_create[pool_item] -= 1
            self.multiworld.push_precollected(self.create_item(pool_item))
            granted.append(pool_item)
        self.start_kit = granted
        self.patch_extras["starting_items"] = StartKit.odr_starting_items(
            granted, options=self.options
        )

        # Guarantee Flash Shift Upgrade placement: displace Missile Tank filler 1:1
        # for every upgrade still going into the shuffled pool (not start-kit).
        # Upgrades are never optional leftovers that padding/trim can drop.
        fs_upgrades_in_pool = int(items_to_create.get("Flash Shift Upgrade", 0) or 0)
        if fs_upgrades_in_pool > 0:
            mt = int(items_to_create.get("Missile Tank", 0) or 0)
            items_to_create["Missile Tank"] = max(0, mt - fs_upgrades_in_pool)

        for item_name, count in items_to_create.items():
            for _ in range(count):
                itempool.append(self.create_item(item_name))

        # Combat-off: Energy Tanks/Parts gate Gold Chozo / Raven Beak (Damage
        # requirements). Treat them as progression so assumed fill cannot bury
        # them behind those fights.
        if int(self.options.combat_tricks.value) == 0:
            for item in itempool:
                if item.name in ("Energy Tank", "Energy Part"):
                    item.classification = ItemClassification.progression

        # Progressive Flash Shift (no main): first upgrade unlocks the ability, so it
        # must be advancement. Later upgrades stay filler chain-ammo like missiles.
        if (
            not fs_plan["vanilla"]
            and not fs_plan["require_main"]
            and fs_upgrades_in_pool > 0
        ):
            for item in itempool:
                if item.name == "Flash Shift Upgrade":
                    item.classification = ItemClassification.progression
                    break

        if self.options.early_morph_ball and items_to_create.get("Morph Ball", 0) > 0:
            self.multiworld.local_early_items[self.player]["Morph Ball"] = 1

        # Cramped sphere-0: force the openers that expand the start into early
        # spheres so fill cannot fill both early slots with Progressive Beam etc.
        for name in getattr(self, "early_expand_pins", []) or []:
            if items_to_create.get(name, 0) > 0:
                self.multiworld.local_early_items[self.player][name] = max(
                    self.multiworld.local_early_items[self.player].get(name, 0),
                    1,
                )

        # Exclude boss/EMMI checks → fewer locations, trim/pad filler accordingly.
        # Never trim Flash Shift Upgrade — only Missile Tank (padding bucket), then
        # Power Bomb Tank as a last resort.
        active_locations = self.active_location_names()
        total_locations = len(active_locations)
        items_created = len(itempool)

        if items_created < total_locations:
            for _ in range(total_locations - items_created):
                itempool.append(self.create_item("Missile Tank"))
        elif items_created > total_locations:
            extras = items_created - total_locations
            trim_order = ("Missile Tank", "Power Bomb Tank")
            kept = []
            trimmed = 0
            for item in reversed(itempool):
                if (
                    trimmed < extras
                    and item.name in trim_order
                    and item.name != "Flash Shift Upgrade"
                    and not item.advancement
                ):
                    trimmed += 1
                    continue
                kept.append(item)
            itempool = list(reversed(kept))
            if len(itempool) > total_locations:
                raise Exception(
                    f"Too many items created: {len(itempool)} items for {total_locations} locations"
                )

        # Sanity: every non-start-kit upgrade must still be in the pool.
        upgrades_kept = sum(1 for i in itempool if i.name == "Flash Shift Upgrade")
        if upgrades_kept != fs_upgrades_in_pool:
            raise Exception(
                f"Flash Shift Upgrade pool guarantee failed: expected "
                f"{fs_upgrades_in_pool}, kept {upgrades_kept}"
            )

        # Hub Map Tracker: total items available to this player (shuffled + kit).
        tracker_pool: Dict[str, int] = {}
        for item in itempool:
            tracker_pool[item.name] = tracker_pool.get(item.name, 0) + 1
        for kit_name in self.start_kit:
            tracker_pool[kit_name] = tracker_pool.get(kit_name, 0) + 1
        if self.options.start_with_pulse_radar:
            tracker_pool["Pulse Radar"] = tracker_pool.get("Pulse Radar", 0) + 1
        self.patch_extras["tracker_item_pool"] = {
            name: count for name, count in tracker_pool.items() if count > 0
        }

        self.multiworld.itempool += itempool

    def active_location_names(self) -> List[str]:
        names = list(location_table.keys())
        if not self.options.include_boss_pickups:
            forced = getattr(self, "forced_boss_locations", set()) or set()
            names = [
                n for n in names
                if n in forced or not any(s in n for s in _BOSS_EMMI_LOCATION_SUBSTR)
            ]
        # 100% goal: only ship checks reachable with a full inventory under the
        # rolled logic so the client can require every slot check without softlock.
        if int(self.options.game_goal.value) == 1 and getattr(self, "logic", None):
            reachable = self.logic.get_reachable_nodes(
                self.logic.inventory_from_counts(self._full_inventory_counts())
            )
            names = [
                n for n in names
                if self.logic.pickup_nodes.get(n) in reachable
            ]
        return names

    def create_item(self, name: str) -> MetroidBreadItem:
        item_data = item_table[name]
        if item_data.id is None:
            return MetroidBreadItem(name, item_data.classification, None, self.player)
        return MetroidBreadItem(name, item_data.classification, item_data.id, self.player)

    def set_rules(self):
        set_rules(self.multiworld, self.player, self.options)
        # Remove inactive pickup locations (boss/EMMI off, or non-clearable under 100%).
        active = set(self.active_location_names())
        for name in list(location_table.keys()):
            if name in active:
                continue
            try:
                loc = self.multiworld.get_location(name, self.player)
            except KeyError:
                continue
            if loc.parent_region:
                loc.parent_region.locations.remove(loc)

    def pre_fill(self) -> None:
        self._pre_place_dna()
        victory_clearance.assert_location_capacity(self)

    def post_fill(self) -> None:
        """Assign reach-gated door locks (Individual Doors), then clearance check."""
        if self.options.door_lock_rando.value == 1 and (
            self.door_shuffled_keys or self.door_fill_assist_keys
        ):
            self.door_assignments = DoorRandoAssigner.post_fill_assign(
                self,
                self.door_shuffled_keys,
                self.random,
                change_doors_to=self.options.change_doors_to.value,
                fill_assist_keys=self.door_fill_assist_keys,
            )
            DoorRando.apply_assignments(self.logic.parser, self.door_assignments)
            self.door_patches = DoorRando.assignments_to_door_patches(
                self.door_assignments
            )
            self.logic.rebuild_graph()
            openish = sum(
                1
                for w in (self.door_assignments or {}).values()
                if w in ("Power Beam Door", "Access Open")
            )
            print(
                f"[Metroid Bread Player {self.player}] door post-fill: "
                f"{len(self.door_shuffled_keys or [])} reroute lock(s), "
                f"{len(self.door_fill_assist_keys or [])} assist unlock(s), "
                f"{openish} still Power Beam/Open among assigned"
            )
            if self.patch_extras is not None:
                self.patch_extras["door_patches"] = self.door_patches
                self.patch_extras["door_assignments"] = [
                    {"scenario": scenario, "actor": actor, "weakness": weakness}
                    for (scenario, actor), weakness in sorted(
                        (self.door_assignments or {}).items()
                    )
                ]
                self.patch_extras["door_fill_assist"] = [
                    {"scenario": s, "actor": a}
                    for (s, a) in (self.door_fill_assist_keys or [])
                ]
                self.patch_extras["door_reroute"] = [
                    {"scenario": s, "actor": a}
                    for (s, a) in (self.door_shuffled_keys or [])
                ]
        victory_clearance.assert_victory_implies_full_clearance(self)

    def _dna_placement_substrs(self) -> tuple:
        mode = int(self.options.dna_placement.value)
        if mode == 0:
            return _EMMI_DNA_SUBSTR
        if mode == 1:
            return _BOSS_DNA_SUBSTR
        return ()

    def _dna_frontier_names(self) -> set:
        """
        Start-kit sphere plus a one-step opener expansion.

        DNA must not consume these when alternatives exist: they are the fill
        frontier for Morph / early progression. Sphere-0 alone is not enough —
        Artaria tutorials are outside a Ferenia start sphere yet still starve fill.
        """
        counts = StartKit.kit_counts(self.start_kit)
        frontier = set(self.logic.reachable_pickup_names(counts))
        sim = dict(counts)
        openers = (
            "Morph Ball",
            "Bomb",
            "Charge Beam",
            "Spider Magnet",
            "Grapple Beam",
            "Speed Booster",
            "Phantom Cloak",
            "Wide Beam",
            "Power Bomb",
            "Varia Suit",
            "Flash Shift",
            "Screw Attack",
            "Space Jump",
            "Spin Boost",
            "Wave Beam",
            "Plasma Beam",
            "Ice Missile",
            "Storm Missile",
        )
        for name in openers:
            grant = name
            if name in ("Wide Beam", "Plasma Beam", "Wave Beam") and self.options.progressive_beams:
                grant = "Progressive Beam"
            elif name in ("Charge Beam", "Diffusion Beam") and self.options.progressive_charge:
                grant = "Progressive Charge Beam"
            elif name in ("Bomb", "Cross Bomb") and self.options.progressive_bombs:
                grant = "Progressive Bombs"
            elif name in ("Varia Suit", "Gravity Suit") and self.options.progressive_suit:
                grant = "Progressive Suit"
            elif name in ("Spin Boost", "Space Jump") and self.options.progressive_spin:
                grant = "Progressive Spin"
            if sim.get(grant, 0) > 0:
                continue
            sim[grant] = sim.get(grant, 0) + 1
        frontier.update(self.logic.reachable_pickup_names(sim))
        return frontier

    def _dna_stale_intro_names(self, names: set) -> set:
        """Wrong-region vanilla intros: late vs start kit, but awful DNA sinks."""
        start_region = self.logic.starting_node[0]
        stale = set()
        for name in names:
            if start_region != "Artaria" and any(s in name for s in _STALE_INTRO_DNA_SUBSTR):
                stale.add(name)
                continue
            # Any region's named tutorial pickup when that is not the start region.
            if "Tutorial" in name and not name.startswith(f"{start_region} -"):
                stale.add(name)
        return stale

    def _dna_candidate_locations(self) -> List[str]:
        """
        Ordered DNA targets: eventually-reachable preferred sinks first, then
        other eventually-reachable actives. Unreachable / inactive checks omitted.
        """
        mode = int(self.options.dna_placement.value)
        active = set(self.active_location_names())
        full = set(self.logic.reachable_pickup_names(self._full_inventory_counts()))
        usable = [n for n in location_table if n in active and n in full]
        if mode == 2:
            return usable

        substrs = self._dna_placement_substrs()
        preferred = [n for n in usable if any(s in n for s in substrs)]
        # Prefer true arena/EMMI-defeat sinks before Central Unit Access (Morph etc.).
        arenas = [n for n in preferred if any(s in n for s in _ARENA_DNA_SUBSTR)]
        cu_access = [n for n in preferred if n not in arenas]
        preferred = arenas + cu_access
        seen = set(preferred)
        # Preferred first, then other eventually-reachable actives (softening).
        return preferred + [n for n in usable if n not in seen]

    def _pre_place_dna(self) -> None:
        n = int(self.options.required_dna.value)
        if n <= 0 or int(self.options.dna_placement.value) == 2:
            return
        candidates = self._dna_candidate_locations()
        if len(candidates) < n:
            return

        substrs = self._dna_placement_substrs()
        preferred = {name for name in candidates if any(s in name for s in substrs)}
        frontier = self._dna_frontier_names()
        stale = self._dna_stale_intro_names(set(candidates))

        def _tier(name: str) -> int:
            # Lower = better DNA sink for fill health.
            is_pref = name in preferred
            is_arena = any(s in name for s in _ARENA_DNA_SUBSTR)
            in_frontier = name in frontier
            is_stale = name in stale
            if is_stale and not is_pref:
                return 5
            if in_frontier and not is_pref:
                return 4
            if in_frontier and is_pref:
                return 3
            if is_pref and is_arena:
                return 0
            if is_pref:
                return 1
            return 2

        buckets: dict[int, list] = {i: [] for i in range(6)}
        for name in candidates:
            buckets[_tier(name)].append(name)
        ordered: List[str] = []
        for i in range(6):
            bucket = buckets[i]
            self.random.shuffle(bucket)
            ordered.extend(bucket)
        candidates = ordered

        dna_items = [
            item for item in self.multiworld.itempool
            if item.player == self.player and item.name == "Metroid DNA"
        ]
        if len(dna_items) < n:
            return
        for i in range(n):
            loc = self.multiworld.get_location(candidates[i], self.player)
            item = dna_items[i]
            loc.place_locked_item(item)
            self.multiworld.itempool.remove(item)

    def generate_basic(self):
        kit = ", ".join(StartKit.logical_names(self.start_kit)) or "none"
        print(
            f"[Metroid Bread Player {self.player}] "
            f"RDV logic graph active (start={self.logic.starting_node}); "
            f"doors={len(self.door_patches)} elevators={len(self.elevator_patches)} "
            f"dna={self.options.required_dna.value} start_kit={kit}"
        )

    def fill_slot_data(self):
        region, area, node = self.logic.starting_node
        extras = dict(self.patch_extras or {})
        # DNA placement list for nav hints (same data write_spoiler appends).
        if extras.get("hint_all_dna"):
            dna_locs = []
            for loc in self.multiworld.get_locations(self.player):
                if (
                    loc.item
                    and loc.item.player == self.player
                    and loc.item.name == "Metroid DNA"
                ):
                    dna_locs.append(loc.name)
            if dna_locs:
                extras["dna_locations"] = dna_locs
        # Trick / ammo preset for the client tracker (must match generation logic).
        logic_options = collect_logic_options_from_options(self.options)
        extras["logic_options"] = dict(logic_options)
        tracker_pool = extras.get("tracker_item_pool")
        if not isinstance(tracker_pool, dict):
            tracker_pool = {}
        slot_data = {
            "death_link": self.options.death_link.value,
            "game_goal": int(self.options.game_goal.value),
            "required_dna": int(self.options.required_dna.value),
            "starting_location": {
                "region": region,
                "area": area,
                "node": node,
                "path": f"{region}/{area}/{node}",
            },
            "energy_per_tank": int(self.options.energy_per_tank.value),
            "door_lock_rando": int(self.options.door_lock_rando.value),
            "transport_rando": int(self.options.transport_rando.value),
            "logic_options": dict(logic_options),
            # Exact seed pool for Hub Map Tracker icon filtering (also in patch_extras).
            "tracker_item_pool": dict(tracker_pool),
            # Full patch payload so clients can rebuild the mod without a local spoiler.
            "patch_extras": extras,
        }
        return slot_data

    def write_spoiler_header(self, spoiler_handle) -> None:
        region, area, node = self.logic.starting_node
        player = self.multiworld.get_player_name(self.player)
        spoiler_handle.write(
            f"Starting Location ({player}): {region}/{area}/{node}\n"
        )
        if self.start_kit:
            kit = ", ".join(StartKit.logical_names(self.start_kit))
            spoiler_handle.write(f"Starting Items ({player}): {kit}\n")
        extras = dict(self.patch_extras or {})
        # Record DNA locations for hint_all_dna after fill — filled in write_spoiler.
        spoiler_handle.write(
            f"{DREAD_PATCH_EXTRAS_MARKER}{player}:"
            + json.dumps(extras, separators=(",", ":"))
            + "\n"
        )

    def write_spoiler(self, spoiler_handle) -> None:
        """Append DNA location list for nav hints when requested."""
        if not (self.patch_extras or {}).get("hint_all_dna"):
            return
        player = self.multiworld.get_player_name(self.player)
        dna_locs = []
        for loc in self.multiworld.get_locations(self.player):
            if loc.item and loc.item.player == self.player and loc.item.name == "Metroid DNA":
                dna_locs.append(loc.name)
        if dna_locs:
            spoiler_handle.write(
                f"DREAD_DNA_LOCATIONS:{player}:"
                + json.dumps(dna_locs, separators=(",", ":"))
                + "\n"
            )

    def get_filler_item_name(self) -> str:
        return "Missile Tank"

"""
Metroid Dread world implementation for Archipelago

Uses Randovania logic_database as the live reachability engine (see dread_logic.py).
"""

from __future__ import annotations

import json
from typing import List, Optional

from BaseClasses import Tutorial, ItemClassification
from Fill import FillError
from worlds.AutoWorld import World, WebWorld
from .Items import MetroidDreadItem, item_table, item_name_groups
from .Locations import MetroidDreadLocation, location_table, location_name_groups
from .Options import MetroidDreadOptions, metroid_dread_option_groups
from .Regions import create_regions
from .Rules import set_rules
from .dread_logic import DreadLogic
from .starting_locations import get_by_option_key, get_default, load_starting_locations
from . import DoorRando
from . import StartKit
from . import TransportRando
from . import victory_clearance
from .logic_options import collect_logic_options_from_options

# Register launcher component
try:
    from . import launcher
except ImportError:
    pass

DREAD_PATCH_EXTRAS_MARKER = "DREAD_PATCH_EXTRAS_JSON:"

_GOAL_NODE = ("Itorash", "Raven Beak Arena", "Boss - Raven Beak")

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


class MetroidDreadWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up Metroid Dread for Archipelago multiworld",
        "English",
        "setup_en.md",
        "setup/en",
        ["Contributors"]
    )]
    theme = "ocean"
    bug_report_page = "https://github.com/ArchipelagoMW/Archipelago/issues"


class MetroidDreadWorld(World):
    """
    Metroid Dread is a 2D action-adventure game and the fifth main installment in the Metroid series.
    """
    game = "Metroid Dread"
    options_dataclass = MetroidDreadOptions
    options: MetroidDreadOptions
    option_groups = metroid_dread_option_groups
    web = MetroidDreadWeb()
    logic: DreadLogic

    item_name_to_id = {name: data.id for name, data in item_table.items() if data.id is not None}
    location_name_to_id = {name: data.id for name, data in location_table.items()}

    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    required_client_version = (0, 4, 0)

    # Filled during generate_early / pre_fill for spoiler → patcher.
    door_assignments: dict
    door_patches: list
    transport_matching: dict
    elevator_patches: list
    patch_extras: dict
    start_kit: list
    # Boss/EMMI checks kept despite include_boss_pickups=false for DNA capacity.
    forced_boss_locations: set

    def generate_early(self):
        self.logic = DreadLogic(self)
        self.door_assignments = {}
        self.door_patches = []
        self.transport_matching = {}
        self.elevator_patches = []
        self.patch_extras = {}
        self.start_kit = []
        self.forced_boss_locations = set()

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
                f"[Metroid Dread Player {self.player}] accessibility "
                f"'minimal' upgraded to 'items' (victory implies {goal_note})"
            )

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
                        f"[Metroid Dread Player {self.player}] "
                        f"door/transport preflight failed after re-rolls"
                        f"{' + door soften' if want_doors else ''} "
                        f"({last_preflight}); reverted to vanilla graph"
                    )

        # Final guard: never ship a kit that can already touch Raven Beak.
        if self._start_kit_reaches_goal():
            self._roll_start_kit()

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

    def _start_kit_reaches_goal(self) -> bool:
        """True when the starting kit alone can already reach Raven Beak."""
        counts = StartKit.kit_counts(self.start_kit)
        nodes = self.logic.get_reachable_nodes(
            self.logic.inventory_from_counts(counts)
        )
        return _GOAL_NODE in nodes

    def _has_uncleared_logic_locations(self) -> bool:
        """True if any AP pickup/event node stays out of logic with full inventory."""
        # Lazy import: Events↔Items circular import if pulled at module load.
        from .Events import event_locations

        nodes = self.logic.get_reachable_nodes(
            self.logic.inventory_from_counts(self._full_inventory_counts())
        )
        for name in self.active_location_names():
            node = self.logic.pickup_nodes.get(name)
            if node is not None and node not in nodes:
                return True
        # Canonical event locations (one AP loc per event item) must also be
        # reachable under accessibility:full.
        seen_event_items = set()
        for ev in event_locations:
            if ev.event_item in seen_event_items:
                continue
            seen_event_items.add(ev.event_item)
            if (ev.game_region, ev.area, ev.node) not in nodes:
                return True
        return False

    def _downgrade_full_accessibility_if_needed(self) -> None:
        if self.options.accessibility != "full":
            return
        if not self._has_uncleared_logic_locations():
            return
        self.options.accessibility.value = self.options.accessibility.option_items
        print(
            f"[Metroid Dread Player {self.player}] accessibility "
            f"'full' downgraded to 'items' (some checks need tricks that "
            f"are disabled)"
        )

    def _kit_is_ok(self) -> bool:
        return (
            self._start_checks() >= _MIN_START_CHECKS
            and not self._start_kit_reaches_goal()
        )

    def _roll_start_kit(self) -> None:
        """Pick the starting kit, relocating if this start cannot be opened.

        A handful of save rooms — Burenia's south room is the worst, sitting
        underwater behind a four-item gate — need more handed to the player
        than is reasonable. Moving the start is much better than shipping a
        seed the fill cannot complete.
        """
        self.start_kit = StartKit.build_start_kit(self)
        if self._kit_is_ok():
            return

        original = self.logic.starting_node
        original_kit = self.start_kit
        candidates = list(load_starting_locations())
        self.random.shuffle(candidates)
        for info in candidates:
            if info.node_id == original or not self._start_is_viable(info.node_id):
                continue
            self.logic.set_starting_node(info.node_id)
            self.start_kit = StartKit.build_start_kit(self)
            if self._kit_is_ok():
                print(
                    f"[Metroid Dread Player {self.player}] starting location "
                    f"{'/'.join(original)} has too little in logic to fill from; "
                    f"moved to {info.path}"
                )
                return

        self.logic.set_starting_node(original)
        self.start_kit = original_kit

    def _reset_logic_graph(self, kit: list) -> None:
        """Rebuild a vanilla logic graph at the current start (clear rando)."""
        node = self.logic.starting_node
        self.logic = DreadLogic(self)
        self.logic.set_starting_node(node)
        self.door_assignments = {}
        self.door_patches = []
        self.transport_matching = {}
        self.elevator_patches = []
        self.start_kit = list(kit)

    def _roll_door_and_transport_rando(self) -> None:
        """Apply one door-lock / transport shuffle onto the current vanilla graph."""
        self.door_assignments = {}
        self.door_patches = []
        self.transport_matching = {}
        self.elevator_patches = []

        if self.options.door_lock_rando.value == 1:
            self.door_assignments = DoorRando.roll_assignments(
                self.logic,
                self.random,
                doors_to_change=self.options.doors_to_change.value,
                change_doors_to=self.options.change_doors_to.value,
                mode="individual_doors",
                start_counts=StartKit.kit_counts(self.start_kit),
            )
            DoorRando.apply_assignments(self.logic.parser, self.door_assignments)
            self.door_patches = DoorRando.assignments_to_door_patches(
                self.door_assignments
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
        self._reset_logic_graph(vanilla_kit)
        self.transport_matching = matching
        self.door_assignments = doors
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
        self.start_kit = StartKit.build_start_kit(self, base_kit=vanilla_kit)

    def _graph_state_acceptable(self) -> Optional[FillError]:
        """None when start kit + preflight are OK; otherwise the failure reason."""
        if self._start_checks() < _MIN_START_CHECKS or self._start_kit_reaches_goal():
            return FillError(
                "start kit too weak or already reaches Raven Beak "
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
            self.start_kit = StartKit.build_start_kit(self, base_kit=vanilla_kit)
            err = self._graph_state_acceptable()
            if err is None:
                if attempt > 0:
                    print(
                        f"[Metroid Dread Player {self.player}] "
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
            keys = DoorRando.pick_doors_to_soften(scored, top_k=_DOOR_SOFTEN_TOP_K)
            if not keys:
                return False
            changed = DoorRando.soften_assignments(self.door_assignments, keys)
            if not changed:
                return False
            self._reapply_door_and_transport(vanilla_kit)
            err = self._graph_state_acceptable()
            print(
                f"[Metroid Dread Player {self.player}] door soften pass "
                f"{pass_i + 1}/{_DOOR_SOFTEN_PASSES}: opened {len(changed)} "
                f"door(s) toward denser checks"
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
                    protected=DoorRando.start_frontier_keys(
                        self.logic,
                        self.logic.inventory_from_counts(
                            StartKit.kit_counts(vanilla_kit)
                        ),
                    ),
                )
                keys = DoorRando.pick_doors_to_soften(
                    scored, top_k=_DOOR_SOFTEN_TOP_K
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
                    f"[Metroid Dread Player {self.player}] fill failed "
                    f"({exc}); softened {len(keys)} door(s) for retry "
                    f"{attempt + 1}/{_DOOR_SOFTEN_PASSES}"
                )
        if last_exc is not None:
            raise last_exc

    def _revert_randomizers(self, vanilla_kit: list) -> None:
        """Drop door / transport rando and go back to the vanilla graph."""
        self._reset_logic_graph(vanilla_kit)
        print(
            f"[Metroid Dread Player {self.player}] door / transport rando left "
            f"{'/'.join(self.logic.starting_node)} with too little in logic; "
            f"reverted to vanilla"
        )

    def _compute_forced_boss_locations(self) -> None:
        """
        When boss/EMMI pickups are excluded, still keep enough DNA sinks under
        high DNA / transport / door pressure so prefer_emmi/bosses can place.
        """
        self.forced_boss_locations = set()
        if self.options.include_boss_pickups:
            return
        needed = int(self.options.required_dna.value)
        mode = int(self.options.dna_placement.value)
        if needed <= 0 or mode == 2:
            return
        pressured = (
            self.options.transport_rando.value == 1
            or self.options.door_lock_rando.value == 1
            or needed >= 6
        )
        if not pressured:
            return
        substrs = _EMMI_DNA_SUBSTR if mode == 0 else _BOSS_DNA_SUBSTR
        sinks = [n for n in location_table if any(s in n for s in substrs)]
        self.random.shuffle(sinks)
        # Keep at least `needed` sink checks (and a small buffer) available.
        keep = min(len(sinks), max(needed + 2, needed))
        self.forced_boss_locations = set(sinks[:keep])
        if self.forced_boss_locations:
            print(
                f"[Metroid Dread Player {self.player}] keeping "
                f"{len(self.forced_boss_locations)} boss/EMMI check(s) as DNA "
                f"sinks (include_boss_pickups is off)"
            )

    def _full_inventory_counts(self) -> dict:
        """Every real item, in quantities past any progressive / DNA threshold."""
        return {name: 12 for name, data in item_table.items() if data.id is not None}

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
                    f"Unknown Metroid Dread starting_location option: {key!r}"
                )

        if not self._start_is_viable(info.node_id):
            fallback = next(
                (s for s in starts if self._start_is_viable(s.node_id)), None
            ) or get_default()
            print(
                f"[Metroid Dread Player {self.player}] starting location "
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

    def create_item(self, name: str) -> MetroidDreadItem:
        item_data = item_table[name]
        if item_data.id is None:
            return MetroidDreadItem(name, item_data.classification, None, self.player)
        return MetroidDreadItem(name, item_data.classification, item_data.id, self.player)

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
        """Reject fills where Raven Beak opens before the goal's clearance ratio."""
        victory_clearance.assert_victory_implies_full_clearance(self)

    def _dna_candidate_locations(self) -> List[str]:
        mode = int(self.options.dna_placement.value)
        active = set(self.active_location_names())
        anywhere = [n for n in location_table if n in active]
        if mode == 2:
            return anywhere

        if mode == 0:  # prefer_emmi
            substrs = _EMMI_DNA_SUBSTR
        else:  # prefer_bosses
            substrs = _BOSS_DNA_SUBSTR

        preferred = [
            n for n in location_table
            if n in active and any(s in n for s in substrs)
        ]
        needed = int(self.options.required_dna.value)
        # High DNA + transport/doors: preferred first, then anywhere (softening).
        pressured = (
            needed >= 6
            or self.options.transport_rando.value == 1
            or self.options.door_lock_rando.value == 1
        )
        if len(preferred) >= needed and not pressured:
            return preferred
        # Preferred first, then remaining actives — never starve DNA placement.
        seen = set(preferred)
        return preferred + [n for n in anywhere if n not in seen]

    def _pre_place_dna(self) -> None:
        n = int(self.options.required_dna.value)
        if n <= 0 or int(self.options.dna_placement.value) == 2:
            return
        candidates = self._dna_candidate_locations()
        # Keep preferred-first order but shuffle within tiers loosely.
        if candidates:
            head = candidates[:n]
            self.random.shuffle(head)
            rest = candidates[n:]
            self.random.shuffle(rest)
            candidates = head + rest
        if len(candidates) < n:
            return
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
            f"[Metroid Dread Player {self.player}] "
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

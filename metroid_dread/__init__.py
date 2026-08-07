"""
Metroid Dread world implementation for Archipelago

Uses Randovania logic_database as the live reachability engine (see dread_logic.py).
"""

from __future__ import annotations

import json
from typing import List

from BaseClasses import Tutorial, ItemClassification
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

    def generate_early(self):
        self.logic = DreadLogic(self)
        self.door_assignments = {}
        self.door_patches = []
        self.transport_matching = {}
        self.elevator_patches = []
        self.patch_extras = {}
        self.start_kit = []

        self._resolve_starting_location()

        # Most valid_starting_location nodes have no pickup in logic on an empty
        # inventory, which the assumed fill cannot work with. Roll the kit that
        # reopens the start (see StartKit) before door rando, so the doors it
        # needs are part of the frontier that stays vanilla.
        self._roll_start_kit()

        # Door lock rando (mutate graph, then rebuild adjacency).
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
            self.door_patches = DoorRando.assignments_to_door_patches(self.door_assignments)

        # Transport rando.
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

        if self.door_assignments or self.transport_matching:
            vanilla_kit = self.start_kit
            self.logic.rebuild_graph()
            # Rando can still cost the start a few checks; top the kit back up,
            # and if that is not enough, go back to the graph we validated.
            self.start_kit = StartKit.build_start_kit(self, base_kit=vanilla_kit)
            if self._start_checks() < _MIN_START_CHECKS:
                self._revert_randomizers(vanilla_kit)

        self._build_patch_extras_base()

    def _build_patch_extras_base(self) -> None:
        room_name = ("NEVER", "ALWAYS", "WITH_FADE")[int(self.options.room_name_display.value)]
        rb_table = ("unmodified", "consistent_low", "consistent_high")[
            int(self.options.raven_beak_damage_table.value)
        ]
        required = int(self.options.required_dna.value)
        self.patch_extras = {
            "door_patches": self.door_patches,
            "elevators": self.elevator_patches,
            "required_artifacts": required,
            "hint_all_dna": bool(self.options.hint_all_dna.value) and required > 0,
            "cosmetic_combat": {
                "bShowBossLifebar": bool(self.options.show_boss_lifebar.value),
                "bShowEnemyLife": bool(self.options.show_enemy_life.value),
                "bShowEnemyDamage": bool(self.options.show_enemy_damage.value),
                "bShowPlayerDamage": bool(self.options.show_player_damage.value),
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
            "flash_shift_upgrade_amount": int(self.options.flash_shift_upgrade_amount.value),
            "flash_shift_included_ammo": int(self.options.flash_shift_included_ammo.value),
            "start_with_pulse_radar": bool(self.options.start_with_pulse_radar.value),
            "starting_items": StartKit.odr_starting_items(self.start_kit),
        }

    def _start_checks(self) -> int:
        return StartKit.start_checks(self, StartKit.kit_counts(self.start_kit))

    def _roll_start_kit(self) -> None:
        """Pick the starting kit, relocating if this start cannot be opened.

        A handful of save rooms — Burenia's south room is the worst, sitting
        underwater behind a four-item gate — need more handed to the player
        than is reasonable. Moving the start is much better than shipping a
        seed the fill cannot complete.
        """
        self.start_kit = StartKit.build_start_kit(self)
        if self._start_checks() >= _MIN_START_CHECKS:
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
            if self._start_checks() >= _MIN_START_CHECKS:
                print(
                    f"[Metroid Dread Player {self.player}] starting location "
                    f"{'/'.join(original)} has too little in logic to fill from; "
                    f"moved to {info.path}"
                )
                return

        self.logic.set_starting_node(original)
        self.start_kit = original_kit

    def _revert_randomizers(self, vanilla_kit: list) -> None:
        """Drop door / transport rando and go back to the vanilla graph."""
        node = self.logic.starting_node
        self.logic = DreadLogic(self)
        self.logic.set_starting_node(node)
        self.door_assignments = {}
        self.door_patches = []
        self.transport_matching = {}
        self.elevator_patches = []
        self.start_kit = vanilla_kit
        print(
            f"[Metroid Dread Player {self.player}] door / transport rando left "
            f"{'/'.join(node)} with too little in logic; reverted to vanilla"
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

        items_to_create["Flash Shift Upgrade"] = int(self.options.flash_shift_upgrade_count.value)
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
        self.patch_extras["starting_items"] = StartKit.odr_starting_items(granted)

        for item_name, count in items_to_create.items():
            for _ in range(count):
                itempool.append(self.create_item(item_name))

        if self.options.early_morph_ball and items_to_create.get("Morph Ball", 0) > 0:
            self.multiworld.local_early_items[self.player]["Morph Ball"] = 1

        # Exclude boss/EMMI checks → fewer locations, trim filler accordingly.
        active_locations = self.active_location_names()
        total_locations = len(active_locations)
        items_created = len(itempool)

        if items_created < total_locations:
            for _ in range(total_locations - items_created):
                itempool.append(self.create_item("Missile Tank"))
        elif items_created > total_locations:
            # Prefer trimming filler Missile Tanks first.
            extras = items_created - total_locations
            kept = []
            trimmed = 0
            for item in reversed(itempool):
                if trimmed < extras and item.name == "Missile Tank":
                    trimmed += 1
                    continue
                kept.append(item)
            itempool = list(reversed(kept))
            if len(itempool) > total_locations:
                raise Exception(
                    f"Too many items created: {len(itempool)} items for {total_locations} locations"
                )

        self.multiworld.itempool += itempool

    def active_location_names(self) -> List[str]:
        names = list(location_table.keys())
        if self.options.include_boss_pickups:
            return names
        return [
            n for n in names
            if not any(s in n for s in _BOSS_EMMI_LOCATION_SUBSTR)
        ]

    def create_item(self, name: str) -> MetroidDreadItem:
        item_data = item_table[name]
        if item_data.id is None:
            return MetroidDreadItem(name, item_data.classification, None, self.player)
        return MetroidDreadItem(name, item_data.classification, item_data.id, self.player)

    def set_rules(self):
        set_rules(self.multiworld, self.player, self.options)
        # Remove excluded boss/EMMI locations from the multiworld.
        if not self.options.include_boss_pickups:
            for name in list(location_table.keys()):
                if any(s in name for s in _BOSS_EMMI_LOCATION_SUBSTR):
                    try:
                        loc = self.multiworld.get_location(name, self.player)
                    except KeyError:
                        continue
                    if loc.parent_region:
                        loc.parent_region.locations.remove(loc)

    def pre_fill(self) -> None:
        self._pre_place_dna()

    def _dna_candidate_locations(self) -> List[str]:
        mode = int(self.options.dna_placement.value)
        active = set(self.active_location_names())
        if mode == 0:  # prefer_emmi
            substrs = _EMMI_DNA_SUBSTR
        elif mode == 1:  # prefer_bosses
            substrs = _BOSS_DNA_SUBSTR
        else:
            return [n for n in location_table if n in active]

        preferred = [n for n in location_table if n in active and any(s in n for s in substrs)]
        if len(preferred) >= int(self.options.required_dna.value):
            return preferred
        # Fall back to anywhere active.
        return [n for n in location_table if n in active]

    def _pre_place_dna(self) -> None:
        n = int(self.options.required_dna.value)
        if n <= 0 or int(self.options.dna_placement.value) == 2:
            return
        candidates = self._dna_candidate_locations()
        self.random.shuffle(candidates)
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
        slot_data = {
            "death_link": self.options.death_link.value,
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

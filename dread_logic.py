"""
Live Randovania logic bridge for Metroid Dread Archipelago.

Evaluates the logic_database node graph against CollectionState so assumed fill
respects one-ways, events, and lock-ins (e.g. ElunReleaseX / frozen Artaria).
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import AbstractSet, Dict, FrozenSet, Iterable, Optional, Set, Tuple, TYPE_CHECKING

from BaseClasses import CollectionState

from .logic_parser import RandovaniaLogicParser
from .Events import EVENT_RESOURCE_TO_ITEM

if TYPE_CHECKING:
    from . import MetroidDreadWorld

NodeId = Tuple[str, str, str]  # region, area, node

# RDV misc resources that are always enabled (matches dread bootstrap defaults).
MISC_ALWAYS_ON: FrozenSet[str] = frozenset({"SeparateBeams", "SeparateMissiles"})

# RDV misc short name -> MetroidDreadOptions field (truthy value enables the resource).
# Matches randovania dread generator bootstrap logical_patches / dock / teleporter flags.
MISC_TO_OPTION: Dict[str, str] = {
    "NerfPowerBombs": "nerf_power_bombs",
    "DoorLocks": "door_lock_rando",
    "Teleporters": "transport_rando",
}

# RDV trick short name -> MetroidDreadOptions field
TRICK_TO_OPTION: Dict[str, str] = {
    "Knowledge": "knowledge_tricks",
    "Movement": "movement_tricks",
    "Combat": "combat_tricks",
    "Pseudo": "pseudo_wave",
    "IBJ": "infinite_bomb_jump",
    "WBJ": "water_bomb_jump",
    "WSJ": "water_space_jump",
    "SWJ": "single_wall_wall_jump",
    "Slide": "slide_jump",
    "Speedbooster": "speedbooster_conservation",
    "Walljump": "wall_jump_tricks",
    "Suitless": "heat_cold_runs",
    "RGrapple": "reverse_grapple_block",
    "DBoost": "damage_boost",
    "FrozenEnemy": "stand_on_frozen_enemy",
    "GrappleMovement": "grapple_movement",
    "CrossSkip": "cross_bomb_skip",
    "TunnelSlope": "climb_sloped_tunnels",
    "ShortBoost": "short_boost",
    "DiffusionAbuse": "diffusion_abuse",
    "FlashSkip": "flash_shift_skip",
    "DBJ": "diagonal_bomb_jump",
    "LedgeWarp": "ledge_warp",
    "CBL": "cross_bomb_launch",
    "FloorClip": "floor_clip",
    "SlopeClimb": "climb_sloped_surfaces",
}

# Individual AP names implied by progressive counts
PROGRESSIVE_EXPAND: Dict[str, Tuple[str, ...]] = {
    "Progressive Beam": ("Wide Beam", "Plasma Beam", "Wave Beam"),
    "Progressive Charge Beam": ("Charge Beam", "Diffusion Beam"),
    "Progressive Missiles": ("Super Missile", "Ice Missile"),
    "Progressive Bombs": ("Bomb", "Cross Bomb"),
    "Progressive Suit": ("Varia Suit", "Gravity Suit"),
    "Progressive Spin": ("Spin Boost", "Space Jump"),
}

# RDV item short name -> AP item (None = always owned / not an item)
# Keys must match logic_database/header.json resource_database.items
ITEM_SHORT_TO_AP: Dict[str, Optional[str]] = {
    "Nothing": None,
    "Power": None,
    "Wide": "Wide Beam",
    "Plasma": "Plasma Beam",
    "Wave": "Wave Beam",
    "Hyper": None,
    "Charge": "Charge Beam",
    "Diffusion": "Diffusion Beam",
    "Grapple": "Grapple Beam",
    "MissileLauncher": None,  # always available in Dread
    "Supers": "Super Missile",
    "Ice": "Ice Missile",
    "Storm": "Storm Missile",
    "Cloak": "Phantom Cloak",
    "Flash": "Flash Shift",
    "Pulse": "Pulse Radar",
    "PowerSuit": None,
    "Varia": "Varia Suit",
    "Gravity": "Gravity Suit",
    "HyperSuit": None,
    "Morph": "Morph Ball",
    "Bomb": "Bomb",
    "Cross": "Cross Bomb",
    "MainPB": "Power Bomb",
    "Magnet": "Spider Magnet",
    "Speed": "Speed Booster",
    "Spin": "Spin Boost",
    "Space": "Space Jump",
    "Screw": "Screw Attack",
    "ETank": "Energy Tank",
    "EFragment": "Energy Part",
    "MissileAmmo": None,  # capacity; base missiles always usable
    "PBAmmo": "__pb_ammo__",
    "Slide": None,  # default ability
    "Metroidnization": None,
    "FlashUpgrade": "Flash Shift Upgrade",
    "SpeedBoostUpgrade": "Speed Booster Upgrade",
    # DNA artifacts
    "Artifact1": "Metroid DNA",
    "Artifact2": "Metroid DNA",
    "Artifact3": "Metroid DNA",
    "Artifact4": "Metroid DNA",
    "Artifact5": "Metroid DNA",
    "Artifact6": "Metroid DNA",
    "Artifact7": "Metroid DNA",
    "Artifact8": "Metroid DNA",
    "Artifact9": "Metroid DNA",
    "Artifact10": "Metroid DNA",
    "Artifact11": "Metroid DNA",
    "Artifact12": "Metroid DNA",
    # Legacy aliases (older mapper / docs)
    "Radar": "Pulse Radar",
    "VariaSuit": "Varia Suit",
    "GravitySuit": "Gravity Suit",
    "CrossBomb": "Cross Bomb",
    "PowerBomb": "Power Bomb",
    "SpiderMagnet": "Spider Magnet",
    "SpeedBooster": "Speed Booster",
    "SpinBoost": "Spin Boost",
    "SpaceJump": "Space Jump",
    "ScrewAttack": "Screw Attack",
    "Missile": None,
    "PowerBombAmmo": "__pb_ammo__",
    "Energy": "__energy__",
    "WaterNoBreath": None,
    "LavaNoBreath": None,
    "Shoot": None,
    "FreeMelee": None,
    "Omega": "Omega Cannon",
    "OmegaStream": "Omega Stream Beam",
}


class DreadLogic:
    """Per-player Randovania graph evaluator."""

    def __init__(self, world: "MetroidDreadWorld"):
        self.world = world
        self.player = world.player
        logic_path = Path(__file__).parent / "logic_database"
        self.parser = RandovaniaLogicParser(str(logic_path))
        self.parser.load_database()

        starts = self.parser.get_starting_nodes()
        # Prefer Artaria intro-style starts when present
        artaria_starts = [s for s in starts if s[0] == "Artaria"]
        self.starting_node: NodeId = (
            artaria_starts[0] if artaria_starts else (starts[0] if starts else ("Artaria", "Intro Room", "Start Point"))
        )

        self._reachable_cache: Dict[FrozenSet[str], Set[NodeId]] = {}
        # node -> list of (target, requirement)
        self._adj: Dict[NodeId, list] = {}
        self._build_adjacency()

        # Event nodes grant logical event items during BFS (RDV-style).
        from .Events import event_locations
        self._event_items: Dict[NodeId, str] = {
            (ev.game_region, ev.area, ev.node): ev.event_item
            for ev in event_locations
        }

        self.pickup_nodes: Dict[str, NodeId] = {}
        for region, area, node, _idx in self.parser.get_pickup_locations():
            name = f"{region} - {area} - {node}"
            self.pickup_nodes[name] = (region, area, node)

    def _build_adjacency(self) -> None:
        for region_name, region_data in self.parser.regions.items():
            for area_name, area_data in region_data.get("areas", {}).items():
                for node_name in area_data.get("nodes", {}):
                    src: NodeId = (region_name, area_name, node_name)
                    self._adj[src] = []
                    for t_region, t_area, t_node, req in self.parser.get_node_connections(
                        region_name, area_name, node_name
                    ):
                        self._adj[src].append(((t_region, t_area, t_node), req))

    def set_starting_node(self, node: NodeId) -> None:
        self.starting_node = node
        self._reachable_cache.clear()

    def rebuild_graph(self) -> None:
        """Call after DoorRando / TransportRando mutate the parser graph."""
        self._adj.clear()
        self._build_adjacency()
        self._reachable_cache.clear()

    # ----- inventory -----

    def inventory_from_counts(self, counts: Dict[str, int]) -> FrozenSet[str]:
        """Build BFS inventory from item-name → count (tracker / client use)."""
        owned: Set[str] = set()

        # Expand progressive stacks into individual logical items
        for prog, parts in PROGRESSIVE_EXPAND.items():
            count = int(counts.get(prog, 0) or 0)
            for i, part in enumerate(parts):
                if count > i:
                    owned.add(part)

        from .Items import item_table
        from .Events import event_item_table

        for name in item_table:
            if name in PROGRESSIVE_EXPAND:
                continue
            if int(counts.get(name, 0) or 0) > 0:
                owned.add(name)
        for name in event_item_table:
            if int(counts.get(name, 0) or 0) > 0:
                owned.add(name)

        # Flash Shift: mode-aware ability + chain count (see flash_shift.py).
        from .flash_shift import logical_ability_and_chains, plan_from_options

        fs_plan = plan_from_options(self.world.options)
        has_flash, chains = logical_ability_and_chains(counts, fs_plan)
        if has_flash:
            owned.add("Flash Shift")
        if chains > 0 or int(counts.get("Flash Shift Upgrade", 0) or 0) > 0:
            owned.add("Flash Shift Upgrade")
        owned.add(f"__flash_upgrade_{int(chains)}__")

        # Synthetic capacity tokens — base missiles always available in Dread
        owned.add("__missiles__")
        # Main Power Bomb includes starting PB ammo; tanks add per-tank yield.
        start_pb = 0
        try:
            start_pb = int(self.world.options.starting_power_bombs.value)
        except Exception:
            start_pb = 0
        pb_per = 1
        try:
            pb_per = int(self.world.options.power_bomb_tank_ammo.value)
        except Exception:
            pb_per = 1
        pb = int(counts.get("Power Bomb Tank", 0) or 0) * pb_per + (
            start_pb + 2 if int(counts.get("Power Bomb", 0) or 0) > 0 else 0
        )
        if pb > 0:
            owned.add("__pb_ammo__")
        ept = 100
        try:
            ept = max(1, int(self.world.options.energy_per_tank.value))
        except Exception:
            ept = 100
        energy = (
            (ept - 1)
            + int(counts.get("Energy Tank", 0) or 0) * ept
            + int(counts.get("Energy Part", 0) or 0) * (ept / 4)
        )
        owned.add(f"__energy_{int(energy)}__")
        owned.add("__energy__")

        dna = int(counts.get("Metroid DNA", 0) or 0)
        if dna:
            owned.add("Metroid DNA")
            owned.add(f"__dna_{dna}__")

        return frozenset(owned)

    def inventory_from_state(self, state: CollectionState) -> FrozenSet[str]:
        """Normalized set of logical capability / event names for BFS caching."""
        player = self.player
        from .Items import item_table
        from .Events import event_item_table

        counts: Dict[str, int] = {}
        for prog in PROGRESSIVE_EXPAND:
            counts[prog] = state.count(prog, player)
        for name in item_table:
            if name in PROGRESSIVE_EXPAND:
                continue
            if state.has(name, player):
                counts[name] = state.count(name, player)
        for name in event_item_table:
            if state.has(name, player):
                counts[name] = state.count(name, player)
        return self.inventory_from_counts(counts)

    def reachable_pickup_names(
        self,
        counts: Dict[str, int],
        *,
        exclude_auto_events: Optional[AbstractSet[str]] = None,
    ) -> list[str]:
        """Location names currently in-logic for the given inventory counts."""
        inv = self.inventory_from_counts(counts)
        nodes = self.get_reachable_nodes(inv, exclude_auto_events=exclude_auto_events)
        return sorted(name for name, node in self.pickup_nodes.items() if node in nodes)

    def reachable_areas(
        self,
        counts: Dict[str, int],
        *,
        exclude_auto_events: Optional[AbstractSet[str]] = None,
    ) -> Set[Tuple[str, str]]:
        """
        Unique (region, area) pairs reachable with the given inventory.
        Always includes the starting area.
        """
        inv = self.inventory_from_counts(counts)
        nodes = self.get_reachable_nodes(inv, exclude_auto_events=exclude_auto_events)
        areas: Set[Tuple[str, str]] = {
            (self.starting_node[0], self.starting_node[1])
        }
        for region, area, _node in nodes:
            areas.add((region, area))
        return areas

    def trick_level(self, trick_short: str) -> int:
        opt_name = TRICK_TO_OPTION.get(trick_short)
        if not opt_name:
            return 0
        opt = getattr(self.world.options, opt_name, None)
        if opt is None:
            return 0
        return int(opt.value)

    # ----- requirement eval -----

    def evaluate_requirement(self, req, inventory: FrozenSet[str]) -> bool:
        if not req:
            return True
        if not isinstance(req, dict):
            return True

        req_type = req.get("type")
        if req_type == "trivial":
            return True
        if req_type == "impossible":
            return False

        if req_type == "resource":
            data = req.get("data") or {}
            rtype = data.get("type")
            rname = data.get("name")
            amount = int(data.get("amount", 1) or 1)
            negate = bool(data.get("negate", False))
            ok = self._resource_ok(rtype, rname, amount, inventory)
            return (not ok) if negate else ok

        if req_type == "template":
            tname = req.get("data")
            tmpl = self.parser.templates.get(tname)
            if not tmpl:
                return True
            inner = tmpl.get("requirement") if isinstance(tmpl, dict) else tmpl
            return self.evaluate_requirement(inner, inventory)

        if req_type == "and":
            items = (req.get("data") or {}).get("items") or []
            return all(self.evaluate_requirement(i, inventory) for i in items)

        if req_type == "or":
            items = (req.get("data") or {}).get("items") or []
            if not items:
                return False
            return any(self.evaluate_requirement(i, inventory) for i in items)

        return True

    def _resource_ok(self, rtype: str, rname: str, amount: int, inventory: FrozenSet[str]) -> bool:
        if rtype == "items":
            if rname.startswith("Artifact"):
                required = 0
                try:
                    required = int(self.world.options.required_dna.value)
                except Exception:
                    required = 0
                if required <= 0:
                    return True
                try:
                    art_index = int(rname.replace("Artifact", ""))
                except ValueError:
                    art_index = amount
                # Artifacts beyond required_dna are pre-granted in the ROM.
                if art_index > required:
                    return True
                dna_count = 0
                for token in inventory:
                    if token.startswith("__dna_") and token.endswith("__"):
                        try:
                            dna_count = max(dna_count, int(token[len("__dna_"):-2]))
                        except ValueError:
                            pass
                return dna_count >= art_index

            if rname not in ITEM_SHORT_TO_AP:
                return False
            ap = ITEM_SHORT_TO_AP[rname]
            if ap is None:
                return True
            if ap == "__pb_ammo__":
                return "__pb_ammo__" in inventory or "Power Bomb" in inventory
            if ap == "__energy__":
                best = 99
                for token in inventory:
                    if token.startswith("__energy_") and token.endswith("__") and token != "__energy__":
                        try:
                            best = max(best, int(token[len("__energy_"):-2]))
                        except ValueError:
                            pass
                return best >= amount
            if ap == "Flash Shift Upgrade":
                if amount <= 1:
                    return "Flash Shift Upgrade" in inventory or any(
                        t.startswith("__flash_upgrade_") and t.endswith("__")
                        for t in inventory
                    )
                best = 0
                for token in inventory:
                    if token.startswith("__flash_upgrade_") and token.endswith("__"):
                        try:
                            best = max(best, int(token[len("__flash_upgrade_"):-2]))
                        except ValueError:
                            pass
                return best >= amount
            return ap in inventory

        if rtype == "events":
            item = EVENT_RESOURCE_TO_ITEM.get(rname)
            if not item:
                return False
            return item in inventory

        if rtype == "tricks":
            return self.trick_level(rname) >= amount

        if rtype == "damage":
            return self._damage_ok(rname, amount, inventory)

        if rtype == "misc":
            return self._misc_ok(rname)

        return False

    def _misc_ok(self, rname: str) -> bool:
        """
        RDV misc resources gate optional patches (e.g. NerfPowerBombs).

        Open Charge Door / Destroy Enky require ``NOT NerfPowerBombs`` for the
        Power Bomb alternate; when the option is on, that branch must fail so
        generator logic matches ODR's ``_remove_pb_weaknesses`` patch.
        """
        if rname in MISC_ALWAYS_ON:
            return True
        opt_name = MISC_TO_OPTION.get(rname)
        if not opt_name:
            return False
        opt = getattr(self.world.options, opt_name, None)
        if opt is None:
            return False
        try:
            return int(opt.value) > 0
        except Exception:
            return bool(opt.value)

    def _damage_ok(self, name: str, amount: int, inventory: FrozenSet[str]) -> bool:
        suitless = self.trick_level("Suitless")
        has_varia = "Varia Suit" in inventory
        has_grav = "Gravity Suit" in inventory
        if name == "Heat":
            return has_varia or has_grav or suitless >= 1
        if name in ("Cold", "Lava"):
            return has_grav or suitless >= 2
        if name == "Damage":
            # Combat chip damage — allow if Combat trick or enough energy
            if self.trick_level("Combat") >= 1:
                return True
            return self._resource_ok("items", "Energy", amount, inventory)
        if name == "OOB":
            return self.trick_level("FloorClip") >= 1
        return True

    # ----- reachability -----

    def _bfs_once(self, inventory: FrozenSet[str], start: NodeId) -> Set[NodeId]:
        reachable: Set[NodeId] = set()
        queue: deque[NodeId] = deque()
        queue.append(start)
        reachable.add(start)
        while queue:
            current = queue.popleft()
            for target, requirement in self._adj.get(current, ()):
                if target in reachable:
                    continue
                if self.evaluate_requirement(requirement, inventory):
                    reachable.add(target)
                    queue.append(target)
        return reachable

    def get_reachable_nodes(
        self,
        inventory: FrozenSet[str],
        start: Optional[NodeId] = None,
        collect_events: bool = True,
        exclude_auto_events: Optional[AbstractSet[str]] = None,
    ) -> Set[NodeId]:
        """BFS from start, optionally granting event items as their nodes become reachable.

        ``exclude_auto_events``: event item names that must already be in
        ``inventory`` to count (Hub tracker uses this so Quiet Robe / X release
        are not invented from reachability alone). Generation leaves this empty.
        """
        start = start or self.starting_node
        exclude = frozenset(exclude_auto_events or ())
        # Cache only the default generation path (full auto-collect, no excludes).
        cache_ok = collect_events and not exclude and start == self.starting_node
        if cache_ok and inventory in self._reachable_cache:
            return self._reachable_cache[inventory]

        if not collect_events:
            return self._bfs_once(inventory, start)

        inv: Set[str] = set(inventory)
        reachable: Set[NodeId] = set()
        for _ in range(len(self._event_items) + 2):
            reachable = self._bfs_once(frozenset(inv), start)
            gained = False
            for node, event_item in self._event_items.items():
                if event_item in exclude:
                    continue
                if node in reachable and event_item not in inv:
                    inv.add(event_item)
                    gained = True
            if not gained:
                break

        if cache_ok:
            self._reachable_cache[inventory] = reachable
            if len(self._reachable_cache) > 512:
                self._reachable_cache.clear()
        return reachable

    def can_reach_node(self, node: NodeId, state: CollectionState) -> bool:
        inv = self.inventory_from_state(state)
        return node in self.get_reachable_nodes(inv)

    def can_reach_location_name(self, location_name: str, state: CollectionState) -> bool:
        node = self.pickup_nodes.get(location_name)
        if node is None:
            # Event location naming
            parts = location_name.split(" - ", 2)
            if len(parts) == 3:
                node = (parts[0], parts[1], parts[2])
            else:
                return False
        return self.can_reach_node(node, state)

    def clear_cache(self) -> None:
        self._reachable_cache.clear()

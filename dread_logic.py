"""
Live Randovania logic bridge for Metroid Bread Archipelago.

Evaluates the logic_database node graph against CollectionState so assumed fill
respects one-ways, events, and lock-ins (e.g. ElunReleaseX / frozen Artaria).
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import AbstractSet, Dict, FrozenSet, Iterable, Optional, Set, Tuple, TYPE_CHECKING

from .logic_parser import RandovaniaLogicParser
from .Events import EVENT_RESOURCE_TO_ITEM

if TYPE_CHECKING:
    from BaseClasses import CollectionState
    from . import MetroidBreadWorld

NodeId = Tuple[str, str, str]  # region, area, node

# RDV misc resources that are always enabled (matches dread bootstrap defaults).
MISC_ALWAYS_ON: FrozenSet[str] = frozenset({"SeparateBeams", "SeparateMissiles"})

# RDV misc short name -> MetroidBreadOptions field (truthy value enables the resource).
# Matches randovania dread generator bootstrap logical_patches / dock / teleporter flags.
MISC_TO_OPTION: Dict[str, str] = {
    "NerfPowerBombs": "nerf_power_bombs",
    "DoorLocks": "door_lock_rando",
    "Teleporters": "transport_rando",
}

# RDV trick short name -> MetroidBreadOptions field
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

TRICK_DISPLAY: Dict[str, str] = {
    "Knowledge": "Knowledge",
    "Movement": "Movement",
    "Combat": "Combat",
    "Pseudo": "Pseudo Wave",
    "IBJ": "Infinite Bomb Jump",
    "WBJ": "Water Bomb Jump",
    "WSJ": "Water Space Jump",
    "SWJ": "Single Wall Jump",
    "Slide": "Slide Jump",
    "Speedbooster": "Speed Booster Conservation",
    "Walljump": "Wall Jump",
    "Suitless": "Heat/Cold Runs",
    "RGrapple": "Reverse Grapple Block",
    "DBoost": "Damage Boost",
    "FrozenEnemy": "Stand on Frozen Enemy",
    "GrappleMovement": "Grapple Movement",
    "CrossSkip": "Cross Bomb Skip",
    "TunnelSlope": "Climb Sloped Tunnels",
    "ShortBoost": "Short Boost",
    "DiffusionAbuse": "Diffusion Abuse",
    "FlashSkip": "Flash Shift Skip",
    "DBJ": "Diagonal Bomb Jump",
    "LedgeWarp": "Ledge Warp",
    "CBL": "Cross Bomb Launch",
    "FloorClip": "Floor Clip",
    "SlopeClimb": "Climb Sloped Surfaces",
}

TRICK_LEVEL_LABELS: Dict[int, str] = {
    1: "Beginner",
    2: "Intermediate",
    3: "Advanced",
    4: "Expert",
    5: "Ludicrous",
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
    "MissileLauncher": None,  # always available in Dread (ammo gates fire)
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
    "MissileAmmo": "__missile_ammo__",  # capacity from starting_missiles + tanks
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
    "Missile": "__missile_ammo__",
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

    def __init__(self, world: "MetroidBreadWorld"):
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
        self._rev_adj: Optional[Dict[NodeId, list]] = None
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
        self._rev_adj = None
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

        # Synthetic capacity tokens — missiles from starting ammo + tanks.
        start_missiles = 15
        try:
            start_missiles = int(self.world.options.starting_missiles.value)
        except Exception:
            start_missiles = 15
        mt_per = 2
        try:
            mt_per = int(self.world.options.missile_tank_ammo.value)
        except Exception:
            mt_per = 2
        mp_per = 10
        try:
            mp_per = int(self.world.options.missile_plus_tank_ammo.value)
        except Exception:
            mp_per = 10
        missiles = (
            start_missiles
            + int(counts.get("Missile Tank", 0) or 0) * mt_per
            + int(counts.get("Missile+ Tank", 0) or 0) * mp_per
        )
        # Optional launcher pickup grants capacity (same as dread_item_mapping).
        if int(counts.get("Missile Launcher", 0) or 0) > 0:
            missiles += 15
        owned.add(f"__missile_ammo_{int(missiles)}__")
        if missiles > 0:
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
            if ap == "__missile_ammo__":
                best = 0
                for token in inventory:
                    if token.startswith("__missile_ammo_") and token.endswith("__"):
                        try:
                            best = max(best, int(token[len("__missile_ammo_"):-2]))
                        except ValueError:
                            pass
                # Legacy presence token from hand-built inventories / older tests.
                if best == 0 and "__missiles__" in inventory:
                    best = 1
                return best >= amount
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

    def _bfs_once(
        self,
        inventory: FrozenSet[str],
        start: NodeId | AbstractSet[NodeId],
    ) -> Set[NodeId]:
        """Expand from one node or a seed set (multi-source).

        Multi-source is required when auto-collecting events: some rooms use
        ``negate`` on the same event that you collect inside (Chain Reaction
        Device). Restarting BFS from world spawn after granting that event
        permanently softlocks the room in logic — entry needs the event *off*,
        but the climb needs it *on* after you already walked in.
        """
        if isinstance(start, (set, frozenset, list, deque)):
            seeds: Iterable[NodeId] = start
        else:
            seeds = (start,)  # type: ignore[assignment]
        reachable: Set[NodeId] = set(seeds)
        queue: deque[NodeId] = deque(reachable)
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

        When events are collected, expansion continues from the already-reachable
        set (not only from spawn) so before/after event gates stay consistent.
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
        reachable: Set[NodeId] = {start}
        for _ in range(len(self._event_items) + 2):
            # Expand from every node already reached so collecting a room event
            # does not require re-entering through a "event not yet done" door.
            reachable = self._bfs_once(frozenset(inv), reachable)
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

    # ----- visualizer / path explanation -----

    def node_for_location(self, location_name: str) -> Optional[NodeId]:
        node = self.pickup_nodes.get(location_name)
        if node is not None:
            return node
        parts = location_name.split(" - ", 2)
        if len(parts) == 3:
            candidate = (parts[0], parts[1], parts[2])
            if candidate in self._adj:
                return candidate
        return None

    def _reverse_adj(self) -> Dict[NodeId, list]:
        if self._rev_adj is not None:
            return self._rev_adj
        rev: Dict[NodeId, list] = {}
        for src, edges in self._adj.items():
            for tgt, req in edges:
                rev.setdefault(tgt, []).append((src, req))
        self._rev_adj = rev
        return rev

    def _item_fact_label(self, rname: str, amount: int) -> Optional[str]:
        if rname.startswith("Artifact"):
            return "Metroid DNA" if amount <= 1 else f"Metroid DNA (×{amount})"
        if rname not in ITEM_SHORT_TO_AP:
            return None
        ap = ITEM_SHORT_TO_AP[rname]
        if ap is None:
            return None
        if ap == "__missile_ammo__":
            return "Missiles" if amount <= 1 else f"Missiles (×{amount})"
        if ap == "__pb_ammo__":
            return "Power Bombs" if amount <= 1 else f"Power Bombs (×{amount})"
        if ap == "__energy__":
            return f"Energy ({amount})"
        if ap == "Flash Shift Upgrade":
            return "Flash Shift Upgrade" if amount <= 1 else f"Flash Shift chains (×{amount})"
        if ap == "Metroid DNA":
            return "Metroid DNA" if amount <= 1 else f"Metroid DNA (×{amount})"
        return ap

    def _trick_fact_label(self, rname: str, amount: int) -> str:
        name = TRICK_DISPLAY.get(rname, rname)
        level = TRICK_LEVEL_LABELS.get(int(amount), str(amount))
        return f"{name} ({level})"

    def _event_fact_label(self, rname: str) -> Optional[str]:
        item = EVENT_RESOURCE_TO_ITEM.get(rname)
        if not item:
            return None
        if item.startswith("Event - "):
            return item[8:]
        return item

    def _add_unique(self, bucket: list, seen: Set[str], label: Optional[str]) -> None:
        if not label or label in seen:
            return
        seen.add(label)
        bucket.append(label)

    def _collect_damage_used(
        self,
        name: str,
        amount: int,
        inventory: FrozenSet[str],
        items: list,
        tricks: list,
        seen_items: Set[str],
        seen_tricks: Set[str],
    ) -> None:
        has_varia = "Varia Suit" in inventory
        has_grav = "Gravity Suit" in inventory
        suitless = self.trick_level("Suitless")
        if name == "Heat":
            if has_varia:
                self._add_unique(items, seen_items, "Varia Suit")
            elif has_grav:
                self._add_unique(items, seen_items, "Gravity Suit")
            elif suitless >= 1:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label("Suitless", 1))
            return
        if name in ("Cold", "Lava"):
            if has_grav:
                self._add_unique(items, seen_items, "Gravity Suit")
            elif suitless >= 2:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label("Suitless", 2))
            return
        if name == "Damage":
            if self.trick_level("Combat") >= 1:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label("Combat", 1))
            else:
                self._add_unique(items, seen_items, self._item_fact_label("Energy", amount))
            return
        if name == "OOB" and self.trick_level("FloorClip") >= 1:
            self._add_unique(tricks, seen_tricks, self._trick_fact_label("FloorClip", 1))

    def _collect_damage_missing(
        self,
        name: str,
        amount: int,
        inventory: FrozenSet[str],
        items: list,
        tricks: list,
        events: list,
        seen_items: Set[str],
        seen_tricks: Set[str],
        seen_events: Set[str],
    ) -> None:
        if self._damage_ok(name, amount, inventory):
            return
        has_varia = "Varia Suit" in inventory
        has_grav = "Gravity Suit" in inventory
        suitless = self.trick_level("Suitless")
        if name == "Heat":
            if not has_varia and not has_grav:
                self._add_unique(items, seen_items, "Varia Suit")
            if suitless >= 1:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label("Suitless", max(1, suitless)))
            return
        if name in ("Cold", "Lava"):
            if not has_grav:
                self._add_unique(items, seen_items, "Gravity Suit")
            if suitless >= 2:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label("Suitless", 2))
            return
        if name == "Damage":
            self._add_unique(items, seen_items, self._item_fact_label("Energy", amount))
            if self.trick_level("Combat") >= 1:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label("Combat", 1))
            return
        if name == "OOB" and self.trick_level("FloorClip") >= 1:
            self._add_unique(tricks, seen_tricks, self._trick_fact_label("FloorClip", 1))

    def _collect_used_facts(
        self,
        req,
        inventory: FrozenSet[str],
        items: list,
        tricks: list,
        seen_items: Set[str],
        seen_tricks: Set[str],
    ) -> None:
        if not req or not isinstance(req, dict):
            return
        if not self.evaluate_requirement(req, inventory):
            return
        req_type = req.get("type")
        if req_type in (None, "trivial", "impossible"):
            return
        if req_type == "template":
            tname = req.get("data")
            tmpl = self.parser.templates.get(tname)
            if not tmpl:
                return
            inner = tmpl.get("requirement") if isinstance(tmpl, dict) else tmpl
            self._collect_used_facts(inner, inventory, items, tricks, seen_items, seen_tricks)
            return
        if req_type == "and":
            for child in (req.get("data") or {}).get("items") or []:
                self._collect_used_facts(child, inventory, items, tricks, seen_items, seen_tricks)
            return
        if req_type == "or":
            children = (req.get("data") or {}).get("items") or []
            satisfied = [c for c in children if self.evaluate_requirement(c, inventory)]
            if not satisfied:
                return

            def _or_score(child) -> Tuple[int, int]:
                ci: list = []
                ct: list = []
                self._collect_used_facts(child, inventory, ci, ct, set(), set())
                return (len(ct), len(ci))

            best = min(satisfied, key=_or_score)
            self._collect_used_facts(best, inventory, items, tricks, seen_items, seen_tricks)
            return
        if req_type != "resource":
            return
        data = req.get("data") or {}
        if bool(data.get("negate", False)):
            return
        rtype = data.get("type")
        rname = data.get("name")
        amount = int(data.get("amount", 1) or 1)
        if rtype == "items":
            self._add_unique(items, seen_items, self._item_fact_label(rname, amount))
        elif rtype == "tricks":
            if self.trick_level(rname) >= amount:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label(rname, amount))
        elif rtype == "damage":
            self._collect_damage_used(
                rname, amount, inventory, items, tricks, seen_items, seen_tricks
            )

    def _empty_need_group(self) -> Dict[str, list]:
        return {"items": [], "tricks": [], "events": []}

    def _merge_need_groups(self, left: Dict[str, list], right: Dict[str, list]) -> Dict[str, list]:
        out = self._empty_need_group()
        for key in ("items", "tricks", "events"):
            seen: Set[str] = set()
            for label in list(left.get(key) or []) + list(right.get(key) or []):
                self._add_unique(out[key], seen, label)
        return out

    def _group_nonempty(self, group: Dict[str, list]) -> bool:
        return bool(group.get("items") or group.get("tricks") or group.get("events"))

    def _missing_groups(self, req, inventory: FrozenSet[str]) -> list:
        if not req or not isinstance(req, dict):
            return []
        if self.evaluate_requirement(req, inventory):
            return []
        req_type = req.get("type")
        if req_type == "impossible":
            return [{"items": [], "tricks": [], "events": ["Impossible in this seed"]}]
        if req_type == "template":
            tname = req.get("data")
            tmpl = self.parser.templates.get(tname)
            if not tmpl:
                return []
            inner = tmpl.get("requirement") if isinstance(tmpl, dict) else tmpl
            return self._missing_groups(inner, inventory)
        if req_type == "and":
            groups = [self._empty_need_group()]
            for child in (req.get("data") or {}).get("items") or []:
                child_groups = self._missing_groups(child, inventory)
                if not child_groups:
                    continue
                groups = [self._merge_need_groups(g, cg) for g in groups for cg in child_groups]
            return [g for g in groups if self._group_nonempty(g)]
        if req_type == "or":
            groups = []
            for child in (req.get("data") or {}).get("items") or []:
                groups.extend(self._missing_groups(child, inventory))
            return [g for g in groups if self._group_nonempty(g)]
        if req_type != "resource":
            return []
        data = req.get("data") or {}
        if bool(data.get("negate", False)):
            return []
        rtype = data.get("type")
        rname = data.get("name")
        amount = int(data.get("amount", 1) or 1)
        items: list = []
        tricks: list = []
        events: list = []
        seen_items: Set[str] = set()
        seen_tricks: Set[str] = set()
        seen_events: Set[str] = set()
        if rtype == "items":
            if not self._resource_ok(rtype, rname, amount, inventory):
                self._add_unique(items, seen_items, self._item_fact_label(rname, amount))
        elif rtype == "tricks":
            have = self.trick_level(rname)
            if have >= 1 and have < amount:
                self._add_unique(tricks, seen_tricks, self._trick_fact_label(rname, amount))
        elif rtype == "events":
            if not self._resource_ok(rtype, rname, amount, inventory):
                self._add_unique(events, seen_events, self._event_fact_label(rname))
        elif rtype == "damage":
            self._collect_damage_missing(
                rname,
                amount,
                inventory,
                items,
                tricks,
                events,
                seen_items,
                seen_tricks,
                seen_events,
            )
        group = {"items": items, "tricks": tricks, "events": events}
        return [group] if self._group_nonempty(group) else []

    def _bfs_explain(
        self,
        inventory: FrozenSet[str],
        start: NodeId,
        exclude_auto_events: Optional[AbstractSet[str]] = None,
    ) -> Tuple[Set[NodeId], Dict[NodeId, NodeId], Dict[NodeId, object], Dict[NodeId, FrozenSet[str]]]:
        exclude = frozenset(exclude_auto_events or ())
        inv: Set[str] = set(inventory)
        reachable: Set[NodeId] = {start}
        parent: Dict[NodeId, NodeId] = {}
        edge_req: Dict[NodeId, object] = {}
        inv_at: Dict[NodeId, FrozenSet[str]] = {start: frozenset(inv)}

        def expand(current_inv: FrozenSet[str]) -> None:
            queue: deque[NodeId] = deque(reachable)
            while queue:
                current = queue.popleft()
                for target, requirement in self._adj.get(current, ()):
                    if target in reachable:
                        continue
                    if self.evaluate_requirement(requirement, current_inv):
                        reachable.add(target)
                        parent[target] = current
                        edge_req[target] = requirement
                        inv_at[target] = current_inv
                        queue.append(target)

        for _ in range(len(self._event_items) + 2):
            expand(frozenset(inv))
            gained = False
            for node, event_item in self._event_items.items():
                if event_item in exclude:
                    continue
                if node in reachable and event_item not in inv:
                    inv.add(event_item)
                    gained = True
            if not gained:
                break
        return reachable, parent, edge_req, inv_at

    def _path_nodes(self, target: NodeId, parent: Dict[NodeId, NodeId], start: NodeId) -> Optional[list]:
        if target != start and target not in parent:
            return None
        path = [target]
        seen: Set[NodeId] = {target}
        while path[-1] in parent:
            prev = parent[path[-1]]
            if prev in seen:
                break
            seen.add(prev)
            path.append(prev)
        path.reverse()
        if path[0] != start:
            return None
        return path

    def _first_blocker_req(
        self,
        target: NodeId,
        reachable: Set[NodeId],
        inventory: FrozenSet[str],
    ):
        if target in reachable:
            return None
        rev = self._reverse_adj()
        seen: Set[NodeId] = {target}
        queue: deque[NodeId] = deque([target])
        hop: Dict[NodeId, Tuple[NodeId, object]] = {}
        frontier = None
        while queue:
            node = queue.popleft()
            for pred, req in rev.get(node, ()):
                if pred in seen:
                    continue
                seen.add(pred)
                hop[pred] = (node, req)
                if pred in reachable:
                    frontier = pred
                    queue.clear()
                    break
                queue.append(pred)
        if frontier is None:
            return None
        cur = frontier
        guard = 0
        while cur != target and guard < 4096:
            guard += 1
            nxt, req = hop[cur]
            if not self.evaluate_requirement(req, inventory):
                return req
            cur = nxt
        return None

    def _via_areas(self, path: list) -> list:
        via: list = []
        seen: Set[str] = set()
        for region, area, _node in path:
            label = f"{region} - {area}"
            if label in seen:
                continue
            seen.add(label)
            via.append(label)
        return via

    def explain_location(
        self,
        location_name: str,
        counts: Dict[str, int],
        *,
        exclude_auto_events: Optional[AbstractSet[str]] = None,
    ) -> dict:
        """Items / enabled tricks used (or blocking) a check for the visualizer."""
        node = self.node_for_location(location_name)
        if node is None:
            return {
                "location": location_name,
                "in_logic": False,
                "items": [],
                "tricks": [],
                "events": [],
                "alternatives": [],
                "via": [],
                "error": f"Unknown location: {location_name}",
            }

        inv = self.inventory_from_counts(counts)
        reachable, parent, edge_req, inv_at = self._bfs_explain(
            inv, self.starting_node, exclude_auto_events=exclude_auto_events
        )
        in_logic = node in reachable
        items: list = []
        tricks: list = []
        events: list = []
        alternatives: list = []
        via: list = []

        if in_logic:
            path = self._path_nodes(node, parent, self.starting_node) or [self.starting_node]
            via = self._via_areas(path)
            seen_items: Set[str] = set()
            seen_tricks: Set[str] = set()
            for step in path[1:]:
                req = edge_req.get(step)
                step_inv = inv_at.get(step, inv)
                if req:
                    self._collect_used_facts(
                        req, step_inv, items, tricks, seen_items, seen_tricks
                    )
        else:
            blocker = self._first_blocker_req(node, reachable, inv)
            groups = self._missing_groups(blocker, inv) if blocker else []
            alternatives = groups
            if len(groups) == 1:
                items = list(groups[0].get("items") or [])
                tricks = list(groups[0].get("tricks") or [])
                events = list(groups[0].get("events") or [])
            elif len(groups) > 1:
                seen_items = set()
                seen_tricks = set()
                seen_events = set()
                for group in groups:
                    for label in group.get("items") or []:
                        self._add_unique(items, seen_items, label)
                    for label in group.get("tricks") or []:
                        self._add_unique(tricks, seen_tricks, label)
                    for label in group.get("events") or []:
                        self._add_unique(events, seen_events, label)

        return {
            "location": location_name,
            "in_logic": in_logic,
            "items": items,
            "tricks": tricks,
            "events": events,
            "alternatives": alternatives,
            "via": via,
            "error": "",
        }

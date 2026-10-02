"""Live Randovania logic bridge for Metroid Bread Archipelago."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import AbstractSet, Dict, FrozenSet, Iterable, Mapping, Optional, Set, Tuple, TYPE_CHECKING

from .logic_parser import RandovaniaLogicParser
from .Events import EVENT_RESOURCE_TO_ITEM

if TYPE_CHECKING:
    from BaseClasses import CollectionState
    from . import MetroidBreadWorld

NodeId = Tuple[str, str, str]  # region, area, node

# RDV misc resources that are always enabled (matches dread bootstrap defaults).
MISC_ALWAYS_ON: FrozenSet[str] = frozenset({"SeparateBeams", "SeparateMissiles"})

# RDV misc short name -> MetroidBreadOptions field (truthy value enables the resource).
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

# Randovania dread logic_database/header.json ``damage_reductions``.
# Lowest owned multiplier wins. 0.0 is immunity.
# Heat/Cold/Lava HP costs stay the database amounts (RDV Strict, 1×).
# RDV Damage Strictness (starter presets use Medium 1.5×) is a separate
# global multiplier Bread does not expose; boss Damage gates already use
# the raw database numbers, and these do too.
# constant_heat_damage / constant_cold_damage / constant_lava_damage are
# patcher DPS only. RDV does not rescale these requirements from them.
ENV_DAMAGE_REDUCTIONS: Dict[str, Tuple[Tuple[str, float], ...]] = {
    "Heat": (("Varia Suit", 0.0), ("Gravity Suit", 0.0)),
    "Cold": (("Varia Suit", 0.75), ("Gravity Suit", 0.0)),
    "Lava": (("Varia Suit", 0.75), ("Gravity Suit", 0.0)),
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

        # (inventory, dangerous_logic) -> nodes that are in logic
        self._reachable_cache: Dict[Tuple[FrozenSet[str], bool], Set[NodeId]] = {}
        # node -> list of (target, requirement)
        self._adj: Dict[NodeId, list] = {}
        self._rev_adj: Optional[Dict[NodeId, list]] = None
        # Event items that appear in a negated requirement. Adding one can close a path.
        self._negated_event_items: FrozenSet[str] = frozenset()
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
        self._rev_adj = None
        self._negated_event_items = self._scan_negated_event_items()

    def dangerous_logic_enabled(self) -> bool:
        """True when reachable rooms may be required even if the player cannot leave."""
        try:
            opt = getattr(self.world.options, "dangerous_logic", None)
        except Exception:
            return False
        if opt is None:
            return False
        try:
            return int(opt.value) > 0
        except Exception:
            return bool(getattr(opt, "value", False))

    def _scan_negated_event_items(self) -> FrozenSet[str]:
        """Event items used as ``negate`` requirements (a collect can close a path)."""
        found: Set[str] = set()
        seen_templates: Set[str] = set()

        def walk(req) -> None:
            if not isinstance(req, dict):
                return
            req_type = req.get("type")
            if req_type == "resource":
                data = req.get("data") or {}
                if data.get("type") == "events" and data.get("negate") and data.get("name"):
                    item = EVENT_RESOURCE_TO_ITEM.get(data.get("name"))
                    if item:
                        found.add(item)
                return
            if req_type == "template":
                tname = req.get("data")
                if not isinstance(tname, str) or tname in seen_templates:
                    return
                seen_templates.add(tname)
                tmpl = self.parser.templates.get(tname)
                if isinstance(tmpl, dict):
                    walk(tmpl.get("requirement") if "requirement" in tmpl else tmpl)
                return
            data = req.get("data")
            if isinstance(data, dict):
                items = data.get("items")
                if isinstance(items, list):
                    for item in items:
                        walk(item)

        for edges in self._adj.values():
            for _target, req in edges:
                walk(req)
        return frozenset(found)

    def _ensure_reverse(self) -> Dict[NodeId, list]:
        if self._rev_adj is not None:
            return self._rev_adj
        rev: Dict[NodeId, list] = {}
        for src, edges in self._adj.items():
            for tgt, req in edges:
                rev.setdefault(tgt, []).append((src, req))
        self._rev_adj = rev
        return rev

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
        """Unique (region, area) pairs reachable with the given inventory."""
        inv = self.inventory_from_counts(counts)
        nodes = self.get_reachable_nodes(inv, exclude_auto_events=exclude_auto_events)
        areas: Set[Tuple[str, str]] = {
            (self.starting_node[0], self.starting_node[1])
        }
        for region, area, _node in nodes:
            areas.add((region, area))
        return areas

    def trick_level(self, trick_short: str) -> int:
        # Out-of-logic checks still need a reach path. Tricks stay off the panel.
        if getattr(self, "_ignore_tricks", False):
            return 99
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
                return self._current_energy(inventory) >= amount
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

    def _option_enabled(self, name: str) -> bool:
        opt = getattr(self.world.options, name, None)
        if opt is None:
            return False
        try:
            return int(opt.value) > 0
        except Exception:
            return bool(getattr(opt, "value", False))

    def _misc_ok(self, rname: str) -> bool:
        """RDV misc resources gate optional patches (e.g. NerfPowerBombs)."""
        if rname in MISC_ALWAYS_ON:
            return True
        # DoorLocks removes vanilla-shield sequence breaks. Randovania enables
        # it for any non-vanilla dock mode; Bread does the same when either
        # door placer is on.
        if rname == "DoorLocks":
            return self._option_enabled("door_lock_rando") or self._option_enabled(
                "randovania_door_rando"
            )
        opt_name = MISC_TO_OPTION.get(rname)
        if not opt_name:
            return False
        return self._option_enabled(opt_name)

    def _current_energy(self, inventory: FrozenSet[str]) -> int:
        """Collected max HP. Numeric ``__energy_N__`` wins; 99 if none is present.

        Matches RDV's starting energy of ``energy_per_tank - 1`` plus tanks and
        parts (see ``inventory_from_counts``). A legacy inventory that only has
        the ``__energy__`` flag is treated as base 99 HP.
        """
        best: Optional[int] = None
        for token in inventory:
            if not token.startswith("__energy_") or not token.endswith("__") or token == "__energy__":
                continue
            try:
                value = int(token[len("__energy_"):-2])
            except ValueError:
                continue
            best = value if best is None else max(best, value)
        return 99 if best is None else best

    def _env_damage_taken(self, name: str, amount: int, inventory: FrozenSet[str]) -> Optional[float]:
        """HP this Heat/Cold/Lava requirement costs after suit reduction.

        None when ``name`` is not environmental damage. 0.0 means immune.
        Same rule as RDV ``ResourceDatabase.get_damage_reduction``: the lowest
        matching multiplier applies, then ``health > amount * multiplier``.
        """
        rows = ENV_DAMAGE_REDUCTIONS.get(name)
        if rows is None:
            return None
        mult = 1.0
        for item_name, factor in rows:
            if item_name in inventory and factor < mult:
                mult = factor
        if mult <= 0.0:
            return 0.0
        return float(amount) * mult

    def _min_energy_to_survive(self, taken: float) -> int:
        """Smallest integer HP that stays strictly above ``taken`` (RDV ``health <= 0`` fails)."""
        if taken <= 0.0:
            return 1
        return int(taken) + 1

    def _damage_ok(self, name: str, amount: int, inventory: FrozenSet[str]) -> bool:
        taken = self._env_damage_taken(name, amount, inventory)
        if taken is not None:
            # Suitless level is the sibling trick resource (Beginner/Intermediate/
            # Advanced = 1/2/3). Disabled fails that check, not this one.
            # Varia or Gravity zeros Heat. Gravity zeros Cold and Lava.
            # Varia cuts Cold and Lava to 75%. No extra trick floor.
            return self._current_energy(inventory) > taken
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
        """Expand from one node or a seed set (multi-source)."""
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

    def _nodes_that_can_reach(self, goal: NodeId, inventory: FrozenSet[str]) -> Set[NodeId]:
        """Nodes with a satisfied path to ``goal`` (escape back toward the start)."""
        return self._nodes_that_can_reach_any((goal,), inventory)

    def _nodes_that_can_reach_any(
        self,
        goals: Iterable[NodeId],
        inventory: FrozenSet[str],
    ) -> Set[NodeId]:
        """Nodes with a satisfied path to any goal (start component or main roam)."""
        rev = self._ensure_reverse()
        found: Set[NodeId] = set(goals)
        queue: deque[NodeId] = deque(found)
        while queue:
            current = queue.popleft()
            for src, requirement in rev.get(current, ()):
                if src in found:
                    continue
                if self.evaluate_requirement(requirement, inventory):
                    found.add(src)
                    queue.append(src)
        return found

    def _roam_targets(
        self,
        reached: AbstractSet[NodeId],
        inventory: FrozenSet[str],
        start: NodeId,
    ) -> Set[NodeId]:
        """Start component plus the largest strongly connected roam.

        The intro spawn is often one-way. The largest component reachable from
        there is the area you can actually move around in. A lock-in room such
        as Charge Beam or the Dairon bomb upgrade is its own tiny component and
        is not a target until an exit from that room is already open.
        """
        fwd: Dict[NodeId, list] = {}
        rev_local: Dict[NodeId, list] = {}
        for node in reached:
            outs: list = []
            for target, requirement in self._adj.get(node, ()):
                if target not in reached:
                    continue
                if not self.evaluate_requirement(requirement, inventory):
                    continue
                outs.append(target)
                rev_local.setdefault(target, []).append(node)
            fwd[node] = outs
            rev_local.setdefault(node, [])

        seen: Set[NodeId] = set()
        order: list = []
        for seed in reached:
            if seed in seen:
                continue
            stack = [(seed, 0)]
            seen.add(seed)
            while stack:
                current, index = stack[-1]
                outs = fwd.get(current, ())
                if index < len(outs):
                    stack[-1] = (current, index + 1)
                    nxt = outs[index]
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append((nxt, 0))
                else:
                    stack.pop()
                    order.append(current)

        seen = set()
        sccs: list = []
        for node in reversed(order):
            if node in seen:
                continue
            comp: list = []
            stack = [node]
            seen.add(node)
            while stack:
                current = stack.pop()
                comp.append(current)
                for prev in rev_local.get(current, ()):
                    if prev not in seen:
                        seen.add(prev)
                        stack.append(prev)
            sccs.append(comp)

        if not sccs:
            return {start}
        start_comp = next((comp for comp in sccs if start in comp), None)
        # Rooms you cannot leave (bomb upgrade, charge beam) are tiny components.
        # The intro spawn is often one-way, so the main roam can be a different
        # component than the start. Prefer the largest component you can move
        # around in, and ignore one-room lock-ins.
        others = [
            comp for comp in sccs
            if comp is not start_comp and len(comp) >= 4
        ]
        anchor = max(others, key=len) if others else (start_comp or [start])
        targets = set(anchor)
        if start_comp:
            targets.update(start_comp)
        else:
            targets.add(start)
        return targets

    def _forward_hits(
        self,
        origin: NodeId,
        goals: AbstractSet[NodeId],
        inventory: FrozenSet[str],
    ) -> bool:
        if origin in goals:
            return True
        seen: Set[NodeId] = {origin}
        queue: deque[NodeId] = deque((origin,))
        while queue:
            current = queue.popleft()
            for target, requirement in self._adj.get(current, ()):
                if target in seen:
                    continue
                if not self.evaluate_requirement(requirement, inventory):
                    continue
                if target in goals:
                    return True
                seen.add(target)
                queue.append(target)
        return False

    def _grant_safe_events(
        self,
        inv: Set[str],
        safe: AbstractSet[NodeId],
        exclude: FrozenSet[str],
    ) -> bool:
        """Collect events standing in rooms that can already reach the start.

        Skips negated events: collecting those can close the path back.
        """
        added = False
        negated = self._negated_event_items
        for node, event_item in self._event_items.items():
            if event_item in exclude or event_item in inv or event_item in negated:
                continue
            if node not in safe:
                continue
            inv.add(event_item)
            added = True
        return added

    def _grant_one_negated_safe_event(
        self,
        inv: Set[str],
        safe: AbstractSet[NodeId],
        start: NodeId,
        exclude: FrozenSet[str],
    ) -> bool:
        """Collect negated events already inside rooms that can reach the start.

        Tries them together first. An event is kept only when its node can still
        reach the start with every candidate set. If the batch locks every
        candidate out, fall back to the first event that is safe on its own.
        """
        negated = self._negated_event_items
        candidates = [
            (node, event_item)
            for node, event_item in self._event_items.items()
            if event_item in negated
            and event_item not in inv
            and event_item not in exclude
            and node in safe
        ]
        if not candidates:
            return False
        trial = set(inv)
        trial.update(event_item for _node, event_item in candidates)
        trial_key = frozenset(trial)
        reached = self._bfs_once(trial_key, start)
        targets = self._roam_targets(reached, trial_key, start)
        escapable = self._nodes_that_can_reach_any(targets, trial_key)
        kept = [event_item for node, event_item in candidates if node in escapable]
        if kept:
            inv.update(kept)
            return True
        for node, event_item in candidates:
            if self._forward_hits(node, targets, frozenset(inv | {event_item})):
                inv.add(event_item)
                return True
        return False

    def _grant_one_negated_stuck_event(
        self,
        inv: Set[str],
        reached: AbstractSet[NodeId],
        escapable: AbstractSet[NodeId],
        start: NodeId,
        exclude: FrozenSet[str],
    ) -> bool:
        """Collect one negated event in a pocket when triggering it opens the way out.

        Boss rooms and central units are modeled this way: the node cannot reach
        the start until the event is set, and the event is also a negate somewhere
        else in the graph. The pickup item is still not assumed.
        """
        negated = self._negated_event_items
        for node, event_item in self._event_items.items():
            if event_item not in negated or event_item in inv or event_item in exclude:
                continue
            if node not in reached or node in escapable:
                continue
            trial = frozenset(inv | {event_item})
            reached_now = self._bfs_once(trial, start)
            targets = self._roam_targets(reached_now, trial, start)
            if self._forward_hits(node, targets, trial):
                inv.add(event_item)
                return True
        return False

    def _pocket_rescue(
        self,
        inv: Set[str],
        reached: AbstractSet[NodeId],
        escapable: AbstractSet[NodeId],
        start: NodeId,
        exclude: FrozenSet[str],
    ) -> bool:
        """Collect events inside a no-return pocket when those events open a way out.

        The item at a pickup is not assumed. A switch (event) in the room counts
        only if, after triggering it, some node in the pocket can reach the start.
        """
        stuck = reached - escapable
        if not stuck:
            return False
        local = set(inv)
        before = set(local)
        seeds = list(stuck)
        goals = escapable | {start}
        for _ in range(len(self._event_items) + 1):
            hit, grew = self._pocket_bfs(seeds, local, goals, exclude)
            if hit and (local - before):
                inv.update(local)
                return True
            if not grew:
                return False
        return False

    def _pocket_bfs(
        self,
        seeds: list,
        local: Set[str],
        goals: AbstractSet[NodeId],
        exclude: FrozenSet[str],
    ) -> Tuple[bool, bool]:
        """Walk a stuck pocket. Returns (hit escape, gained one non-negated event)."""
        negated = self._negated_event_items
        seen: Set[NodeId] = set(seeds)
        queue: deque[NodeId] = deque(seeds)
        while queue:
            current = queue.popleft()
            event_item = self._event_items.get(current)
            if (
                event_item
                and event_item not in local
                and event_item not in exclude
                and event_item not in negated
            ):
                local.add(event_item)
                return False, True
            if current in goals:
                return True, False
            inv_key = frozenset(local)
            for target, requirement in self._adj.get(current, ()):
                if target in seen:
                    continue
                if not self.evaluate_requirement(requirement, inv_key):
                    continue
                if target in goals:
                    return True, False
                seen.add(target)
                queue.append(target)
        return False, False

    def _reachable_with_escape(
        self,
        inventory: FrozenSet[str],
        start: NodeId,
        exclude: FrozenSet[str],
    ) -> Set[NodeId]:
        """Reachable nodes the player can also leave.

        Escape means a path back to the start component, or into the largest
        roaming component (the main area you can move around in after a one-way
        out of the intro). A one-room lock-in is not that component. The pickup
        in the room is never assumed, so the Dairon bomb upgrade and the Artaria
        charge beam room stay out of logic until an exit is already open.
        """
        inv: Set[str] = set(inventory)
        limit = len(self._event_items) + 3
        safe: Set[NodeId] = {start}
        for _ in range(limit):
            frozen = frozenset(inv)
            reached = self._bfs_once(frozen, start)
            targets = self._roam_targets(reached, frozen, start)
            escapable = self._nodes_that_can_reach_any(targets, frozen)
            safe = reached & escapable
            if self._grant_safe_events(inv, safe, exclude):
                continue
            if self._grant_one_negated_safe_event(inv, safe, start, exclude):
                continue
            if self._grant_one_negated_stuck_event(inv, reached, escapable, start, exclude):
                continue
            if self._pocket_rescue(inv, reached, escapable, start, exclude):
                continue
            return safe
        frozen = frozenset(inv)
        return self._bfs_once(frozen, start) & self._nodes_that_can_reach(start, frozen)

    def get_reachable_nodes(
        self,
        inventory: FrozenSet[str],
        start: Optional[NodeId] = None,
        collect_events: bool = True,
        exclude_auto_events: Optional[AbstractSet[str]] = None,
    ) -> Set[NodeId]:
        """BFS from start, optionally granting event items as their nodes become reachable."""
        start = start or self.starting_node
        exclude = frozenset(exclude_auto_events or ())
        dangerous = self.dangerous_logic_enabled()
        # Cache only the default generation path (full auto-collect, no excludes).
        # _ignore_tricks is stable for a whole search, and the cache is cleared
        # when that flag toggles, so those results can be reused too.
        # The dangerous-logic flag is part of the key so on/off cannot share a result.
        cache_ok = (
            collect_events
            and not exclude
            and start == self.starting_node
        )
        cache_key = (inventory, dangerous)
        if cache_ok and cache_key in self._reachable_cache:
            return self._reachable_cache[cache_key]

        if not collect_events:
            return self._bfs_once(inventory, start)

        # Off: a node is in logic only when it is reachable and can get back to
        # the start with the items already owned (events along a real escape count;
        # the pickup in the room does not). On: reachable is enough.
        if not dangerous:
            reachable = self._reachable_with_escape(inventory, start, exclude)
            if cache_ok:
                self._reachable_cache[cache_key] = reachable
                if len(self._reachable_cache) > 8192:
                    self._reachable_cache.clear()
            return reachable

        inv: Set[str] = set(inventory)
        reachable = {start}
        for _ in range(len(self._event_items) + 2):
            # Expand from every node already reached so collecting a room event
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
            self._reachable_cache[cache_key] = reachable
            if len(self._reachable_cache) > 8192:
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

    def _note_env_damage(
        self,
        name: str,
        amount: int,
        inventory: FrozenSet[str],
        items: list,
        seen_items: Set[str],
        *,
        missing: bool,
    ) -> bool:
        """Record suit immunity or the HP a Heat/Cold/Lava edge actually costs.

        The Suitless trick is a sibling resource and is recorded there, at the
        level that edge asks for. This does not invent an extra trick floor.
        """
        taken = self._env_damage_taken(name, amount, inventory)
        if taken is None:
            return False
        has_varia = "Varia Suit" in inventory
        has_grav = "Gravity Suit" in inventory
        if name == "Heat":
            if has_varia:
                if not missing:
                    self._add_unique(items, seen_items, "Varia Suit")
            elif has_grav:
                if not missing:
                    self._add_unique(items, seen_items, "Gravity Suit")
            elif missing:
                self._add_unique(items, seen_items, "Varia Suit")
        elif name in ("Cold", "Lava"):
            if has_grav:
                if not missing:
                    self._add_unique(items, seen_items, "Gravity Suit")
            elif missing:
                self._add_unique(items, seen_items, "Gravity Suit")
            if has_varia and taken > 0.0 and not missing:
                self._add_unique(items, seen_items, "Varia Suit")
        if taken > 0.0:
            self._add_unique(
                items,
                seen_items,
                self._item_fact_label("Energy", self._min_energy_to_survive(taken)),
            )
        return True

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
        if self._note_env_damage(name, amount, inventory, items, seen_items, missing=False):
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
        if self._note_env_damage(name, amount, inventory, items, seen_items, missing=True):
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

    # Abilities the pause-map panel can list. Order is the display order.
    # Tokens are what evaluate_requirement understands; the label is the panel text.
    _PANEL_ABILITIES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
        ("Morph Ball", ("Morph Ball",)),
        ("Bomb", ("Bomb",)),
        ("Cross Bomb", ("Cross Bomb",)),
        ("Power Bomb", ("Power Bomb", "__pb_ammo__")),
        ("Spider Magnet", ("Spider Magnet",)),
        ("Charge Beam", ("Charge Beam",)),
        ("Diffusion Beam", ("Diffusion Beam",)),
        ("Wide Beam", ("Wide Beam",)),
        ("Plasma Beam", ("Plasma Beam",)),
        ("Wave Beam", ("Wave Beam",)),
        ("Grapple Beam", ("Grapple Beam",)),
        ("Super Missile", ("Super Missile",)),
        ("Ice Missile", ("Ice Missile",)),
        ("Storm Missile", ("Storm Missile",)),
        ("Phantom Cloak", ("Phantom Cloak",)),
        ("Flash Shift", ("Flash Shift",)),
        ("Pulse Radar", ("Pulse Radar",)),
        ("Varia Suit", ("Varia Suit",)),
        ("Gravity Suit", ("Gravity Suit",)),
        ("Speed Booster", ("Speed Booster",)),
        ("Spin Boost", ("Spin Boost",)),
        ("Space Jump", ("Space Jump",)),
        ("Screw Attack", ("Screw Attack",)),
        ("Flash Shift chains", ("__flash_upgrade_9__",)),
        ("Missiles", ("__missile_ammo_999__",)),
        ("Energy", ("__energy_9999__",)),
    )

    def _panel_base_inventory(self) -> FrozenSet[str]:
        """Gear the seed starts with, so it is not listed as a requirement."""
        inv = {"__missile_ammo_15__", "__energy_99__"}
        try:
            start_missiles = int(self.world.options.starting_missiles.value)
        except Exception:
            start_missiles = 15
        if start_missiles > 0:
            inv.add(f"__missile_ammo_{start_missiles}__")
        try:
            if int(self.world.options.start_with_pulse_radar.value) > 0:
                inv.add("Pulse Radar")
        except Exception:
            pass
        try:
            if int(self.world.options.starting_power_bombs.value) > 0:
                inv.add("Power Bomb")
                inv.add("__pb_ammo__")
        except Exception:
            pass
        return frozenset(inv)

    def _panel_inventory(self, labels: AbstractSet[str]) -> FrozenSet[str]:
        inv = set(self._panel_base_inventory())
        token_of = {label: tokens for label, tokens in self._PANEL_ABILITIES}
        for label in labels:
            inv.update(token_of.get(label, (label,)))
        return frozenset(inv)

    def _panel_help_labels(self, req, inventory: FrozenSet[str]) -> Set[str]:
        """Ability names that could satisfy a failing requirement."""
        found: Set[str] = set()
        if not isinstance(req, dict):
            return found
        req_type = req.get("type")
        if req_type in (None, "trivial", "impossible"):
            return found
        if req_type == "template":
            tmpl = self.parser.templates.get(req.get("data"))
            inner = tmpl.get("requirement") if isinstance(tmpl, dict) else tmpl
            return self._panel_help_labels(inner, inventory)
        if req_type == "and":
            for item in (req.get("data") or {}).get("items") or []:
                if not self.evaluate_requirement(item, inventory):
                    found |= self._panel_help_labels(item, inventory)
            return found
        if req_type == "or":
            items = (req.get("data") or {}).get("items") or []
            if any(self.evaluate_requirement(item, inventory) for item in items):
                return found
            for item in items:
                found |= self._panel_help_labels(item, inventory)
            return found
        if req_type != "resource":
            return found
        data = req.get("data") or {}
        if data.get("negate"):
            return found
        if self.evaluate_requirement(req, inventory):
            return found
        rtype = data.get("type")
        rname = data.get("name")
        if rtype == "items":
            ap = ITEM_SHORT_TO_AP.get(rname) if rname in ITEM_SHORT_TO_AP else None
            if ap == "__missile_ammo__":
                found.add("Missiles")
            elif ap == "__pb_ammo__":
                found.add("Power Bomb")
            elif ap == "__energy__":
                found.add("Energy")
            elif ap == "Flash Shift Upgrade":
                found.add("Flash Shift chains")
            elif ap and ap != "Metroid DNA":
                found.add(ap)
            return found
        if rtype == "damage":
            if rname == "Heat":
                found.add("Varia Suit")
                found.add("Energy")
            elif rname in ("Cold", "Lava"):
                found.add("Gravity Suit")
                found.add("Energy")
            elif rname == "Damage":
                found.add("Energy")
        return found

    def _frontier_abilities(
        self,
        inventory: FrozenSet[str],
        reachable: Optional[Set[NodeId]] = None,
    ) -> Set[str]:
        if reachable is None:
            reachable = self.get_reachable_nodes(inventory)
        found: Set[str] = set()
        known = {label for label, _tokens in self._PANEL_ABILITIES}
        for node in reachable:
            for target, req in self._adj.get(node, ()):
                if target in reachable:
                    continue
                if self.evaluate_requirement(req, inventory):
                    continue
                for label in self._panel_help_labels(req, inventory):
                    if label in known:
                        found.add(label)
        return found

    def minimal_abilities(
        self,
        node: NodeId,
        *,
        ignore_tricks: bool = False,
        max_size: int = 6,
        max_states: int = 800,
    ) -> Optional[list]:
        """Smallest ability set that reaches node under the seed trickset.

        Returns None when no set of at most max_size abilities reaches it.
        Tricks are not listed; ignore_tricks treats them as allowed so an
        out-of-logic check can still report the items that reach it.
        """
        self._ignore_tricks = ignore_tricks
        if ignore_tricks:
            self._reachable_cache.clear()
        try:
            order = [label for label, _tokens in self._PANEL_ABILITIES]
            rank = {label: i for i, label in enumerate(order)}

            def reached(labels: FrozenSet[str]) -> bool:
                return node in self.get_reachable_nodes(self._panel_inventory(labels))

            empty: FrozenSet[str] = frozenset()
            if reached(empty):
                return []
            queue: deque[FrozenSet[str]] = deque([empty])
            seen = {empty}
            while queue and len(seen) <= max_states:
                current = queue.popleft()
                if len(current) >= max_size:
                    continue
                inventory = self._panel_inventory(current)
                reachable_now = self.get_reachable_nodes(inventory)
                for label in self._frontier_abilities(inventory, reachable_now):
                    if label in current:
                        continue
                    nxt = frozenset(set(current) | {label})
                    if nxt in seen:
                        continue
                    seen.add(nxt)
                    if reached(nxt):
                        return sorted(nxt, key=lambda name: rank.get(name, 99))
                    queue.append(nxt)
            return None
        finally:
            if ignore_tricks:
                self._ignore_tricks = False
                self._reachable_cache.clear()

    def map_panel_lines(self, node: NodeId) -> list:
        """Lines for the pause-map panel. Empty means nothing is required."""
        catalog = self.catalog_panel_lines([node])
        return list(catalog.get(node) or [])

    def catalog_panel_lines(self, nodes: Iterable[NodeId]) -> Dict[NodeId, list]:
        """Minimum ability lines for many checks, searched once per mode.

        A check the trickset can obtain gets that smallest item set. A check
        the trickset cannot obtain gets only the items that reach it.
        """
        pending = [node for node in nodes]
        solved: Dict[NodeId, list] = {}
        self._panel_reach_only = set()
        self._fill_panel_catalog(pending, solved, ignore_tricks=False)
        left = [node for node in pending if node not in solved]
        if left:
            before = set(solved)
            self._fill_panel_catalog(left, solved, ignore_tricks=True)
            self._panel_reach_only.update(node for node in solved if node not in before)
        still = [node for node in pending if node not in solved]
        for node in still:
            owned = self._shrink_panel_labels(node, ignore_tricks=False)
            if owned is not None:
                solved[node] = owned
                continue
            reached = self._shrink_panel_labels(node, ignore_tricks=True)
            if reached is not None:
                solved[node] = reached
                self._panel_reach_only.add(node)
        return solved

    def _shrink_panel_labels(self, node: NodeId, *, ignore_tricks: bool) -> Optional[list]:
        """Drop abilities until the set is minimal. Used when the breadth search stops early."""
        self._ignore_tricks = ignore_tricks
        self._reachable_cache.clear()
        try:
            labels = [label for label, _tokens in self._PANEL_ABILITIES]
            rank = {label: i for i, label in enumerate(labels)}
            full = frozenset(labels)
            if node not in self.get_reachable_nodes(self._panel_inventory(full)):
                return None
            have = set(labels)
            changed = True
            while changed:
                changed = False
                for label in labels:
                    if label not in have:
                        continue
                    trial = have - {label}
                    if node in self.get_reachable_nodes(self._panel_inventory(frozenset(trial))):
                        have.remove(label)
                        changed = True
            return sorted(have, key=lambda name: rank.get(name, 99))
        finally:
            self._ignore_tricks = False
            self._reachable_cache.clear()

    def _fill_panel_catalog(
        self,
        nodes: list,
        solved: Dict[NodeId, list],
        *,
        ignore_tricks: bool,
    ) -> None:
        self._ignore_tricks = ignore_tricks
        self._reachable_cache.clear()
        try:
            order = [label for label, _tokens in self._PANEL_ABILITIES]
            rank = {label: i for i, label in enumerate(order)}
            targets: Set[NodeId] = set(nodes)
            empty: FrozenSet[str] = frozenset()
            queue: deque[FrozenSet[str]] = deque([empty])
            seen = {empty}
            while queue and targets and len(seen) <= 6000:
                current = queue.popleft()
                inventory = self._panel_inventory(current)
                reachable = self.get_reachable_nodes(inventory)
                hit = targets & reachable
                if hit:
                    lines = sorted(current, key=lambda name: rank.get(name, 99))
                    for node in hit:
                        solved[node] = lines
                        targets.discard(node)
                    if not targets:
                        break
                if len(current) >= 6:
                    continue
                for label in self._frontier_abilities(inventory, reachable):
                    if label in current:
                        continue
                    nxt = frozenset(set(current) | {label})
                    if nxt in seen:
                        continue
                    seen.add(nxt)
                    queue.append(nxt)
        finally:
            self._ignore_tricks = False
            self._reachable_cache.clear()


def map_panel_rows(option_values: Mapping) -> list:
    """Minimum ability rows for every pickup, under the seed's trickset.

    Each row is scenario, map x/y, area name, and the panel lines. An empty
    line list means the check needs no listed ability. Out-of-logic checks
    already contain only the items that reach them.
    """
    import json

    class _Holder:
        def __init__(self, value):
            self.value = value

    class _Options:
        def __init__(self, values: Mapping):
            self._values = {str(key): val for key, val in dict(values).items()}

        def __getattr__(self, name: str):
            if name not in self._values:
                raise AttributeError(name)
            return _Holder(self._values[name])

    class _World:
        player = 1

        def __init__(self, values: Mapping):
            self.options = _Options(values)

    logic = DreadLogic(_World(option_values))
    pickup_path = Path(__file__).parent / "dread_pickup_actors.json"
    pickups = json.loads(pickup_path.read_text(encoding="utf-8"))
    nodes = []
    meta = []
    for info in pickups.values():
        if not isinstance(info, dict):
            continue
        region = info.get("region")
        area = info.get("area")
        node = info.get("node")
        scenario = info.get("scenario")
        coords = info.get("coordinates") or {}
        if not (region and area and node and scenario):
            continue
        try:
            x = int(round(float(coords["x"])))
            y = int(round(float(coords["y"])))
        except (KeyError, TypeError, ValueError):
            continue
        node_id = (str(region), str(area), str(node))
        nodes.append(node_id)
        meta.append((str(scenario), x, y, str(area), node_id))
    catalog = logic.catalog_panel_lines(nodes)
    rows = []
    for scenario, x, y, area, node_id in meta:
        rows.append({
            "scenario": scenario,
            "x": x,
            "y": y,
            "area": area,
            "lines": list(catalog.get(node_id) or []),
        })
    return rows

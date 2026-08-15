"""Flash Shift pool / grant helpers for Metroid Dread Archipelago.

Modes (see Options.py):
- Vanilla ON: one main Flash Shift = ITEM_GHOST_AURA + included_ammo chains (RDV/ODR).
- Vanilla OFF + Require Main ON: main unlocks ability; N upgrades add chains only.
- Vanilla OFF + Require Main OFF: progressive upgrades — first unlocks ability
  (0 chains on first grant); later upgrades add chains.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple


def _opt_bool(options: Any, name: str, default: bool = False) -> bool:
    opt = getattr(options, name, None)
    if opt is None:
        return default
    try:
        return bool(opt.value)
    except Exception:
        return bool(opt)


def _opt_int(options: Any, name: str, default: int = 0) -> int:
    opt = getattr(options, name, None)
    if opt is None:
        return default
    try:
        return int(opt.value)
    except Exception:
        try:
            return int(opt)
        except Exception:
            return default


def plan_from_options(options: Any) -> Dict[str, Any]:
    """Resolve Flash Shift pool plan from player options."""
    vanilla = _opt_bool(options, "vanilla_flash_shift_behaviour", True)
    require_main = _opt_bool(options, "flash_shift_upgrade_requires_main_item", True)
    upgrade_count = max(1, min(5, _opt_int(options, "flash_shift_upgrade_count", 3)))
    included_ammo = max(0, _opt_int(options, "flash_shift_included_ammo", 2))
    upgrade_amount = max(1, _opt_int(options, "flash_shift_upgrade_amount", 1))

    if vanilla:
        return {
            "vanilla": True,
            "require_main": False,
            "main_count": 1,
            "upgrade_count": 0,
            "included_ammo": included_ammo if included_ammo > 0 else 2,
            "upgrade_amount": upgrade_amount,
        }
    return {
        "vanilla": False,
        "require_main": require_main,
        "main_count": 1 if require_main else 0,
        "upgrade_count": upgrade_count,
        "included_ammo": included_ammo,
        "upgrade_amount": upgrade_amount,
    }


def plan_from_extras(extras: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Resolve plan from patch_extras / slot_data (client + patcher)."""
    extras = extras or {}
    if "vanilla_flash_shift_behaviour" in extras:
        class _O:
            pass

        o = _O()
        o.vanilla_flash_shift_behaviour = type(
            "T", (), {"value": int(bool(extras.get("vanilla_flash_shift_behaviour", True)))}
        )()
        o.flash_shift_upgrade_requires_main_item = type(
            "T",
            (),
            {"value": int(bool(extras.get("flash_shift_upgrade_requires_main_item", True)))},
        )()
        o.flash_shift_upgrade_count = type(
            "T", (), {"value": int(extras.get("flash_shift_upgrade_count", 3))}
        )()
        o.flash_shift_included_ammo = type(
            "T", (), {"value": int(extras.get("flash_shift_included_ammo", 2))}
        )()
        o.flash_shift_upgrade_amount = type(
            "T", (), {"value": int(extras.get("flash_shift_upgrade_amount", 1))}
        )()
        return plan_from_options(o)
    # Legacy seeds (pre-1.5.0): progressive upgrades only — first unlocks ability.
    return {
        "vanilla": False,
        "require_main": False,
        "main_count": 0,
        "upgrade_count": int(extras.get("flash_shift_upgrade_count", 7) or 7),
        "included_ammo": int(extras.get("flash_shift_included_ammo", 2) or 2),
        "upgrade_amount": int(extras.get("flash_shift_upgrade_amount", 1) or 1),
    }


def main_resources(included_ammo: int) -> list:
    """ODR resources for the main Flash Shift item (ability + chains)."""
    chains = max(0, int(included_ammo))
    resources = [{"item_id": "ITEM_GHOST_AURA", "quantity": 1}]
    if chains > 0:
        resources.append(
            {"item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "quantity": chains}
        )
    return resources


def upgrade_resources(amount: int = 1) -> list:
    """ODR resources for one Flash Shift Upgrade (chains only)."""
    return [
        {
            "item_id": "ITEM_UPGRADE_FLASH_SHIFT_CHAIN",
            "quantity": max(1, int(amount)),
        }
    ]


def logical_ability_and_chains(
    counts: Mapping[str, int],
    plan: Mapping[str, Any],
) -> Tuple[bool, int]:
    """Return (has_flash_shift_ability, chain_count) for logic / tracker."""
    flash_main = int(counts.get("Flash Shift", 0) or 0) > 0
    upgrades = int(counts.get("Flash Shift Upgrade", 0) or 0)
    included = int(plan.get("included_ammo", 2) or 0)
    up_amt = max(1, int(plan.get("upgrade_amount", 1) or 1))

    if plan.get("vanilla"):
        has_ability = flash_main
        chains = included if flash_main else 0
        return has_ability, chains

    if plan.get("require_main"):
        has_ability = flash_main
        chains = (included if flash_main else 0) + upgrades * up_amt
        return has_ability, chains

    # Progressive: first upgrade unlocks ability and grants 0 chains.
    has_ability = upgrades >= 1 or flash_main
    if upgrades >= 1:
        chains = (upgrades - 1) * up_amt
        if flash_main:
            chains += included
    else:
        chains = included if flash_main else 0
    return has_ability, chains


def apply_resources_to_pickup_entry(
    entry: MutableMapping[str, Any],
    item_name: str,
    plan: Mapping[str, Any],
) -> None:
    """Rewrite local Flash Shift / Upgrade pickup resources to match the plan."""
    if not isinstance(entry, dict) or entry.get("resources") is None:
        return
    if item_name == "Flash Shift":
        flat = main_resources(int(plan.get("included_ammo", 2) or 2))
        entry["resources"] = [flat]
    elif item_name == "Flash Shift Upgrade":
        flat = upgrade_resources(int(plan.get("upgrade_amount", 1) or 1))
        entry["resources"] = [flat]


def infer_requires_main_from_pickups(pickups: Sequence[Mapping[str, Any]]) -> bool:
    """Infer Require-Main from placed pickup resources (for Lua finalize)."""
    has_ghost = False
    has_chain_only = False
    for pickup in pickups or []:
        stages = pickup.get("resources") or []
        ids = set()
        for stage in stages:
            if not isinstance(stage, (list, tuple)):
                continue
            for res in stage:
                if isinstance(res, dict) and res.get("item_id"):
                    ids.add(str(res["item_id"]))
        if "ITEM_GHOST_AURA" in ids:
            has_ghost = True
        if ids == {"ITEM_UPGRADE_FLASH_SHIFT_CHAIN"}:
            has_chain_only = True
    return bool(has_chain_only and has_ghost)

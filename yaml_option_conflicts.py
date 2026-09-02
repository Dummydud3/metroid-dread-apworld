"""Static YAML option conflicts for Hub sphere-0 probe (trick vs pool/ammo).

Keep thresholds in sync with dread-client-app/main.js ``yamlOptionConflicts``.
"""
from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class Conflict(TypedDict):
    id: str
    severity: str
    title: str
    message: str
    fix: str
    fields: List[str]


def _as_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def effective_energy_tanks(values: Dict[str, Any]) -> int:
    """Tank-equivalents available in the pool for starvation checks."""
    tanks = max(0, _as_int(values.get("energy_tanks"), 8))
    parts = max(0, _as_int(values.get("energy_parts"), 16))
    immediate = _as_int(values.get("immediate_energy_parts"), 1) != 0
    if immediate:
        return tanks + parts
    return tanks + parts // 4


def max_obtainable_energy(values: Dict[str, Any]) -> int:
    """Peak HP from energy_per_tank × tanks/parts (same formula as world gen)."""
    ept = max(1, _as_int(values.get("energy_per_tank"), 100))
    tanks = max(0, _as_int(values.get("energy_tanks"), 8))
    parts = max(0, _as_int(values.get("energy_parts"), 16))
    return int((ept - 1) + tanks * ept + parts * (ept / 4.0))


def combat_boss_energy_need(combat: int) -> int:
    """
    Hardest Damage energy gate still required at this Combat level.

    Matches Raven Beak / Gold Chozo-style RDV energy OR branches:
    Disabled → 799; Beginner → 549; Intermediate → 299; Advanced+ → 0.
    """
    if combat <= 0:
        return 799
    if combat == 1:
        return 549
    if combat == 2:
        return 299
    return 0


def analyze_option_conflicts(values: Dict[str, Any]) -> List[Conflict]:
    """Return warning-level conflicts (never escalate to error by themselves)."""
    combat = _as_int(values.get("combat_tricks"), 1)
    heat_cold = _as_int(values.get("heat_cold_runs"), 0)
    tanks = max(0, _as_int(values.get("energy_tanks"), 8))
    parts = max(0, _as_int(values.get("energy_parts"), 16))
    ept = max(0, _as_int(values.get("energy_per_tank"), 100))
    missiles = max(0, _as_int(values.get("starting_missiles"), 15))
    effective = effective_energy_tanks(values)
    max_energy = max_obtainable_energy(values)
    energy_need = combat_boss_energy_need(combat)

    out: List[Conflict] = []

    if energy_need > 0 and max_energy < energy_need:
        combat_label = (
            "Disabled"
            if combat <= 0
            else "Beginner"
            if combat == 1
            else "Intermediate"
        )
        gen_note = (
            " Generation may raise Energy Per Tank or force Combat Beginner."
            if combat <= 0
            else ""
        )
        out.append(
            {
                "id": "energy_pool_below_combat_gate",
                "severity": "warning",
                "title": "Energy pool too low for Combat setting",
                "message": (
                    f"Max energy from the pool is ~{max_energy}, but Combat "
                    f"{combat_label} still expects >={energy_need} for hard boss "
                    f"Damage gates (e.g. Raven Beak / Gold Chozo).{gen_note}"
                ),
                "fix": (
                    "Raise Energy Tanks/Parts or Energy Per Tank, or raise Combat."
                ),
                "fields": [
                    "combat_tricks",
                    "energy_tanks",
                    "energy_parts",
                    "energy_per_tank",
                ],
            }
        )

    if combat == 0 and effective < 4:
        out.append(
            {
                "id": "combat_energy_starved",
                "severity": "warning",
                "title": "Combat Disabled with low energy pool",
                "message": (
                    "Combat is Disabled while the energy pool is thin "
                    f"(~{effective} tank-equivalent(s)). Early bosses may need "
                    "Energy in logic without Combat Beginner skips."
                ),
                "fix": (
                    "Set Combat to Beginner (default), or raise Energy Tanks/Parts."
                ),
                "fields": ["combat_tricks", "energy_tanks", "energy_parts"],
            }
        )

    if combat <= 1 and tanks == 0 and parts == 0:
        out.append(
            {
                "id": "combat_energy_empty",
                "severity": "warning",
                "title": "No energy in the item pool",
                "message": (
                    "Energy Tanks and Energy Parts are both 0 while Combat is "
                    "Disabled or Beginner - bosses/heat have no energy upgrades."
                ),
                "fix": "Add Energy Tanks/Parts, or raise Combat above Beginner.",
                "fields": ["combat_tricks", "energy_tanks", "energy_parts"],
            }
        )

    if combat <= 1 and ept < 50:
        out.append(
            {
                "id": "energy_per_tank_low",
                "severity": "warning",
                "title": "Low Energy Per Tank with low Combat",
                "message": (
                    f"Energy Per Tank is {ept} while Combat is Disabled/Beginner - "
                    "boss and heat/cold checks stay painful."
                ),
                "fix": "Raise Energy Per Tank (default 100) or raise Combat.",
                "fields": ["combat_tricks", "energy_per_tank"],
            }
        )

    if missiles == 0:
        out.append(
            {
                "id": "starting_missiles_zero",
                "severity": "warning",
                "title": "Starting Missiles is 0",
                "message": (
                    "Starting Missiles is 0 - early missile doors and combat have "
                    "no ammo until tanks are found."
                ),
                "fix": "Set Starting Missiles to at least 15 (default) unless intentional.",
                "fields": ["starting_missiles"],
            }
        )

    if heat_cold >= 2 and effective < 4:
        out.append(
            {
                "id": "heat_cold_energy",
                "severity": "warning",
                "title": "Heat/Cold Runs with low energy pool",
                "message": (
                    "Heat/Cold Runs is Intermediate+ while the energy pool is thin "
                    f"(~{effective} tank-equivalent(s))."
                ),
                "fix": "Raise Energy Tanks/Parts, or lower Heat/Cold Runs.",
                "fields": ["heat_cold_runs", "energy_tanks", "energy_parts"],
            }
        )

    heat_dps = max(0, _as_int(values.get("constant_heat_damage"), 20))
    cold_dps = max(0, _as_int(values.get("constant_cold_damage"), 20))
    if heat_cold >= 1 and effective < 4 and (heat_dps > 20 or cold_dps > 20):
        hot = []
        if heat_dps > 20:
            hot.append(f"heat {heat_dps}")
        if cold_dps > 20:
            hot.append(f"cold {cold_dps}")
        out.append(
            {
                "id": "heat_cold_dps_energy",
                "severity": "warning",
                "title": "High env DPS with Heat/Cold Runs and thin energy",
                "message": (
                    "Heat/Cold Runs is on with constant "
                    f"{' / '.join(hot)} DPS (>20) and a thin energy pool "
                    f"(~{effective} tank-equivalent(s))."
                ),
                    "fix": (
                    "Lower Constant Heat/Cold DPS to <=20, raise Energy Tanks/Parts, "
                    "or disable Heat/Cold Runs."
                ),
                "fields": [
                    "heat_cold_runs",
                    "constant_heat_damage",
                    "constant_cold_damage",
                    "energy_tanks",
                    "energy_parts",
                ],
            }
        )

    damage_boost = _as_int(values.get("damage_boost"), 0)
    if damage_boost >= 2 and effective < 4:
        out.append(
            {
                "id": "damage_boost_energy",
                "severity": "warning",
                "title": "Damage Boost with low energy pool",
                "message": (
                    "Damage Boost is Intermediate+ while the energy pool is thin "
                    f"(~{effective} tank-equivalent(s)) - knockback routes spend health."
                ),
                "fix": "Raise Energy Tanks/Parts, or lower Damage Boost.",
                "fields": ["damage_boost", "energy_tanks", "energy_parts"],
            }
        )

    immediate = _as_int(values.get("immediate_energy_parts"), 1) != 0
    if not immediate and parts < 4:
        out.append(
            {
                "id": "immediate_parts_off_low",
                "severity": "warning",
                "title": "Immediate Energy Parts off with few parts",
                "message": (
                    f"Immediate Energy Parts is off and Energy Parts is {parts} "
                    "(need 4 fragments for one tank-equivalent)."
                ),
                "fix": (
                    "Enable Immediate Energy Parts, or set Energy Parts to at least 4."
                ),
                "fields": ["immediate_energy_parts", "energy_parts"],
            }
        )

    access = str(values.get("accessibility") or "items").strip().lower()
    if access == "minimal":
        out.append(
            {
                "id": "accessibility_minimal_upgrade",
                "severity": "warning",
                "title": "Accessibility Minimal upgrades to Items",
                "message": (
                    "Accessibility Minimal is upgraded to Items during generation "
                    "(Metroid Bread victory clearance)."
                ),
                "fix": "Set Accessibility to Items (same effective result) or Full.",
                "fields": ["accessibility"],
            }
        )

    return out


def merge_conflicts_into_result(
    result: Dict[str, Any],
    conflicts: List[Conflict],
) -> Dict[str, Any]:
    """Attach conflicts and adjust severity/message per probe plan rules."""
    out = dict(result)
    out["conflicts"] = list(conflicts)
    if not conflicts:
        return out

    sev = str(out.get("severity") or "ok")
    has_error = any(str(c.get("severity") or "") == "error" for c in conflicts)
    messages = [c["message"] for c in conflicts]
    bullets = " ".join(f"* {m}" for m in messages)
    base_msg = str(out.get("message") or "")
    err = next((c for c in conflicts if str(c.get("severity") or "") == "error"), None)

    # Prefer accessibility Full's trick_alt for Hub field highlights when present.
    for c in conflicts:
        if c.get("id") == "accessibility_full_blocked" and c.get("trick_alt"):
            out["trick_alt"] = c["trick_alt"]
            if not out.get("fix_alt"):
                from worlds.metroid_bread.start_sphere0_tricks import format_trick_alt

                out["fix_alt"] = format_trick_alt(c["trick_alt"])
            break

    if has_error:
        out["severity"] = "error"
        out["title"] = (err or conflicts[0]).get("title") or "Option conflicts"
        out["message"] = f"{base_msg} {bullets}".strip() if sev == "ok" else (
            f"{base_msg} Also: {'; '.join(c['title'] for c in conflicts)}.".strip()
        )
        if not out.get("fix") and err is not None:
            out["fix"] = err.get("fix") or ""
        elif not out.get("fix"):
            out["fix"] = conflicts[0]["fix"]
    elif sev == "ok":
        out["severity"] = "warning"
        out["title"] = "Option conflicts"
        out["message"] = f"{base_msg} {bullets}".strip()
        if not out.get("fix"):
            out["fix"] = conflicts[0]["fix"]
    else:
        summary = "; ".join(c["title"] for c in conflicts)
        out["message"] = f"{base_msg} Also: {summary}.".strip()
    return out

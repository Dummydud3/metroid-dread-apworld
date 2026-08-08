"""
Build a synthetic Archipelago spoiler from live server LocationInfo + slot_data.

Used by MetroidDreadClient so players can patch without a local seed zip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


def _split_location_name(location_name: str) -> Optional[Tuple[str, str, str]]:
    """
    AP Dread location names are 'Region - Area - Node'.
    Node itself may contain ' - ', so only split on the first two separators.
    """
    parts = location_name.split(" - ", 2)
    if len(parts) != 3:
        return None
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def build_synthetic_spoiler(
    *,
    player_name: str,
    seed_name: str,
    starting_path: str,
    placements: Sequence[Tuple[str, str, str]],
    patch_extras: Optional[dict] = None,
    player_names: Optional[Mapping[int, str]] = None,
) -> str:
    """
    placements: list of (location_name, item_name, item_owner_name)
    """
    lines: List[str] = [
        f"Archipelago Version (server download)  -  Seed: {seed_name or 'unknown'}",
        "",
        f"Players:                         {max(1, len(player_names or {}))}",
        f"Game:                            Metroid Dread",
        "",
    ]

    # Multiworld-style player header so ap_to_patcher can resolve the slot.
    lines.append(f"Player 1: {player_name}")
    lines.append("Game: Metroid Dread")
    lines.append("")

    if starting_path:
        lines.append(f"Starting Location ({player_name}): {starting_path}")

    extras = dict(patch_extras or {})
    dna_locs = extras.pop("dna_locations", None)
    if extras:
        lines.append(
            f"DREAD_PATCH_EXTRAS_JSON:{player_name}:"
            + json.dumps(extras, separators=(",", ":"))
        )
    if dna_locs:
        lines.append(
            f"DREAD_DNA_LOCATIONS:{player_name}:"
            + json.dumps(list(dna_locs), separators=(",", ":"))
        )

    lines.append("")
    lines.append("Locations:")
    lines.append("")

    for location_name, item_name, item_owner in placements:
        loc = (location_name or "").strip()
        item = (item_name or "Unknown Item").strip()
        owner = (item_owner or player_name).strip() or player_name
        if not loc:
            continue
        lines.append(f"{loc} ({player_name}): {item} ({owner})")

    lines.append("")
    return "\n".join(lines) + "\n"


def placements_from_locations_info(
    *,
    location_ids: Iterable[int],
    locations_info: Mapping[int, object],
    location_name_lookup,
    item_name_lookup,
    player_names: Mapping[int, str],
    our_slot: int,
    our_name: str,
) -> List[Tuple[str, str, str]]:
    """
    Convert scouted NetworkItems into (location_name, item_name, owner_name).

    location_name_lookup(location_id) -> str
    item_name_lookup(item_id, player_id) -> str
    """
    out: List[Tuple[str, str, str]] = []
    for loc_id in sorted(location_ids):
        net = locations_info.get(loc_id)
        if net is None:
            continue
        try:
            item_id = int(net.item)
            owner_id = int(net.player)
        except Exception:
            continue
        try:
            loc_name = location_name_lookup(loc_id)
        except Exception:
            loc_name = f"Unknown Location {loc_id}"
        try:
            item_name = item_name_lookup(item_id, owner_id)
        except Exception:
            item_name = f"Unknown Item {item_id}"
        owner_name = player_names.get(owner_id) or (
            our_name if owner_id == our_slot else f"Player {owner_id}"
        )
        out.append((str(loc_name), str(item_name), str(owner_name)))
    return out


def write_synthetic_spoiler(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

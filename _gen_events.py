"""
Regenerate Events.py from logic_database.

Usage (from Archipelago-main):
  py -3.11 -m worlds.metroid_dread._gen_events
"""

from pathlib import Path
import json


def main():
    p = Path(__file__).parent / "logic_database"
    header = json.loads((p / "header.json").read_text(encoding="utf-8"))
    events_db = header.get("resource_database", {}).get("events", {})

    event_nodes = []
    for f in sorted(p.glob("*.json")):
        if f.name == "header.json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        region = d["name"]
        for area, ad in d.get("areas", {}).items():
            for node, nd in ad.get("nodes", {}).items():
                if nd.get("node_type") == "event":
                    en = nd.get("event_name")
                    if en:
                        event_nodes.append((region, area, node, en))

    def ap_event_name(event_key: str) -> str:
        long = (events_db.get(event_key) or {}).get("long_name") or event_key
        return f"Event - {long}"

    all_keys = set(events_db.keys()) | {e for *_, e in event_nodes}

    lines = [
        '"""',
        "Metroid Dread event items and locked event locations",
        "AUTO-GENERATED from logic_database — do not hand-edit.",
        "Regenerate: python -m worlds.metroid_dread._gen_events",
        '"""',
        "",
        "from typing import Dict, List, NamedTuple, Tuple",
        "from BaseClasses import ItemClassification",
        "from .Items import ItemData",
        "",
        "# RDV event resource name -> AP event item name",
        "EVENT_RESOURCE_TO_ITEM: Dict[str, str] = {",
    ]
    for key in sorted(all_keys):
        lines.append(f"    {key!r}: {ap_event_name(key)!r},")
    lines.append("}")
    lines.append("")
    lines.append("# Event items (id=None — not networked)")
    lines.append("event_item_table: Dict[str, ItemData] = {")
    for key in sorted(all_keys):
        name = ap_event_name(key)
        lines.append(f"    {name!r}: ItemData(None, ItemClassification.progression),")
    lines.append("}")
    lines.append("")
    lines.append("class EventLocationData(NamedTuple):")
    lines.append("    name: str")
    lines.append('    region: str  # AP area region key: "GameRegion/Area"')
    lines.append("    game_region: str")
    lines.append("    area: str")
    lines.append("    node: str")
    lines.append("    event_resource: str")
    lines.append("    event_item: str")
    lines.append("")
    lines.append("event_locations: List[EventLocationData] = [")
    for region, area, node, en in event_nodes:
        loc_name = f"{region} - {area} - {node}"
        ap_area = f"{region}/{area}"
        item = ap_event_name(en)
        lines.append(
            f"    EventLocationData({loc_name!r}, {ap_area!r}, {region!r}, "
            f"{area!r}, {node!r}, {en!r}, {item!r}),"
        )
    lines.append("]")
    lines.append("")
    lines.append("# (game_region, area, node) -> event location name")
    lines.append("EVENT_NODE_TO_LOCATION: Dict[Tuple[str, str, str], str] = {")
    for region, area, node, en in event_nodes:
        loc_name = f"{region} - {area} - {node}"
        lines.append(f"    ({region!r}, {area!r}, {node!r}): {loc_name!r},")
    lines.append("}")
    lines.append("")

    out = Path(__file__).parent / "Events.py"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(all_keys)} events, {len(event_nodes)} locations)")


if __name__ == "__main__":
    main()

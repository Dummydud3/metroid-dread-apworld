#!/usr/bin/env python3
"""
Parse Metroid Dread ``CauseOfDeath`` (and related fields) from Ryujinx logs.

PlayReport ``Room: gameover`` is **not** exposed to Lua / Blackboard. Ryujinx's
``ServicePrepo ProcessPlayReport`` dumps the report JSON, e.g.::

    PlayReport log:
     Room: gameover
     Report:
     {
         "CauseOfDeath": 2,
         "WhichGrab": 0,
         "WhichBoss": 1,
         "MapWhereDeathOccurred": 0,
         ...
     }

Use this for empirical env-vs-combat mapping (see CAUSE_OF_DEATH_MATRIX.md).

CLI::

    python -m cause_of_death
    python tools/parse_cause_of_death.py --latest
    python tools/parse_cause_of_death.py --all
    python tools/parse_cause_of_death.py PATH\\to\\Ryujinx.log
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Fields we care about from gameover PlayReports.
GAMEOVER_KEYS = (
    "CauseOfDeath",
    "WhichGrab",
    "WhichBoss",
    "MapWhereDeathOccurred",
    "GameProgressID",
    "PlayTime",
    "CumulativePlayTime",
    "Mode",
    "SessionID",
    "SaveDataID",
)

_REPORT_JSON_RE = re.compile(
    r"Room:\s*gameover[\x00\s]*\r?\n\s*Report:\s*\r?\n\s*"
    r"(\{[^{}]*\"CauseOfDeath\"[^{}]*\})",
    re.IGNORECASE | re.MULTILINE,
)
# Fallback: any JSON object with CauseOfDeath (some log formats omit Room line nearby).
_CAUSE_OBJECT_RE = re.compile(
    r"(\{[^{}]*\"CauseOfDeath\"\s*:\s*-?\d+[^{}]*\})",
    re.MULTILINE,
)


@dataclass(frozen=True)
class GameOverReport:
    cause_of_death: Optional[int]
    which_grab: Optional[int] = None
    which_boss: Optional[int] = None
    map_where_death_occurred: Optional[int] = None
    game_progress_id: Optional[int] = None
    play_time: Optional[int] = None
    cumulative_play_time: Optional[int] = None
    mode: Optional[int] = None
    session_id: Optional[str] = None
    save_data_id: Optional[str] = None
    source_path: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def summary_line(self) -> str:
        parts = [f"CauseOfDeath={self.cause_of_death}"]
        if self.which_grab is not None:
            parts.append(f"WhichGrab={self.which_grab}")
        if self.which_boss is not None:
            parts.append(f"WhichBoss={self.which_boss}")
        if self.map_where_death_occurred is not None:
            parts.append(f"Map={self.map_where_death_occurred}")
        if self.game_progress_id is not None:
            parts.append(f"GameProgressID={self.game_progress_id}")
        return " ".join(parts)


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def report_from_dict(
    data: Dict[str, Any], *, source_path: Optional[Path] = None
) -> GameOverReport:
    return GameOverReport(
        cause_of_death=_optional_int(data.get("CauseOfDeath")),
        which_grab=_optional_int(data.get("WhichGrab")),
        which_boss=_optional_int(data.get("WhichBoss")),
        map_where_death_occurred=_optional_int(data.get("MapWhereDeathOccurred")),
        game_progress_id=_optional_int(data.get("GameProgressID")),
        play_time=_optional_int(data.get("PlayTime")),
        cumulative_play_time=_optional_int(data.get("CumulativePlayTime")),
        mode=_optional_int(data.get("Mode")),
        session_id=str(data["SessionID"]) if data.get("SessionID") is not None else None,
        save_data_id=(
            str(data["SaveDataID"]) if data.get("SaveDataID") is not None else None
        ),
        source_path=str(source_path) if source_path else None,
        raw=dict(data),
    )


def parse_gameover_reports_from_text(
    text: str, *, source_path: Optional[Path] = None
) -> List[GameOverReport]:
    """Extract all gameover CauseOfDeath reports from a Ryujinx log body."""
    out: List[GameOverReport] = []
    seen_spans: set[Tuple[int, int]] = set()

    def _try_json(blob: str, span: Tuple[int, int]) -> None:
        if span in seen_spans:
            return
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict) or "CauseOfDeath" not in data:
            return
        seen_spans.add(span)
        out.append(report_from_dict(data, source_path=source_path))

    for m in _REPORT_JSON_RE.finditer(text):
        _try_json(m.group(1), m.span(1))
    for m in _CAUSE_OBJECT_RE.finditer(text):
        _try_json(m.group(1), m.span(1))
    return out


def parse_gameover_reports(path: Path) -> List[GameOverReport]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_gameover_reports_from_text(text, source_path=path)


def _home() -> Path:
    return Path.home()


def candidate_log_dirs(
    extra: Optional[Sequence[Path]] = None,
    *,
    ryujinx_exe: Optional[Path] = None,
) -> List[Path]:
    """Ordered unique directories that may contain ``Ryujinx_*.log``."""
    dirs: List[Path] = []

    def add(p: Optional[Path]) -> None:
        if p is None:
            return
        try:
            resolved = p.expanduser().resolve()
        except OSError:
            resolved = p.expanduser()
        if resolved not in dirs:
            dirs.append(resolved)

    env = (os.environ.get("METROID_BREAD_RYUJINX_LOGS") or os.environ.get("RYUJINX_LOGS") or "").strip()
    if env:
        add(Path(env))

    if ryujinx_exe is not None:
        add(ryujinx_exe.expanduser().resolve().parent / "Logs")

    # Hub / client UI config next to this world package (or tools/ sibling).
    here = Path(__file__).resolve()
    world = here.parent if here.name == "cause_of_death.py" else here.parents[1]
    for cfg_name in ("dread_client_ui_config.json", "dread_direct_patch_config.json"):
        cfg_path = world / cfg_name
        if not cfg_path.is_file():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        exe = cfg.get("ryujinx_path") or cfg.get("ryujinx_exe")
        if exe:
            add(Path(str(exe)).expanduser().parent / "Logs")

    add(_home() / "Downloads" / "ryujinx-1.2.78-win_x64" / "publish" / "Logs")
    downloads = _home() / "Downloads"
    if downloads.is_dir():
        try:
            for child in sorted(downloads.glob("ryujinx-*"), reverse=True):
                add(child / "publish" / "Logs")
        except OSError:
            pass
    add(Path(os.path.expandvars(r"%LOCALAPPDATA%\Ryujinx\Logs")))
    add(Path(os.path.expandvars(r"%APPDATA%\Ryujinx\Logs")))

    if extra:
        for p in extra:
            add(p)
    return dirs


def find_ryujinx_log_files(
    log_dirs: Optional[Sequence[Path]] = None,
    *,
    ryujinx_exe: Optional[Path] = None,
) -> List[Path]:
    dirs = list(log_dirs) if log_dirs is not None else candidate_log_dirs(ryujinx_exe=ryujinx_exe)
    files: List[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            files.extend(d.glob("Ryujinx_*.log"))
            files.extend(d.glob("*.log"))
        except OSError:
            continue
    # Unique by resolve, newest first.
    uniq: Dict[Path, Path] = {}
    for f in files:
        try:
            key = f.resolve()
        except OSError:
            key = f
        uniq[key] = f
    return sorted(uniq.values(), key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True)


def latest_log_path(**kwargs: Any) -> Optional[Path]:
    files = find_ryujinx_log_files(**kwargs)
    return files[0] if files else None


def latest_gameover_report(**kwargs: Any) -> Optional[GameOverReport]:
    """Newest CauseOfDeath report across the newest Ryujinx log file."""
    path = latest_log_path(**kwargs)
    if path is None:
        return None
    reports = parse_gameover_reports(path)
    return reports[-1] if reports else None


def all_gameover_reports(**kwargs: Any) -> List[GameOverReport]:
    out: List[GameOverReport] = []
    for path in find_ryujinx_log_files(**kwargs):
        out.extend(parse_gameover_reports(path))
    return out


def format_report_table(reports: Iterable[GameOverReport]) -> str:
    rows = list(reports)
    if not rows:
        return "(no CauseOfDeath / gameover PlayReports found)"
    lines = [
        "CauseOfDeath | WhichGrab | WhichBoss | Map | GameProgressID | source",
        "-------------|---------|---------|-----|----------------|--------",
    ]
    for r in rows:
        src = Path(r.source_path).name if r.source_path else "?"
        lines.append(
            f"{r.cause_of_death!s:>12} | {r.which_grab!s:>7} | {r.which_boss!s:>7} | "
            f"{r.map_where_death_occurred!s:>3} | {r.game_progress_id!s:>14} | {src}"
        )
    return "\n".join(lines)


def format_client_log_line(
    report: Optional[GameOverReport],
    *,
    tag: str = "death",
    lua_probe: str = "",
) -> str:
    """Single line for Metroid Bread client logger."""
    bits = [f"[DEATH_CAUSE] {tag}"]
    if report is None:
        bits.append("PlayReport=missing (die once, wait for ServicePrepo, or check RYUJINX_LOGS)")
    else:
        bits.append(report.summary_line())
        if report.source_path:
            bits.append(f"log={Path(report.source_path).name}")
    if lua_probe:
        bits.append(f"lua={lua_probe}")
    return " ".join(bits)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        help="Specific Ryujinx log file (default: auto-detect)",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Print only the newest gameover CauseOfDeath report",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan all discovered Ryujinx logs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a table",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        help="Extra / override Logs directory",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.path:
        reports = parse_gameover_reports(Path(args.path))
    elif args.all:
        dirs = candidate_log_dirs(extra=[args.logs_dir] if args.logs_dir else None)
        reports = []
        for path in find_ryujinx_log_files(log_dirs=dirs):
            reports.extend(parse_gameover_reports(path))
    else:
        dirs = candidate_log_dirs(extra=[args.logs_dir] if args.logs_dir else None)
        path = latest_log_path(log_dirs=dirs)
        if path is None:
            print("No Ryujinx log found. Set METROID_BREAD_RYUJINX_LOGS or pass a log path.")
            print("Candidates:")
            for d in dirs:
                print(f"  {d}  ({'ok' if d.is_dir() else 'missing'})")
            return 1
        print(f"Log: {path}")
        reports = parse_gameover_reports(path)

    if args.latest:
        reports = reports[-1:] if reports else []

    if args.json:
        print(json.dumps([asdict(r) for r in reports], indent=2))
    else:
        print(format_report_table(reports))
        if reports:
            print()
            print("Latest:", reports[-1].summary_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Metroid Dread Client for Archipelago

Connects to Ryujinx running a patched Metroid Dread (open-dread-rando remote Lua
on TCP port 6969) and synchronizes locations/items with the Archipelago server.

Protocol adapted from Randovania's DreadExecutor / MercuryConnector / DreadRemoteConnector.
See DREAD_TECHNICAL_REFERENCE.md for wire formats.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import platform
import re
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Colocated under worlds/metroid_dread — ensure sibling client modules + AP core import.
# AP_ROOT must win over WORLD_DIR on sys.path (world Options.py shadows AP Options).
# Runtime extracts live at custom_worlds/_metroid_dread_runtime (parents[1] is NOT AP root).
_WORLD_DIR = Path(__file__).resolve().parent

# Script dir is on sys.path when launched as a file; prefer shared resolver.
if str(_WORLD_DIR) not in sys.path:
    sys.path.insert(0, str(_WORLD_DIR))
try:
    import dread_paths as _dread_paths

    _dread_paths.ensure_import_paths()
    _AP_ROOT = _dread_paths.AP_ROOT
except Exception:
    def _resolve_ap_root(world_dir: Path) -> Path:
        for key in ("DREAD_HUB_AP_ROOT", "ARCHIPELAGO_ROOT"):
            raw = (os.environ.get(key) or "").strip()
            if raw:
                candidate = Path(raw).expanduser()
                if (candidate / "CommonClient.py").is_file():
                    return candidate.resolve()
        for parent in (world_dir, *world_dir.parents):
            if (parent / "CommonClient.py").is_file() and parent.name.lower() != "ap_core":
                return parent.resolve()
        bundled = world_dir / "ap_core"
        if (bundled / "CommonClient.py").is_file():
            return bundled.resolve()
        try:
            return world_dir.parents[1].resolve()
        except IndexError:
            return world_dir.resolve()

    _AP_ROOT = _resolve_ap_root(_WORLD_DIR)
    for _p in (_WORLD_DIR, _AP_ROOT):
        _s = str(_p)
        if _s in sys.path:
            sys.path.remove(_s)
    sys.path.insert(0, str(_WORLD_DIR))
    sys.path.insert(0, str(_AP_ROOT))
    _install = (os.environ.get("DREAD_HUB_INSTALL_ROOT") or "").strip()
    if _install:
        try:
            import Utils as _Utils_early

            _Utils_early.local_path.cached_path = str(Path(_install).resolve())
        except Exception:
            pass

from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    handle_url_arg,
    server_loop,
)
from NetUtils import ClientStatus, JSONtoTextParser, NetworkItem, SlotType, status_colors
import Utils

import dread_client_bridge as bridge
import dread_map_icon_labels as map_icon_labels
import dread_paths
import dread_reachable_map as reachable_map
import dread_server_spoiler

logger = logging.getLogger("MetroidDread")

DREAD_PORT = 6969
# Structured status lines for the Electron UI (parsed from stdout).
UI_EVENT_PREFIX = "@@APUI@@"

# Stable, drag-into-chat diagnostic log under Archipelago's logs/ folder
# (usually <Archipelago>/logs/metroid_dread_client.log when the install is writable).
DREAD_DIAG_LOG_FILENAME = "metroid_dread_client.log"
DREAD_DIAG_LOG_MAX_BYTES = 8 * 1024 * 1024  # 8 MB, then rotate
DREAD_DIAG_LOG_BACKUP_COUNT = 2
_dread_diag_log_path: Optional[str] = None
_dread_diag_logging_ready = False


def get_dread_diag_log_path() -> str:
    """Absolute path of the always-on Metroid Dread diagnostic log file."""
    global _dread_diag_log_path
    if _dread_diag_log_path:
        return _dread_diag_log_path
    return Utils.user_path("logs", DREAD_DIAG_LOG_FILENAME)


def write_dread_session_header(
    *,
    dread_ip: str = "127.0.0.1",
    game_connected: bool = False,
    electron_ui: bool = False,
    dread_version: str = "",
    layout_uuid: str = "",
    reason: str = "start",
) -> None:
    """Append a redacted session header (no passwords/tokens) for diagnosis."""
    lines = [
        "",
        "=" * 72,
        f"Metroid Dread client session ({reason})",
        f"timestamp: {datetime.now().isoformat(timespec='seconds')}",
        f"archipelago: {Utils.__version__}",
        f"python: {sys.version.split()[0]} ({platform.python_implementation()})",
        f"os: {platform.platform()}",
        f"frozen: {Utils.is_frozen()}",
        f"dread_endpoint: {dread_ip}:{DREAD_PORT}",
        f"game_connected: {game_connected}",
        f"electron_ui: {electron_ui}",
    ]
    if dread_version:
        lines.append(f"dread_version: {dread_version}")
    if layout_uuid:
        lines.append(f"layout_uuid: {layout_uuid}")
    lines.append(f"diagnostic_log: {get_dread_diag_log_path()}")
    lines.append("=" * 72)
    logger.info("\n".join(lines))


def setup_dread_diagnostic_logging(
    *,
    dread_ip: str = "127.0.0.1",
    electron_ui: bool = False,
) -> str:
    """
    Default-on file logging for Metroid Dread client diagnostics.

    Uses Archipelago's standard init_logging (timestamped session file + console)
    and attaches a stable rotating FileHandler at logs/metroid_dread_client.log.
    """
    global _dread_diag_log_path, _dread_diag_logging_ready

    log_path = get_dread_diag_log_path()
    if not _dread_diag_logging_ready:
        Utils.init_logging("MetroidDreadClient", exception_logger="Client")
        log_path = Utils.user_path("logs", DREAD_DIAG_LOG_FILENAME)
        _dread_diag_log_path = log_path

        handler = RotatingFileHandler(
            log_path,
            maxBytes=DREAD_DIAG_LOG_MAX_BYTES,
            backupCount=DREAD_DIAG_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        # Match Utils.init_logging filters so UI carriage-returns / NoFile records
        # do not pollute the diagnostic file.
        handler.addFilter(lambda record: not getattr(record, "NoFile", False))
        handler.addFilter(lambda record: "\r" not in record.getMessage())
        logging.getLogger().addHandler(handler)
        _dread_diag_logging_ready = True

    write_dread_session_header(
        dread_ip=dread_ip,
        game_connected=False,
        electron_ui=electron_ui,
        reason="start",
    )
    # Intentionally very visible in console + file.
    logger.info("Writing diagnostic log to: %s", log_path)
    return log_path

# Hex colors matching NetUtils.JSONtoTextParser / kvui conventions.
_ELECTRON_COLOR_HEX = dict(JSONtoTextParser.color_codes)


@dataclass
class DreadSocketHolder:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    api_version: int
    buffer_size: int
    request_number: int


# Numeric enums matching open-dread-rando-exlaunch (NOT ASCII '1'..'9').
# Randovania IntEnum(b"1") also becomes int 1 — ord('1')=49 was a connection bug.
class PacketType(IntEnum):
    PACKET_HANDSHAKE = 1
    PACKET_LOG_MESSAGE = 2
    PACKET_REMOTE_LUA_EXEC = 3
    PACKET_KEEP_ALIVE = 4
    PACKET_NEW_INVENTORY = 5
    PACKET_COLLECTED_INDICES = 6
    PACKET_RECEIVED_PICKUPS = 7
    PACKET_GAME_STATE = 8
    PACKET_MALFORMED = 9


class ClientInterests(IntEnum):
    LOGGING = 1
    MULTIWORLD = 2


class DreadLuaException(Exception):
    pass


class MetroidDreadClientCommandProcessor(ClientCommandProcessor):
    def _cmd_dread(self):
        """Show Metroid Dread client status"""
        if self.ctx.game_connected:
            self.output(f"Connected to Metroid Dread at {self.ctx.dread_ip}:{DREAD_PORT}")
            self.output(f"Game version: {self.ctx.version}")
            self.output(f"Layout UUID: {self.ctx.layout_uuid}")
            self.output(
                f"Game pickups confirmed: {self.ctx.received_pickups} / "
                f"{len(self.ctx.items_received)} AP items"
            )
            self.output(f"Inventory index: {self.ctx.inventory_index}")
            self.output(f"In cooldown: {self.ctx.in_cooldown}")
        else:
            self.output("Not connected to Metroid Dread. Use /connect_dread [ip]")
        self.output(f"Diagnostic log: {get_dread_diag_log_path()}")

    def _cmd_dread_log(self):
        """Print the path of the Metroid Dread diagnostic log file"""
        path = get_dread_diag_log_path()
        self.output(f"Diagnostic log: {path}")

    def _cmd_connect_dread(self, ip: str = "127.0.0.1"):
        """Connect to Dread. Usage: /connect_dread [ip]"""
        self.ctx.dread_ip = ip
        self.output(f"Attempting to connect to Metroid Dread at {ip}...")
        asyncio.create_task(self.ctx.connect_to_dread())

    def _cmd_download_patch(self):
        """Ask the Archipelago server for placements and rebuild the patch spoiler."""
        if not self.ctx.server or not self.ctx.slot:
            self.output("Connect to Archipelago first.")
            return
        self.output("Requesting seed placements from the Archipelago server…")
        asyncio.create_task(self.ctx.download_patch_spoiler(force=True))

    def _cmd_lua(self, *code: str):
        """Execute Lua in Dread. Usage: /lua <code>"""
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread")
            return
        lua_code = " ".join(code)
        if not lua_code.strip():
            self.output("Error: No Lua code provided")
            return
        self.output(f"Executing: {lua_code}")
        asyncio.create_task(self._execute_lua(lua_code))

    def _cmd_give(self, *item_name: str):
        """Locally grant an item for testing. Usage: /give <item name>

        Debug-only: applies the item directly in Dread (fuzzy-matched against
        known AP item names) without sending a LocationCheck or advancing the
        multiworld ReceivedItems index. Requires /connect_dread first.
        """
        requested = " ".join(item_name).strip()
        if not requested:
            self.output("Usage: /give <item name> (e.g. /give Morph Ball, /give speed booster)")
            return
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread. Use /connect_dread [ip]")
            return
        self.output(f"Attempting to grant '{requested}' (debug /give)...")
        asyncio.create_task(self.ctx.debug_give_item(requested))

    def _cmd_map_smoke(self, asset_id: str = ""):
        """Smoke-test walk/region paint. Usage: /map_smoke [entity_name] (INGAME)."""
        self._run_map_smoke(asset_id)

    def _cmd_dread_map_smoke(self, asset_id: str = ""):
        """Alias for /map_smoke. Usage: /dread_map_smoke [entity_name] (INGAME)."""
        self._run_map_smoke(asset_id)

    def _cmd_map_smoke_bounds(self, *area_parts: str):
        """Full-room bright smoke via OdrMap.VisitBoundsSafe. Usage: /map_smoke_bounds [Area]."""
        self._run_map_smoke_bounds(" ".join(area_parts).strip())

    def _cmd_map_icon_smoke(self, actor: str = ""):
        """Force a map item icon visible. Usage: /map_icon_smoke [actor] (INGAME)."""
        self._run_map_icon_smoke(actor)

    def _cmd_map_label_smoke(self, *parts: str):
        """Gated map-label probe. Usage: /map_label_smoke force [key] [text...]

        Disabled by default (0.1.5 LoadBank crash). With 'force': soft-fail-only
        SetLocalized when OdrText.IsBankReady — never LoadBank/EnsureBank.
        Durable path: patch-time BTXT.
        """
        if not parts or parts[0].strip().lower() not in ("force", "--force"):
            self.output(
                "Map label smoke DISABLED (0.1.6-passive-bank). "
                "Usage: /map_label_smoke force [key] [text...] "
                "(soft-fail only if bank already loaded; never LoadBank). "
                "Durable path: patch-time BTXT."
            )
            return
        parts = parts[1:]
        key = ""
        text = ""
        if parts:
            key = parts[0].strip()
            text = " ".join(parts[1:]).strip()
        self._run_map_label_smoke(key, text)

    def _cmd_map_sprite_smoke(self, icon: str = "", row: str = "", col: str = ""):
        """Repoint one map icon at an atlas cell. Usage: /map_sprite_smoke [ItemCustom0] [row] [col].

        Defaults to ItemCustom0 → the missile tank cell. Reports the icon-def
        table status first, so a stale subsdk9 shows up as no-SetIconSprite.
        """
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread")
            return
        icon_id = (icon or "ItemCustom0").strip()
        if not all(c.isalnum() or c in "_" for c in icon_id):
            self.output("Error: icon id must be alphanumeric / underscore")
            return
        try:
            r = int(row) if row else map_icon_labels.ICON_SPRITES["item_missiletank"][0]
            c = int(col) if col else map_icon_labels.ICON_SPRITES["item_missiletank"][1]
        except ValueError:
            self.output("Error: row/col must be integers")
            return
        lua = (
            'RL.SendApLog("AP_MAP: sprite-status "..tostring(RL.MapIconSpriteStatus '
            'and RL.MapIconSpriteStatus() or "no-fn")) '
            f'RL.ApplyMapIconSprites({{["{icon_id}"]={{{r},{c}}}}})'
        )
        self.output(f"Map sprite smoke: {icon_id} -> ({r},{c}); watch the AP_MAP log lines.")
        asyncio.create_task(self.ctx.run_lua_code(lua, wait_response=False))

    def _cmd_test_hint_ghavoran(self):
        """Simulate an AP hint on one Ghavoran check (sprite + world-map global).

        Picks the first uncollected Ghavoran location from map_icon_keys, reveals
        its icon (AP logo / item sprite) and sets bIsGlobal so it appears on the
        pause world map. Re-run after collect to confirm the global clears.
        """
        self.ctx._run_test_hint_ghavoran(self.output)

    def _cmd_map_hint_test(self):
        """Alias for /test_hint_ghavoran."""
        self._cmd_test_hint_ghavoran()

    def _default_map_icon_smoke_actor(self) -> str:
        """Known Artaria pickup actor from dread_pickup_actors.json (Charge Tutorial ET)."""
        actors = bridge.load_pickup_actors()
        entry = actors.get("3") or {}
        name = entry.get("actor") if isinstance(entry, dict) else None
        return name or "Item_EnergyTank001"

    def _run_map_smoke(self, asset_id: str = ""):
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread")
            return
        aid = (asset_id or "").strip()
        if aid and not all(c.isalnum() or c in "_-" for c in aid):
            self.output("Error: entity name must be alphanumeric / underscore / hyphen")
            return
        # Re-inject MapPaintSmoke so diagnostics work without a full reconnect.
        # Default: cut_fillmap_54 (Corpius Arena fillmap actor). collision_camera_* no-ops.
        default_id = "cut_fillmap_54"
        target = aid or default_id
        lua = (
            "if not RL then RL = {} end\n"
            "if not RL.ProbeVisitedCells then\n"
            "  function RL.ProbeVisitedCells(scenario)\n"
            "    if not scenario or not minimap or not minimap.GetNumVisitedCells then return nil end\n"
            "    local ok, n = pcall(function() return minimap.GetNumVisitedCells(scenario) end)\n"
            "    if ok then return n end\n"
            "    return nil\n"
            "  end\n"
            "end\n"
            "function RL.MapPaintSmoke(assetId)\n"
            "  local id = assetId\n"
            "  if id == nil or id == '' then id = 'cut_fillmap_54' end\n"
            "  local mode, scen = '?', '?'\n"
            "  pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)\n"
            "  pcall(function() scen = tostring(Game.GetScenarioID()) end)\n"
            "  if not Game.SetMinimapRegionVisited then\n"
            "    RL.SendApLog('AP_MAP: region-visit smoke FAIL no-api id='..tostring(id)..' mode='..mode..' scen='..scen)\n"
            "    return 'no-api'\n"
            "  end\n"
            "  local before = RL.ProbeVisitedCells(scen)\n"
            "  local actor_found = '?'\n"
            "  pcall(function()\n"
            "    if Game.GetActor then\n"
            "      local a = Game.GetActor(id)\n"
            "      actor_found = (a ~= nil) and 'yes' or 'no'\n"
            "    else\n"
            "      actor_found = 'no-GetActor'\n"
            "    end\n"
            "  end)\n"
            "  local ret = nil\n"
            "  local ok, err = pcall(function() ret = Game.SetMinimapRegionVisited(id) end)\n"
            "  local after = RL.ProbeVisitedCells(scen)\n"
            "  pcall(function() if minimap and minimap.SetProfileDataDirty then minimap.SetProfileDataDirty() end end)\n"
            "  local delta = '?'\n"
            "  if before ~= nil and after ~= nil then delta = tostring(after - before) end\n"
            "  if not ok then\n"
            "    RL.SendApLog('AP_MAP: region-visit smoke FAIL id='..tostring(id)..' mode='..mode..' scen='..scen..' err='..tostring(err)..' visited='..tostring(before)..'->'..tostring(after)..' actor='..actor_found)\n"
            "    return 'fail'\n"
            "  end\n"
            "  local verdict = 'ok'\n"
            "  if before ~= nil and after ~= nil and after == before then verdict = 'noop' end\n"
            "  RL.SendApLog('AP_MAP: region-visit smoke '..verdict..' id='..tostring(id)..' mode='..mode..' scen='..scen..' ret='..tostring(ret)..' visited='..tostring(before)..'->'..tostring(after)..' d='..delta..' actor='..actor_found)\n"
            "  return verdict\n"
            "end\n"
            f'RL.MapPaintSmoke("{target}")\n'
        )
        label = "cut_fillmap_54 / Corpius Arena" if not aid else target
        self.output(
            f"Map smoke: SetMinimapRegionVisited({target!r}) ({label}; "
            "logs visited before/after)"
        )
        asyncio.create_task(self._execute_map_smoke(lua))

    def _run_map_smoke_bounds(self, area_spec: str = ""):
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread")
            return
        # Default: Artaria Freezer — full camera AABB, no fillmap actor (proves full-room path).
        # Alt: "Corpius Arena" (has tiny fillmap; this paints the whole camera box).
        area = (area_spec or "Freezer").strip()
        if not area or any(c in area for c in "\\\"';"):
            self.output("Error: area name looks unsafe")
            return
        # Hardcoded Freezer fallback if MapAreaBounds not in romfs yet.
        # Corpius Arena = {17800,-550,21900,800}; Freezer = {-19200,-6400,-17100,-2200}
        lua = (
            "if not RL then RL = {} end\n"
            "if not RL.ProbeVisitedCells then\n"
            "  function RL.ProbeVisitedCells(scenario)\n"
            "    if not scenario or not minimap or not minimap.GetNumVisitedCells then return nil end\n"
            "    local ok, n = pcall(function() return minimap.GetNumVisitedCells(scenario) end)\n"
            "    if ok then return n end\n"
            "    return nil\n"
            "  end\n"
            "end\n"
            "function RL.MapPaintBoundsSmoke(areaName)\n"
            "  local area = areaName\n"
            "  if area == nil or area == '' then area = 'Freezer' end\n"
            "  local mode, scen = '?', '?'\n"
            "  pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)\n"
            "  pcall(function() scen = tostring(Game.GetScenarioID()) end)\n"
            "  if mode ~= 'INGAME' then\n"
            "    RL.SendApLog('AP_MAP: bounds-smoke SKIP not-INGAME mode='..mode..' area='..tostring(area))\n"
            "    return 'not-ingame'\n"
            "  end\n"
            "  if not RL.MapAreaBounds then\n"
            "    pcall(function() Game.DoFile('system/scripts/ap_reachable_map_cells.lua') end)\n"
            "  end\n"
            "  local b = nil\n"
            "  if RL.MapAreaBounds and RL.MapAreaBounds[scen] then\n"
            "    b = RL.MapAreaBounds[scen][area]\n"
            "  end\n"
            "  if not b and area == 'Freezer' then\n"
            "    b = {-19200.0, -6400.0, -17100.0, -2200.0}\n"
            "  elseif not b and area == 'Corpius Arena' then\n"
            "    b = {17800.0, -550.0, 21900.0, 800.0}\n"
            "  end\n"
            "  if not b then\n"
            "    RL.SendApLog('AP_MAP: bounds-smoke FAIL no-bounds area='..tostring(area)..' scen='..scen)\n"
            "    return 'no-bounds'\n"
            "  end\n"
            "  local x1,y1,x2,y2 = b[1],b[2],b[3],b[4]\n"
            "  local ver = tostring(OdrMap and OdrMap.Version)\n"
            "  if not OdrMap or not OdrMap.VisitBoundsSafe then\n"
            "    RL.SendApLog('AP_MAP: bounds-smoke FAIL no-VisitBoundsSafe area='..tostring(area)..' ver='..ver\n"
            "      ..' — need subsdk9 0.4.1-stackvt; try /map_smoke (fillmap cutout)')\n"
            "    return 'no-api'\n"
            "  end\n"
            "  local status_before, status_after = '?', '?'\n"
            "  pcall(function() if OdrMap.VisitBoundsSafeStatus then status_before = tostring(OdrMap.VisitBoundsSafeStatus()) end end)\n"
            "  local before = RL.ProbeVisitedCells(scen)\n"
            "  local ret, reason = nil, nil\n"
            "  local ok, err = pcall(function()\n"
            "    ret, reason = OdrMap.VisitBoundsSafe(scen, x1, y1, x2, y2)\n"
            "  end)\n"
            "  pcall(function() if OdrMap.VisitBoundsSafeStatus then status_after = tostring(OdrMap.VisitBoundsSafeStatus()) end end)\n"
            "  local after = RL.ProbeVisitedCells(scen)\n"
            "  pcall(function() if minimap and minimap.SetProfileDataDirty then minimap.SetProfileDataDirty() end end)\n"
            "  local delta = '?'\n"
            "  if before ~= nil and after ~= nil then delta = tostring(after - before) end\n"
            "  if not ok then\n"
            "    RL.SendApLog('AP_MAP: bounds-smoke FAIL area='..tostring(area)..' err='..tostring(err)\n"
            "      ..' status_before='..status_before..' status_after='..status_after..' ver='..ver\n"
            "      ..' — native error; reopen pause map / retry INGAME')\n"
            "    return 'fail'\n"
            "  end\n"
            "  local verdict = 'ok'\n"
            "  if ret == false or ret == nil then verdict = 'soft-fail' end\n"
            "  if verdict == 'ok' and before ~= nil and after ~= nil and after == before then verdict = 'noop' end\n"
            "  RL.SendApLog('AP_MAP: bounds-smoke '..verdict..' area='..tostring(area)..' scen='..scen\n"
            "    ..' aabb=('..tostring(x1)..','..tostring(y1)..')-('..tostring(x2)..','..tostring(y2)..')'\n"
            "    ..' ret='..tostring(ret)..' reason='..tostring(reason)\n"
            "    ..' visited='..tostring(before)..'->'..tostring(after)..' d='..delta\n"
            "    ..' status_before='..status_before..' status_after='..status_after..' ver='..ver)\n"
            "  if verdict == 'soft-fail' then\n"
            "    RL.SendApLog('AP_MAP: bounds-smoke tip — soft-fail is NOT latched; check stackvt=1 in status.'\n"
            "      ..' Retry INGAME or /map_smoke (fillmap cutout)')\n"
            "  end\n"
            "  return verdict\n"
            "end\n"
            f'RL.MapPaintBoundsSmoke("{area}")\n'
        )
        self.output(
            f"Map bounds smoke: VisitBoundsSafe({area!r}) "
            "(full camera AABB → stackvt → 0xe3ad38 flag=4 dim; INGAME only)"
        )
        asyncio.create_task(self._execute_map_smoke_bounds(lua))

    def _run_map_icon_smoke(self, actor: str = ""):
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread")
            return
        aid = (actor or "").strip() or self._default_map_icon_smoke_actor()
        if not all(c.isalnum() or c in "_-" for c in aid):
            self.output("Error: actor name must be alphanumeric / underscore / hyphen")
            return
        # Re-inject MapIconSmoke so diagnostics work without a full reconnect.
        # Does NOT touch VisitBoundsSafe / MapNativePaintEnabled / bright paint.
        lua = (
            "if not RL then RL = {} end\n"
            "function RL.MapIconSmoke(actorName)\n"
            "  local id = actorName\n"
            "  if id == nil or id == '' then id = 'Item_EnergyTank001' end\n"
            "  local mode, scen = '?', '?'\n"
            "  pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)\n"
            "  pcall(function() scen = tostring(Game.GetScenarioID()) end)\n"
            "  if not Game.ForceEntityIconVisible then\n"
            "    RL.SendApLog('AP_MAP: icon-smoke FAIL no-api actor='..tostring(id)..' mode='..mode..' scen='..scen)\n"
            "    return 'no-api'\n"
            "  end\n"
            "  local actor_found = '?'\n"
            "  pcall(function()\n"
            "    if Game.GetActor then\n"
            "      local a = Game.GetActor(id)\n"
            "      actor_found = (a ~= nil) and 'yes' or 'no'\n"
            "    else\n"
            "      actor_found = 'no-GetActor'\n"
            "    end\n"
            "  end)\n"
            "  local ret = nil\n"
            "  local ok, err = pcall(function() ret = Game.ForceEntityIconVisible(id) end)\n"
            "  if not ok then\n"
            "    RL.SendApLog('AP_MAP: icon-smoke FAIL actor='..tostring(id)..' mode='..mode..' scen='..scen..' err='..tostring(err)..' found='..actor_found)\n"
            "    return 'fail'\n"
            "  end\n"
            "  RL.SendApLog('AP_MAP: icon-smoke ok actor='..tostring(id)..' mode='..mode..' scen='..scen..' ret='..tostring(ret)..' found='..actor_found)\n"
            "  return 'ok'\n"
            "end\n"
            f'RL.MapIconSmoke("{aid}")\n'
        )
        self.output(
            f"Map icon smoke: ForceEntityIconVisible({aid!r}) "
            "(watch AP_MAP: icon-smoke …; INGAME, Artaria for default)"
        )
        asyncio.create_task(self._execute_map_icon_smoke(lua))

    def _run_map_label_smoke(self, key: str = "", text: str = ""):
        if not self.ctx.game_connected:
            self.output("Error: Not connected to Metroid Dread")
            return
        k = (key or "").strip()
        t = (text or "").strip() or "Label Smoke OK"
        if k.startswith("#"):
            k = k[1:]
        if k and not all(c.isalnum() or c in "_-" for c in k):
            self.output("Error: key must be alphanumeric / underscore / hyphen (optional # prefix)")
            return
        if any(c in t for c in ('"', "\\", "\n", "\r")):
            self.output("Error: text must not contain quotes, backslashes, or newlines")
            return
        # Re-inject MapLabelSmoke so diagnostics work without a full reconnect.
        # Does NOT touch VisitBoundsSafe / MapNativePaintEnabled / bright paint.
        key_lua = k.replace("'", "")
        text_lua = t.replace("'", "")
        lua = (
            "if not RL then RL = {} end\n"
            "function RL.MapLabelSmoke(key, text)\n"
            "  local k = key\n"
            "  local t = text\n"
            "  if t == nil or t == '' then t = 'Label Smoke OK' end\n"
            "  local mode, scen = '?', '?'\n"
            "  pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)\n"
            "  pcall(function() scen = tostring(Game.GetScenarioID()) end)\n"
            "  if not OdrText or not OdrText.SetLocalized then\n"
            "    RL.SendApLog('AP_MAP: label-smoke FAIL no-OdrText mode='..mode..' scen='..scen)\n"
            "    return 'no-api'\n"
            "  end\n"
            "  -- Passive only (0.1.6): never WarmBank/LoadBank/EnsureBank.\n"
            "  if not OdrText.IsBankReady then\n"
            "    RL.SendApLog('AP_MAP: label-smoke soft-fail reason=no-IsBankReady mode='..mode..' scen='..scen)\n"
            "    return 'soft-fail'\n"
            "  end\n"
            "  local okb, ready = pcall(OdrText.IsBankReady)\n"
            "  if not okb or ready == false then\n"
            "    RL.SendApLog('AP_MAP: label-smoke soft-fail reason=bank-not-ready mode='..mode..' scen='..scen)\n"
            "    return 'soft-fail'\n"
            "  end\n"
            "  if k == nil or k == '' then\n"
            "    k = 'MAP_ICON_ItemCustom0'\n"
            "    if OdrText.HasLocalized then\n"
            "      for i = 0, 200 do\n"
            "        local cand = 'MAP_ICON_ItemCustom'..tostring(i)\n"
            "        local ok, has = pcall(OdrText.HasLocalized, cand)\n"
            "        if ok and has then k = cand break end\n"
            "      end\n"
            "    end\n"
            "  end\n"
            "  local ok, ret, reason = pcall(function() return OdrText.SetLocalized(k, t) end)\n"
            "  if not ok then\n"
            "    RL.SendApLog('AP_MAP: label-smoke FAIL key='..tostring(k)..' mode='..mode..' scen='..scen..' err='..tostring(ret))\n"
            "    return 'fail'\n"
            "  end\n"
            "  if ret == true then\n"
            "    local got = '?'\n"
            "    pcall(function() if OdrText.GetLocalized then got = tostring(OdrText.GetLocalized(k)) end end)\n"
            "    RL.SendApLog('AP_MAP: label-smoke ok key='..tostring(k)..' text='..tostring(t)..' got='..got..' mode='..mode..' scen='..scen)\n"
            "    return 'ok'\n"
            "  end\n"
            "  RL.SendApLog('AP_MAP: label-smoke soft-fail key='..tostring(k)..' reason='..tostring(reason)..' mode='..mode..' scen='..scen)\n"
            "  return 'soft-fail'\n"
            "end\n"
            f"RL.MapLabelSmoke('{key_lua}', '{text_lua}')\n"
        )
        shown_key = k or "(auto MAP_ICON_ItemCustom*)"
        self.output(
            f"Map label smoke: OdrText.SetLocalized({shown_key!r}, {t!r}) "
            "(watch AP_MAP: label-smoke …; inspect map icon; INGAME)"
        )
        asyncio.create_task(self._execute_map_label_smoke(lua))

    async def _execute_lua(self, code: str):
        try:
            await self.ctx.run_lua_code(code)
            self.output("Lua sent (response handled by read loop)")
        except Exception as e:
            self.output(f"Error: {e}")

    async def _execute_map_smoke(self, code: str):
        try:
            await self.ctx.run_lua_code(code, wait_response=False)
            self.output("Map smoke Lua sent — watch AP_MAP: region-visit smoke …")
        except Exception as e:
            self.output(f"Error: {e}")

    async def _execute_map_smoke_bounds(self, code: str):
        try:
            await self.ctx.run_lua_code(code, wait_response=False)
            self.output("Bounds smoke Lua sent — watch AP_MAP: bounds-smoke …")
        except Exception as e:
            self.output(f"Error: {e}")

    async def _execute_map_icon_smoke(self, code: str):
        try:
            await self.ctx.run_lua_code(code, wait_response=False)
            self.output("Map icon smoke Lua sent — watch AP_MAP: icon-smoke …")
        except Exception as e:
            self.output(f"Error: {e}")

    async def _execute_map_label_smoke(self, code: str):
        try:
            await self.ctx.run_lua_code(code, wait_response=False)
            self.output("Map label smoke Lua sent — watch AP_MAP: label-smoke …")
        except Exception as e:
            self.output(f"Error: {e}")

    def _cmd_deathlink(self, *args: str):
        """DeathLink control. Usage: /deathlink [status|on|off|test]"""
        ctx = self.ctx
        sub = args[0].lower() if args else "status"
        if sub in ("status", ""):
            state = "enabled" if ctx.deathlink_enabled else "disabled"
            tag = "yes" if "DeathLink" in ctx.tags else "no"
            self.output(f"DeathLink is {state} (server tag: {tag})")
            self.output(ctx.death_counter_status())
        elif sub == "on":
            ctx.deathlink_client_override = True
            ctx.deathlink_enabled = True
            asyncio.create_task(ctx.update_death_link(True))
            self.output("DeathLink enabled.")
        elif sub == "off":
            ctx.deathlink_client_override = True
            ctx.deathlink_enabled = False
            asyncio.create_task(ctx.update_death_link(False))
            self.output("DeathLink disabled.")
        elif sub == "test":
            if not ctx.game_connected:
                self.output("Error: Not connected to Metroid Dread")
                return
            self.output("Triggering test DeathLink kill...")
            asyncio.create_task(ctx.trigger_deathlink_kill("Test"))
        elif sub == "probe":
            if not ctx.game_connected:
                self.output("Error: Not connected to Metroid Dread")
                return
            asyncio.create_task(self._probe_death(ctx))
        elif sub == "deaths":
            self.output(ctx.death_counter_status())
        else:
            self.output("Usage: /deathlink [status|on|off|test|probe|deaths]")

    async def _probe_death(self, ctx: "MetroidDreadContext"):
        try:
            status = await ctx.query_death_status()
            if status is None:
                self.output("Death probe failed (no Lua response)")
                return
            self.output(f"Death poll: {status}")
            if ctx.deathlink_enabled:
                await ctx.process_death_poll_status(status, source="probe")
            else:
                self.output("DeathLink disabled — enable with /deathlink on to send on death")
        except Exception as e:
            self.output(f"Death probe error: {e}")


class MetroidDreadContext(CommonContext):
    command_processor = MetroidDreadClientCommandProcessor
    game = "Metroid Dread"
    items_handling = 0b111  # full remote items

    def __init__(self, server_address: Optional[str], password: Optional[str]):
        super().__init__(server_address, password)

        self.dread_ip = "127.0.0.1"
        self._socket: Optional[DreadSocketHolder] = None
        self._connection_lock = asyncio.Lock()
        self._run_code_lock = asyncio.Lock()
        self.game_connected = False
        self.layout_uuid = ""
        self.version = ""

        # Mercury-style sync state (from game push packets)
        self.inventory_index: Optional[int] = None
        self.received_pickups: Optional[int] = None
        self.in_cooldown = True
        self.current_scenario: Optional[str] = None
        # MAINMENU | INGAME | TRANSITION | UNKNOWN — from GAME_STATE / Lua polls.
        self._game_mode: str = "UNKNOWN"
        # Hold item grants across menu↔ingame / scenario loads.
        self._transition_until: float = 0.0
        self.game_reported_locations: Set[int] = set()
        # Wait for first PACKET_COLLECTED_INDICES before granting so reconnect
        # does not re-apply local in-world items before game_reported_locations
        # is populated.
        self._collected_indices_synced = False

        self.item_id_to_name: Dict[int, str] = dict(bridge.ap_item_id_to_name())

        self.deathlink_enabled = False
        self.deathlink_client_override = False
        self.deathlink_sent_this_death = False
        # True after we send or receive a DeathLink; cleared only on respawn log.
        self._deathlink_block_until_respawn = False
        self._deathlink_lock = asyncio.Lock()
        # Once a death gen/count is handled, never send again for that same death.
        self._deathlink_handled_generation = 0
        self._deathlink_handled_deaths = 0
        self._death_poll_generation = 0
        self._death_poll_death_count = 0
        # Client-side death counters (HUD total is separate via ODR enable_death_counter).
        self.deaths_total = 0
        self.deaths_self = 0
        self.deaths_deathlink = 0
        self._death_episode_from_remote = False
        self.electron_ui = False
        self._ui_status_task: Optional[asyncio.Task] = None
        # Lazy RDV logic bridge for in-logic tracker highlighting.
        self._tracker_logic = None
        self._tracker_logic_error: Optional[str] = None
        self._in_logic_cache_key: Optional[tuple] = None
        self._in_logic_location_ids: List[int] = []
        self._tracker_log_sig: Optional[tuple] = None
        self._tracker_ui_refresh_task: Optional[asyncio.Task] = None
        self._tracker_ui_debounce_s = 0.75
        self._slot_starting_location: Optional[dict] = None
        self._slot_required_dna: int = 0
        self._slot_game_goal: int = 0  # legacy; unused after required_dna
        self._slot_data: Dict[str, Any] = {}
        self._patch_extras: Dict[str, Any] = {}
        self._slot_logic_options: Dict[str, int] = {}
        self._logic_options_source: Optional[str] = None
        self._server_spoiler_path: Optional[str] = None
        self._server_spoiler_task: Optional[asyncio.Task] = None
        self._awaiting_patch_scouts: bool = False
        # Latest inventory quantities from PACKET_NEW_INVENTORY (game truth).
        self._game_inventory_amounts: List[int] = []
        # Reachable minimap: AP logic areas → RL.ApplyReachableMap (dim VisitBoundsSafe)
        self.reachable_minimap_enabled = True
        self._reachable_areas_sig: Optional[tuple] = None
        self._reachable_map_task: Optional[asyncio.Task] = None
        self._reachable_map_debounce_s = 1.0
        self._reachable_map_force_pending = False
        # Map-icon labels: patch-time BTXT variants + OdrMap.SetIconInspectorLabel redirect.
        # No LoadBank/EnsureBank. Requires re-patch with text_patches (4 keys per icon).
        self.map_icon_labels_enabled = True
        self._map_icon_keys: Optional[dict] = None
        self._map_icon_keys_source: Optional[str] = None
        self._map_icon_labels: Dict[str, str] = {}
        self._map_icon_labels_sig: Optional[tuple] = None
        self._map_icon_labels_task: Optional[asyncio.Task] = None
        self._map_icon_labels_debounce_s = 0.35
        self._map_icon_labels_force_pending = False
        # OdrText.SetLocalized soft-fails (reason=bank-not-ready) until the game
        # itself has populated its CLanguageManager BTXT dictionary. Neither the
        # Lua-side backoff retry nor this push's own sig-cache reliably keep
        # re-checking that on their own, so a dedicated watcher polls the
        # passive OdrText.IsBankReady flag (via RL.MapIconBankStatus — never
        # forces LoadBank/EnsureBank) and force-repushes the instant it flips
        # ready. Requires OdrText >= 0.1.11; before that the native readiness
        # probe could never return true. See _map_icon_bank_watch_loop.
        self._map_icon_bank_watch_task: Optional[asyncio.Task] = None
        self._map_icon_bank_ready = False
        # Icon graphics (OdrMap.SetIconSprite). Independent of the language bank:
        # this writes uSpriteRow/uSpriteCol in the parsed minimap.bmmdef, so it
        # works even while labels are still soft-failing on bank-not-ready. Kept
        # on its own signature because sprites only change on reveal, while
        # labels also flip on every in-logic recompute.
        self._map_icon_sprites: Dict[str, Tuple[int, int]] = {}
        self._map_icon_sprites_sig: Optional[tuple] = None
        # Hinted (not yet checked) → bIsGlobal so the icon shows on the world map.
        self._map_icon_globals: Dict[str, bool] = {}
        self._map_icon_globals_sig: Optional[tuple] = None
        # Local test-hint overrides (location_id ints) for /test_hint_ghavoran.
        self._test_hint_location_ids: set = set()

        self._lua_response_future: Optional[asyncio.Future] = None
        self.death_poll_task: Optional[asyncio.Task] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        self.read_task: Optional[asyncio.Task] = None

    def emit_ui(self, event_type: str, **payload) -> None:
        """Emit a single-line JSON event for the Electron client UI."""
        if not self.electron_ui:
            return
        try:
            msg = {"type": event_type, **payload}
            print(UI_EVENT_PREFIX + json.dumps(msg, default=str), flush=True)
        except Exception:
            pass

    def _electron_json_parts(self, data: list) -> List[dict]:
        """Resolve PrintJSON parts into {text, color} segments for Electron."""
        out: List[dict] = []
        for raw in data:
            node = dict(raw)
            ntype = node.get("type")

            if ntype == "player_id":
                player = int(node["text"])
                node["text"] = self.player_names.get(player, f"Player {player}")
                node["color"] = "magenta" if self.slot_concerns_self(player) else "yellow"
            elif ntype == "player_name":
                node["color"] = "yellow"
            elif ntype == "item_id":
                item_id = int(node["text"])
                node["text"] = self.item_names.lookup_in_slot(item_id, node.get("player", 0))
                ntype = "item_name"
            elif ntype == "location_id":
                location_id = int(node["text"])
                node["text"] = self.location_names.lookup_in_slot(
                    location_id, node.get("player", 0)
                )
                ntype = "location_name"

            if ntype == "item_name":
                flags = node.get("flags", 0) or 0
                if flags & 0b001:
                    node["color"] = "plum"
                elif flags & 0b010:
                    node["color"] = "slateblue"
                elif flags & 0b100:
                    node["color"] = "salmon"
                else:
                    node["color"] = "cyan"
            elif ntype == "location_name":
                node["color"] = "green"
            elif ntype == "entrance_name":
                node["color"] = "blue"
            elif ntype == "hint_status":
                node["color"] = status_colors.get(node.get("hint_status"), "red")

            text = str(node.get("text", ""))
            color = None
            if node.get("color"):
                color_name = str(node["color"]).split(";")[0]
                color = _ELECTRON_COLOR_HEX.get(color_name)
            out.append({"text": text, "color": color})
        return out

    def on_print_json(self, args: dict) -> None:
        """Forward colored PrintJSON to Electron; keep kvui/CLI path unchanged."""
        if self.electron_ui:
            data = args.get("data") or []
            logging.getLogger("FileLog").info(
                self.rawjsontotextparser(copy.deepcopy(data)),
                extra={"NoStream": True},
            )
            try:
                self.emit_ui(
                    "print_json",
                    parts=self._electron_json_parts(copy.deepcopy(data)),
                    message_type=args.get("type"),
                )
            except Exception:
                # Fallback so chat is never silently dropped.
                print(self.rawjsontotextparser(copy.deepcopy(data)), flush=True)
            return
        super().on_print_json(args)

    def _tracker_received_items(self) -> List[dict]:
        """Item list for the Electron tracker window (id + display name)."""
        names = self.item_id_to_name or bridge.ap_item_id_to_name()
        out: List[dict] = []
        for ni in getattr(self, "items_received", []) or []:
            try:
                item_id = int(ni.item)
            except Exception:
                continue
            name = names.get(item_id) or getattr(ni, "item_name", None) or str(item_id)
            out.append({"id": item_id, "name": name})
        return out

    def _tracker_checked_location_ids(self) -> List[int]:
        checked = getattr(self, "checked_locations", None) or set()
        try:
            return sorted(int(x) for x in checked)
        except Exception:
            return []

    def _apply_slot_start_to_logic(self, logic) -> None:
        """Set seed start if it exists in the graph; otherwise keep parser default."""
        start = self._slot_starting_location
        if not isinstance(start, dict):
            return
        region = start.get("region")
        area = start.get("area")
        node = start.get("node")
        if not (region and area and node):
            return
        candidate = (str(region), str(area), str(node))
        if candidate in getattr(logic, "_adj", {}):
            logic.set_starting_node(candidate)
            return
        # Fall back to a known valid start in the same region if possible.
        for s in logic.parser.get_starting_nodes():
            if s[0] == candidate[0] and s in logic._adj:
                logic.set_starting_node(s)
                logger.warning(
                    "Start %s not in graph; using %s", candidate, s
                )
                return
        logger.warning(
            "Start %s not in graph; keeping default %s",
            candidate,
            logic.starting_node,
        )

    def _apply_slot_rando_to_logic(self, logic) -> None:
        """
        Mutate tracker logic to match shuffled doors/transports from the seed.

        Without this, DreadLogic loads the vanilla graph and the Hub tracker /
        reachable minimap disagree with the patched game (classic symptom: only
        the local vanilla-connected region looks in-logic).
        """
        extras = self._patch_extras if isinstance(self._patch_extras, dict) else {}
        if not extras:
            slot = self._slot_data if isinstance(self._slot_data, dict) else {}
            nested = slot.get("patch_extras")
            extras = nested if isinstance(nested, dict) else slot

        transport_n = 0
        door_n = 0
        elev_n = 0
        try:
            from worlds.metroid_dread import DoorRando, TransportRando

            matching = extras.get("transport_matching") if isinstance(extras, dict) else None
            if isinstance(matching, dict) and matching:
                transport_n = TransportRando.apply_matching_from_slot_data(
                    logic.parser, matching
                )
            elif isinstance(extras, dict) and extras.get("elevators"):
                # Older seeds / synthetic spoilers ship ODR elevators but not
                # transport_matching. Must still run even when door_patches exist
                # (previously skipped by an elif after door apply).
                elev_n = self._apply_elevators_fallback_to_logic(
                    logic, extras["elevators"]
                )

            door_entries = None
            if isinstance(extras, dict):
                door_entries = extras.get("door_assignments") or extras.get(
                    "door_patches"
                )
            if door_entries:
                door_n = DoorRando.apply_assignments_from_slot_data(
                    logic.parser, door_entries
                )

            if transport_n or elev_n or door_n:
                logic.rebuild_graph()
                logger.info(
                    "Tracker logic applied seed rando: "
                    "transport_matching=%s elevators=%s doors=%s",
                    transport_n,
                    elev_n,
                    door_n,
                )
                if self.electron_ui:
                    print(
                        f"[tracker-logic] applied rando "
                        f"transports={transport_n} elevators={elev_n} "
                        f"doors={door_n}",
                        flush=True,
                    )
        except Exception as exc:
            logger.warning("Tracker logic rando apply failed: %s", exc)
            if self.electron_ui:
                print(f"[tracker-logic] rando apply ERROR {exc}", flush=True)

    def _apply_elevators_fallback_to_logic(self, logic, elevators) -> int:
        """Map ODR elevator patches onto dock default_connection (legacy seeds)."""
        if not isinstance(elevators, list):
            return 0
        from worlds.metroid_dread import TransportRando

        transports = TransportRando.collect_transports(logic.parser)
        by_teleporter = {}
        by_arrival = {}
        for meta in transports.values():
            by_teleporter[(meta["scenario"], meta["actor"])] = meta
            by_arrival[
                (meta["scenario"], meta.get("arrival_spawn") or meta["actor"])
            ] = meta
            by_arrival[(meta["scenario"], meta["actor"])] = meta

        applied = 0
        for entry in elevators:
            if not isinstance(entry, dict):
                continue
            tele = entry.get("teleporter") or {}
            dest = entry.get("destination") or {}
            src = by_teleporter.get((tele.get("scenario"), tele.get("actor")))
            if not src:
                continue
            dest_meta = by_arrival.get((dest.get("scenario"), dest.get("actor")))
            if not dest_meta:
                continue
            dr, da, dn = dest_meta["node_id"]
            src["node"]["default_connection"] = {
                "region": dr,
                "area": da,
                "node": dn,
            }
            applied += 1
        return applied

    def _logic_options_spoiler_roots(self) -> List[Path]:
        """output/ directories to scan (packaged client + nearby generate tree)."""
        roots: List[Path] = []
        try:
            roots.append(Path(Utils.user_path("output")))
        except Exception:
            roots.append(Path("output"))
        here = Path(__file__).resolve().parent
        roots.append(here / "output")
        # DreadClient_fresh lives under build/dread_dist/; full generate spoilers
        # often sit on the Archipelago-main/output sibling a few parents up.
        for parent in here.parents:
            roots.append(parent / "output")
            if (parent / "worlds" / "metroid_dread").is_dir():
                break
        # De-dupe while preserving order.
        out: List[Path] = []
        seen: Set[str] = set()
        for root in roots:
            try:
                key = str(root.resolve())
            except Exception:
                key = str(root)
            if key in seen:
                continue
            seen.add(key)
            out.append(root)
        return out

    def _logic_options_from_local_spoilers(self) -> Dict[str, int]:
        """Fallback for older seeds that never shipped logic_options in slot_data."""
        try:
            from worlds.metroid_dread.logic_options import (
                parse_logic_options_from_spoiler_text,
            )
        except Exception:
            return {}

        seed = str(getattr(self, "seed_name", None) or "").strip()
        candidates: List[Path] = []
        if self._server_spoiler_path:
            candidates.append(Path(self._server_spoiler_path))
        for out_root in self._logic_options_spoiler_roots():
            if seed:
                candidates.extend(
                    [
                        out_root / f"AP_{seed}" / f"AP_{seed}_Spoiler.txt",
                        out_root
                        / "_patcher_extract"
                        / f"server_{seed}"
                        / f"AP_{seed}_Spoiler.txt",
                    ]
                )
                ap_dir = out_root / f"AP_{seed}"
                if ap_dir.is_dir():
                    candidates.extend(sorted(ap_dir.glob("*_Spoiler.txt")))
                extract = out_root / "_patcher_extract" / f"server_{seed}"
                if extract.is_dir():
                    candidates.extend(sorted(extract.glob("*_Spoiler.txt")))
        # Prefer fuller spoilers (with trick headers) over synthetic server ones.
        seen: Set[str] = set()
        best: Dict[str, int] = {}
        for path in candidates:
            try:
                key = str(path.resolve())
            except Exception:
                key = str(path)
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            parsed = parse_logic_options_from_spoiler_text(text)
            if len(parsed) > len(best):
                best = parsed
        return best

    def _resolve_logic_options(self) -> Dict[str, int]:
        """
        Seed trick/ammo preset for tracker DreadLogic.

        Priority: slot_data.logic_options → patch_extras.logic_options →
        top-level slot ammo keys → local full spoiler header (legacy seeds).
        """
        try:
            from worlds.metroid_dread.logic_options import (
                coerce_logic_options,
                merge_logic_option_sources,
            )
        except Exception as exc:
            logger.warning("logic_options helper unavailable: %s", exc)
            return {}

        slot = self._slot_data if isinstance(self._slot_data, dict) else {}
        extras = self._patch_extras if isinstance(self._patch_extras, dict) else {}
        if not extras:
            nested = slot.get("patch_extras")
            extras = nested if isinstance(nested, dict) else {}

        top_level = {}
        for key in (
            "required_dna",
            "energy_per_tank",
            "starting_power_bombs",
            "power_bomb_tank_ammo",
        ):
            if key in slot:
                try:
                    top_level[key] = int(slot[key])
                except Exception:
                    pass
        if self._slot_required_dna and "required_dna" not in top_level:
            top_level["required_dna"] = int(self._slot_required_dna)

        merged, source = merge_logic_option_sources(
            ("slot_data", coerce_logic_options(slot.get("logic_options"))),
            ("patch_extras", coerce_logic_options(extras.get("logic_options"))),
            ("slot_top_level", top_level),
            ("local_spoiler", self._logic_options_from_local_spoilers()),
        )
        self._slot_logic_options = merged
        self._logic_options_source = source
        return merged

    def _ensure_tracker_logic(self):
        if self._tracker_logic is not None:
            return self._tracker_logic
        try:
            import contextlib
            import io

            from worlds.metroid_dread.dread_logic import DreadLogic

            logic_opts = dict(self._resolve_logic_options())
            defaults = {
                "required_dna": int(self._slot_required_dna or 0),
                "energy_per_tank": 100,
                "starting_power_bombs": 0,
                "power_bomb_tank_ammo": 1,
            }

            class _TrackerOpt:
                def __getattr__(self, name):
                    if name in logic_opts:
                        return type("o", (), {"value": int(logic_opts[name])})()
                    if name in defaults:
                        return type("o", (), {"value": defaults[name]})()
                    # Unknown options → disabled / zero (safe for non-trick fields).
                    return type("o", (), {"value": 0})()

            class _TrackerWorld:
                player = 1
                options = _TrackerOpt()

            # Silence logic DB load prints so they don't clutter Electron stdout.
            with contextlib.redirect_stdout(io.StringIO()):
                logic = DreadLogic(_TrackerWorld())
            self._apply_slot_rando_to_logic(logic)
            self._apply_slot_start_to_logic(logic)
            self._tracker_logic = logic
            self._tracker_logic_error = None
            from worlds.metroid_dread.dread_logic import TRICK_TO_OPTION

            trick_names = set(TRICK_TO_OPTION.values())
            trick_n = sum(
                1 for k, v in logic_opts.items() if k in trick_names and int(v) > 0
            )
            logger.info(
                "Tracker logic ready (start=%s tricks_on=%s source=%s)",
                logic.starting_node,
                trick_n,
                self._logic_options_source or "defaults",
            )
            if self.electron_ui:
                print(
                    f"[tracker-logic] options source={self._logic_options_source or 'defaults'} "
                    f"tricks_on={trick_n} knowledge={logic_opts.get('knowledge_tricks', 0)}",
                    flush=True,
                )
        except Exception as exc:
            self._tracker_logic_error = str(exc)
            logger.warning("Tracker logic unavailable: %s", exc)
            self._tracker_logic = None
        return self._tracker_logic

    def _tracker_starting_item_counts(self) -> Dict[str, int]:
        """AP counts from patch_extras starting_items (ODR ITEM_* → logic names)."""
        extras = self._patch_extras if isinstance(self._patch_extras, dict) else {}
        if not extras:
            slot = self._slot_data if isinstance(self._slot_data, dict) else {}
            nested = slot.get("patch_extras")
            extras = nested if isinstance(nested, dict) else {}
        starting = extras.get("starting_items") if isinstance(extras, dict) else None
        if not isinstance(starting, dict) or not starting:
            return {}
        try:
            return bridge.counts_from_starting_items(starting)
        except Exception as exc:
            logger.warning("starting_items→counts failed: %s", exc)
            return {}

    def _tracker_item_counts(self) -> Dict[str, int]:
        """Merge start kit, AP received/precollected items, and live game inventory.

        Start-kit abilities are granted via patch_extras starting_items (and
        usually also as AP precollected → items_received). Without seeding from
        starting_items, the Hub tracker can show 0 in-logic checks at connect
        when items_received is still empty / game inventory not yet synced.

        starting_items / game inventory use max() so precollected kits are not
        double-counted once they also appear in items_received.
        """
        counts: Dict[str, int] = {}

        # AP precollected + finds both arrive as items_received.
        for entry in self._tracker_received_items():
            name = entry.get("name")
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1

        for name, n in self._tracker_starting_item_counts().items():
            counts[name] = max(counts.get(name, 0), int(n))

        if self._game_inventory_amounts:
            try:
                game_counts = bridge.counts_from_inventory_amounts(self._game_inventory_amounts)
            except Exception as exc:
                logger.warning("Game inventory→counts failed: %s", exc)
                game_counts = {}
            for name, n in game_counts.items():
                counts[name] = max(counts.get(name, 0), int(n))
        return counts

    def _tracker_in_logic_location_ids(self) -> List[int]:
        logic = self._ensure_tracker_logic()
        if logic is None:
            return []
        counts = self._tracker_item_counts()
        start = logic.starting_node
        # Key on logic-relevant counts only — raw ammo/energy flicker must not
        # force a full reachability pass on every PACKET_NEW_INVENTORY.
        cache_key = (start, tuple(sorted(counts.items())))
        if cache_key == self._in_logic_cache_key:
            return self._in_logic_location_ids
        try:
            from worlds.metroid_dread.Locations import location_table

            names = logic.reachable_pickup_names(counts)
            ids = sorted(
                int(location_table[name].id)
                for name in names
                if name in location_table and location_table[name].id is not None
            )
            self._in_logic_cache_key = cache_key
            self._in_logic_location_ids = ids
            sig = (start, len(counts), len(ids), tuple(names[:3]))
            # Debug always; stdout only when the in-logic result actually changes.
            logger.debug(
                "[tracker-logic] start=%s inv=%s in_logic=%s sample=%r",
                start,
                len(counts),
                len(ids),
                names[:3],
            )
            if self.electron_ui and sig != self._tracker_log_sig:
                self._tracker_log_sig = sig
                print(
                    f"[tracker-logic] start={start} inv={len(counts)} "
                    f"in_logic={len(ids)} sample={names[:3]!r}",
                    flush=True,
                )
            return ids
        except Exception as exc:
            self._tracker_logic_error = str(exc)
            logger.warning("In-logic compute failed: %s", exc)
            if self.electron_ui:
                print(f"[tracker-logic] ERROR {exc}", flush=True)
            return list(self._in_logic_location_ids)

    def _schedule_tracker_ui_refresh(self) -> None:
        """Trailing-debounce UI/logic refresh so inventory spam can't block the loop."""
        self._schedule_reachable_map_push()
        if not self.electron_ui:
            return
        prev = self._tracker_ui_refresh_task
        if prev is not None and not prev.done():
            prev.cancel()

        async def _delayed() -> None:
            try:
                await asyncio.sleep(self._tracker_ui_debounce_s)
                self.emit_ui_status()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Debounced tracker UI refresh failed: %s", exc)

        self._tracker_ui_refresh_task = asyncio.create_task(_delayed())

    def _schedule_reachable_map_push(self, force: bool = False) -> None:
        """Debounce AP reachability → in-game minimap (fire-and-forget Lua).

        Waits out TRANSITION / settle hold before pushing. A plain 1s debounce
        alone loses MAINMENU→INGAME paint (3.5s enter-world hold) and never
        retries — VisitBoundsSafe never runs even though the binder is LIVE.
        """
        if not self.reachable_minimap_enabled or not self.game_connected:
            return
        # Preserve force across debounce coalescing (inventory tick must not
        # cancel a scenario-load force push).
        self._reachable_map_force_pending = bool(force) or bool(
            getattr(self, "_reachable_map_force_pending", False)
        )
        prev = self._reachable_map_task
        if prev is not None and not prev.done():
            prev.cancel()

        async def _delayed() -> None:
            try:
                await asyncio.sleep(self._reachable_map_debounce_s)
                # Match enter-world hold (3.5s) + connect settle (2.5s) + slack.
                for _ in range(80):
                    if not self.game_connected:
                        return
                    if self._game_mode == "INGAME" and not self._in_transition():
                        break
                    await asyncio.sleep(0.25)
                if (
                    not self.game_connected
                    or self._game_mode != "INGAME"
                    or self._in_transition()
                ):
                    logger.debug(
                        "Reachable minimap still gated after wait (mode=%s transition=%s)",
                        self._game_mode,
                        self._in_transition(),
                    )
                    return
                use_force = bool(getattr(self, "_reachable_map_force_pending", False))
                self._reachable_map_force_pending = False
                await self.push_reachable_map(force=use_force)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Reachable map push failed: %s", exc)

        self._reachable_map_task = asyncio.create_task(_delayed())

    async def push_reachable_map(self, force: bool = False) -> None:
        """Compute reachable areas and send RL.ApplyReachableMap to the game."""
        if not self.reachable_minimap_enabled or not self.game_connected:
            return
        # Never flood VisitBoundsSafe / fillmaps during TRANSITION or settle hold.
        # Callers that schedule via _schedule_reachable_map_push wait this out;
        # direct callers (connect hold) must already be settled.
        if self._game_mode != "INGAME" or self._in_transition():
            logger.debug("Reachable minimap deferred (mode=%s transition=%s)", self._game_mode, self._in_transition())
            return
        logic = self._ensure_tracker_logic()
        if logic is None:
            return
        try:
            counts = self._tracker_item_counts()
            areas = logic.reachable_areas(counts)
            sig = reachable_map.areas_signature(areas)
            # Map-icon in-logic labels are keyed on individual pickup nodes, which
            # are finer-grained than (region, area) pairs: an item can unlock a
            # node inside an area that was already reachable (e.g. a
            # missile-locked pickup in an already-visited room), leaving the
            # area signature unchanged even though the in-logic location set
            # grew. Schedule the icon-label push on every call (its own
            # variants-signature check makes this a cheap no-op when nothing
            # actually changed) instead of only when areas expand — otherwise
            # those in-logic transitions are silently dropped.
            self._schedule_map_icon_labels_push(force=bool(force))
            if not force and sig == self._reachable_areas_sig:
                return
            self._reachable_areas_sig = sig
            lua = reachable_map.format_apply_reachable_lua(areas)
            logger.info(
                "Reachable minimap: pushing %s areas to game",
                len(areas),
            )
            await self.run_lua_code(lua, wait_response=False)
        except Exception as exc:
            logger.warning("push_reachable_map: %s", exc)

    async def _push_map_after_connect_hold(self) -> None:
        """Wait out connect INGAME settle hold, then push paint + labels once."""
        try:
            # Match _begin_transition_hold(2.5) after enter-INGAME, plus slack.
            for _ in range(40):
                if not self.game_connected:
                    return
                if self._game_mode == "INGAME" and not self._in_transition():
                    break
                await asyncio.sleep(0.25)
            if not self.game_connected or self._game_mode != "INGAME":
                return
            try:
                await self.run_lua_code("RL.GetInventoryAndSend()", wait_response=False)
            except Exception:
                pass
            await self.push_reachable_map(force=True)
            await self.push_map_icon_labels(force=True)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Deferred connect map push failed: %s", exc)

    def _patch_config_paths(self) -> Dict[str, Optional[Path]]:
        """Read dread_direct_patch_config.json paths used to locate map_icon_keys."""
        return dread_paths.config_paths(Path(__file__).resolve().parent)

    def ensure_map_icon_keys(self, force: bool = False) -> Optional[dict]:
        """Load or derive pickup/location → MAP_ICON_ItemCustom{n} mapping."""
        if self._map_icon_keys is not None and not force:
            return self._map_icon_keys
        paths = self._patch_config_paths()
        spoiler_dir = None
        if self._server_spoiler_path:
            spoiler_dir = Path(self._server_spoiler_path).parent
        player = None
        if self.slot is not None:
            player = self.player_names.get(self.slot) or self.auth
        keys, src = map_icon_labels.load_or_derive_map_icon_keys(
            mod_root=paths.get("mod_root"),
            spoiler_dir=spoiler_dir,
            player_name=player,
            games_folder=paths.get("games_folder"),
        )
        self._map_icon_keys = keys
        self._map_icon_keys_source = str(src) if src else None
        if keys:
            logger.info(
                "Map icon keys loaded (v%s, %s custom icons, %s without an icon) from %s",
                keys.get("version", "?"),
                keys.get("custom_icon_count", "?"),
                len(keys.get("skipped") or []),
                self._map_icon_keys_source or "(derived)",
            )
            if int(keys.get("version") or 0) < map_icon_labels.KEYS_VERSION:
                logger.warning(
                    "Map icon keys are stale (v%s < v%s) and no patcher.json was found to "
                    "rebuild from — labels will land on the wrong icons. Run "
                    "dread_scripts/rebuild_map_icon_keys.py or re-patch.",
                    keys.get("version"),
                    map_icon_labels.KEYS_VERSION,
                )
        else:
            logger.debug("Map icon keys unavailable — collect labels deferred until re-patch")
        return keys

    def _item_name_for_location(self, location_id: int) -> str:
        """Best-effort item name at a Dread location (scout / data package)."""
        info = getattr(self, "locations_info", None) or {}
        net = info.get(location_id)
        if net is None:
            return "Unknown Item"
        try:
            player = getattr(net, "player", None)
            item_id = getattr(net, "item", None)
            if item_id is None:
                return "Unknown Item"
            if player is not None:
                try:
                    return self.item_names.lookup_in_slot(int(item_id), int(player))
                except Exception:
                    pass
            name = self._resolve_item_name(int(item_id))
            return name or "Unknown Item"
        except Exception:
            return "Unknown Item"

    def _hinted_own_location_ids(self) -> set:
        """Locations in our world revealed by AP hints (finding_player == us)."""
        out: set = set()
        slot = getattr(self, "slot", None)
        team = getattr(self, "team", None)
        if slot is None or team is None:
            # Still honour local /test_hint_ghavoran overrides offline.
            out |= set(getattr(self, "_test_hint_location_ids", None) or set())
            return out
        key = f"_read_hints_{team}_{slot}"
        stored = getattr(self, "stored_data", None) or {}
        hints = stored.get(key) or []
        try:
            for hint in hints:
                finding = getattr(hint, "finding_player", None)
                loc = getattr(hint, "location", None)
                item = getattr(hint, "item", None)
                if finding is None or loc is None:
                    # dict-shaped hints from some code paths
                    if isinstance(hint, dict):
                        finding = hint.get("finding_player")
                        loc = hint.get("location")
                        item = hint.get("item")
                if finding is None or loc is None or item is None:
                    continue
                if int(finding) != int(slot):
                    continue
                # Any hint that carries an item id reveals the check.
                out.add(int(loc))
        except Exception as exc:
            logger.debug("hinted locations parse failed: %s", exc)
        out |= set(getattr(self, "_test_hint_location_ids", None) or set())
        return out

    def _rebuild_map_icon_states(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Returns (variants, texts) for every mapped location.

        revealed = checked ∪ AP-hinted; in_logic from tracker/DreadLogic.
        texts are full display strings for SetLocalized fallback on old subsdk9.

        Also refreshes self._map_icon_sprites (base key → atlas cell) for the
        revealed subset and self._map_icon_globals (hinted & uncollected →
        bIsGlobal) for world-map visibility; push_map_icon_labels sends both
        after the labels.
        """
        keys = self.ensure_map_icon_keys()
        if not keys:
            return {}, {}
        by_loc = keys.get("by_location_id") or {}
        if not isinstance(by_loc, dict):
            return {}, {}
        revealed_sprites = map_icon_labels.revealed_sprites_by_location_id(keys)
        sprites: Dict[str, Tuple[int, int]] = {}
        globals_map: Dict[str, bool] = {}
        # Server state + local game-reported checks (collect before RoomUpdate).
        checked = set(getattr(self, "checked_locations", None) or set())
        checked |= set(getattr(self, "locations_checked", None) or set())
        checked |= set(getattr(self, "game_reported_locations", None) or set())
        hinted = self._hinted_own_location_ids()
        in_logic = set(self._tracker_in_logic_location_ids() or [])
        variants: Dict[str, str] = {}
        texts: Dict[str, str] = {}
        for loc_str, base_key in by_loc.items():
            try:
                loc_id = int(loc_str)
            except (TypeError, ValueError):
                continue
            base = str(base_key)
            revealed = loc_id in checked or loc_id in hinted
            is_in = loc_id in in_logic
            variants[base] = map_icon_labels.variant_key(
                base, revealed=revealed, in_logic=is_in
            )
            name = (
                self._item_name_for_location(loc_id)
                if revealed
                else map_icon_labels.UNKNOWN_ITEM
            )
            texts[base] = map_icon_labels.format_map_label(name, is_in)
            if revealed:
                sprite = revealed_sprites.get(loc_id)
                # Pre-logo sidecars baked ItemSphere for foreign/unknown; prefer
                # the Archipelago atlas cell whenever nothing more specific fits.
                if sprite is None or sprite == map_icon_labels.GENERIC_ITEM_SPRITE:
                    sprite = map_icon_labels.AP_LOGO_SPRITE
                sprites[base] = sprite
            # World-map pulse only while hinted and not yet collected.
            globals_map[base] = bool(loc_id in hinted and loc_id not in checked)
        self._map_icon_labels = variants
        self._map_icon_sprites = sprites
        self._map_icon_globals = globals_map
        return variants, texts

    def _rebuild_map_icon_variants(self) -> Dict[str, str]:
        variants, _ = self._rebuild_map_icon_states()
        return variants

    def _rebuild_map_icon_labels(self) -> Dict[str, str]:
        """Alias: variants map (base → variant key)."""
        return self._rebuild_map_icon_variants()

    def _schedule_map_icon_labels_push(self, force: bool = False) -> None:
        """Debounce variant retarget push (fire-and-forget; never blocks item grants)."""
        if not self.map_icon_labels_enabled or not self.game_connected:
            return
        pending_force = bool(force) or bool(getattr(self, "_map_icon_labels_force_pending", False))
        self._map_icon_labels_force_pending = pending_force
        prev = self._map_icon_labels_task
        if prev is not None and not prev.done():
            prev.cancel()

        async def _delayed() -> None:
            try:
                # Wait out transition / enter-world hold (same class of bug as paint).
                for _ in range(80):
                    if not self.game_connected:
                        return
                    if self._game_mode == "INGAME" and not self._in_transition():
                        break
                    await asyncio.sleep(0.25)
                await asyncio.sleep(self._map_icon_labels_debounce_s)
                use_force = bool(getattr(self, "_map_icon_labels_force_pending", False))
                self._map_icon_labels_force_pending = False
                await self.push_map_icon_labels(force=use_force)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Map icon labels push failed: %s", exc)

        self._map_icon_labels_task = asyncio.create_task(_delayed())

    async def push_map_icon_labels(self, force: bool = False) -> None:
        """Send RL.ApplyMapIconVariants (SetLocalized text; redirect-only is a no-op
        while the native GetLocalized hook stays disabled — see map_hooks/text_hooks)."""
        if not self.map_icon_labels_enabled or not self.game_connected:
            return
        if self._game_mode != "INGAME" or self._in_transition():
            logger.debug(
                "Map icon labels deferred (mode=%s transition=%s)",
                self._game_mode,
                self._in_transition(),
            )
            return
        try:
            variants, texts = self._rebuild_map_icon_states()
            if not variants and not force:
                return
            sig = map_icon_labels.variants_signature(variants)
            if not force and sig == self._map_icon_labels_sig:
                return
            if not variants:
                self._map_icon_labels_sig = sig
                return
            sample = next(iter(sorted(variants.items())), ("?", "?"))
            revealed_n = sum(1 for v in variants.values() if "_R" in v)
            in_logic_n = sum(
                1 for v in variants.values() if v.endswith("_IL") or v.endswith("_R_IL")
            )
            buf = self._lua_buffer_size()
            # Must include text: OdrMap.SetIconInspectorLabel only registers a
            # GetLocalized redirect, and that native hook is currently disabled
            # (crash-safety build) — a redirect-only push is visually a no-op.
            # format_apply_map_icon_variants_chunks packs texts+variants together
            # and keeps every chunk under buffer_size (more, smaller chunks than
            # the old redirect-only push, never oversized).
            chunks = map_icon_labels.format_apply_map_icon_variants_chunks(
                variants, texts=texts, buffer_size=buf
            )
            logger.info(
                "Map icon labels: pushing %s variant(s) in %s chunk(s) "
                "(revealed~%s in_logic~%s e.g. %s→%s)",
                len(variants),
                len(chunks),
                revealed_n,
                in_logic_n,
                sample[0],
                sample[1],
            )
            for i, lua in enumerate(chunks):
                if len(lua) > buf:
                    logger.warning(
                        "Map icon label chunk %s/%s still oversized (%s > %s) — skipping",
                        i + 1,
                        len(chunks),
                        len(lua),
                        buf,
                    )
                    continue
                await self.run_lua_code(lua, wait_response=False)
                # Yield so the game can drain EXEC packets between chunks.
                await asyncio.sleep(0.05)
            self._map_icon_labels_sig = sig
        except Exception as exc:
            logger.warning("push_map_icon_labels: %s", exc)
        try:
            await self.push_map_icon_sprites(force=force)
        except Exception as exc:
            logger.warning("push_map_icon_sprites: %s", exc)
        try:
            await self.push_map_icon_globals(force=force)
        except Exception as exc:
            logger.warning("push_map_icon_globals: %s", exc)

    def _lua_buffer_size(self) -> int:
        """Remote-Lua EXEC packet limit; every chunk must fit inside one."""
        if self._socket is not None:
            try:
                return int(getattr(self._socket, "buffer_size", 4096) or 4096)
            except (TypeError, ValueError):
                pass
        return 4096

    async def push_map_icon_sprites(self, force: bool = False) -> None:
        """
        Swap revealed icons' graphics via RL.ApplyMapIconSprites.

        Only revealed locations are sent: everything else is already sitting on
        the patch-time `unknown` cell, so an unrevealed icon needs no write.
        """
        if not self.map_icon_labels_enabled or not self.game_connected:
            return
        if self._game_mode != "INGAME" or self._in_transition():
            return
        sprites = dict(getattr(self, "_map_icon_sprites", None) or {})
        sig = map_icon_labels.sprites_signature(sprites)
        if not force and sig == self._map_icon_sprites_sig:
            return
        if not sprites:
            self._map_icon_sprites_sig = sig
            return
        buf = self._lua_buffer_size()
        chunks = map_icon_labels.format_apply_map_icon_sprites_chunks(
            sprites, buffer_size=buf
        )
        logger.info(
            "Map icon sprites: revealing %s icon(s) in %s chunk(s)",
            len(sprites),
            len(chunks),
        )
        for lua in chunks:
            if len(lua) > buf:
                continue
            await self.run_lua_code(lua, wait_response=False)
            await asyncio.sleep(0.05)
        self._map_icon_sprites_sig = sig

    async def push_map_icon_globals(self, force: bool = False) -> None:
        """Push bIsGlobal for hinted icons via RL.ApplyMapIconGlobals."""
        if not self.map_icon_labels_enabled or not self.game_connected:
            return
        if self._game_mode != "INGAME" or self._in_transition():
            return
        globals_map = dict(getattr(self, "_map_icon_globals", None) or {})
        # Only ship icons that are true, plus any previously-true clears.
        # Sending every false every connect is wasteful; merge prior true→false.
        prev = getattr(self, "_map_icon_globals_prev_true", None) or set()
        to_send: Dict[str, bool] = {}
        true_now = {k for k, v in globals_map.items() if v}
        for key in true_now:
            to_send[key] = True
        for key in prev - true_now:
            to_send[key] = False
        sig = map_icon_labels.globals_signature(to_send)
        if not force and sig == self._map_icon_globals_sig:
            return
        if not to_send:
            self._map_icon_globals_sig = sig
            self._map_icon_globals_prev_true = true_now
            return
        buf = self._lua_buffer_size()
        chunks = map_icon_labels.format_apply_map_icon_globals_chunks(
            to_send, buffer_size=buf
        )
        logger.info(
            "Map icon globals: updating %s icon(s) in %s chunk(s) (true=%s)",
            len(to_send),
            len(chunks),
            len(true_now),
        )
        for lua in chunks:
            if len(lua) > buf:
                continue
            await self.run_lua_code(lua, wait_response=False)
            await asyncio.sleep(0.05)
        self._map_icon_globals_sig = sig
        self._map_icon_globals_prev_true = true_now

    def _run_test_hint_ghavoran(self, output) -> None:
        """Client-command body: simulate a Ghavoran AP hint for map testing."""
        if not self.game_connected:
            output("Error: Not connected to Metroid Dread")
            return
        keys = self.ensure_map_icon_keys()
        if not keys:
            output("Error: map_icon_keys not loaded — re-patch / reconnect")
            return
        entries = keys.get("entries") or []
        checked = set(getattr(self, "checked_locations", None) or set())
        checked |= set(getattr(self, "locations_checked", None) or set())
        checked |= set(getattr(self, "game_reported_locations", None) or set())
        chosen = None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                loc_id = int(entry.get("location_id"))
            except (TypeError, ValueError):
                continue
            # Prefer actor path / scenario hints when present; else name match.
            scenario = str(entry.get("scenario") or "")
            actor = str(entry.get("actor") or "")
            region = str(entry.get("region") or "")
            key = str(entry.get("key") or "")
            is_ghavoran = (
                scenario == "s050_forest"
                or region.lower() == "ghavoran"
                or "forest" in actor.lower()
            )
            if not is_ghavoran:
                loc_name = ""
                try:
                    names = getattr(self, "location_names", None)
                    if names is not None:
                        loc_name = str(names.lookup_in_game(loc_id) or "")
                except Exception:
                    loc_name = ""
                if not loc_name.lower().startswith("ghavoran"):
                    continue
            if loc_id in checked:
                continue
            chosen = (loc_id, key or str(entry.get("key") or ""), entry)
            break
        if chosen is None:
            # Last resort: hard-known Ghavoran missile tank from vanilla ids.
            for loc_id in (84103, 84104, 84105):
                by_loc = keys.get("by_location_id") or {}
                base = by_loc.get(str(loc_id))
                if base and loc_id not in checked:
                    chosen = (loc_id, str(base), {"location_id": loc_id, "key": base})
                    break
        if chosen is None:
            output("Error: no uncollected Ghavoran map-icon location found")
            return
        loc_id, base_key, entry = chosen
        self._test_hint_location_ids.add(loc_id)
        # Force sprite to AP logo when the baked sprite is generic/unknown so
        # the atlas cell is obviously the new logo during this smoke test.
        sprite = map_icon_labels.normalize_sprite(entry.get("sprite"))
        if sprite is None or sprite in (
            map_icon_labels.GENERIC_ITEM_SPRITE,
            map_icon_labels.UNKNOWN_SPRITE,
        ):
            # Mutate the in-memory sidecar so rebuild picks up the logo cell.
            entry["sprite"] = list(map_icon_labels.AP_LOGO_SPRITE)
        item_name = self._item_name_for_location(loc_id) or "Unknown Item"
        icon_id = map_icon_labels.icon_id_from_base_key(base_key)
        output(
            f"Test hint Ghavoran: loc={loc_id} {icon_id} item={item_name!r} "
            f"— revealing sprite + bIsGlobal. Open pause world map / Ghavoran."
        )
        self._map_icon_labels_sig = None
        self._map_icon_sprites_sig = None
        self._map_icon_globals_sig = None
        self._schedule_map_icon_labels_push(force=True)
        # Also poke ForceEntityIconVisible when we know the actor.
        actor = str(entry.get("actor") or "").strip()
        if actor and all(c.isalnum() or c in "_-" for c in actor):
            lua = (
                f'RL.SendApLog("AP_MAP: test_hint_ghavoran {icon_id} loc={loc_id}") '
                f'pcall(function() Game.ForceEntityIconVisible("{actor}") end)'
            )
            asyncio.create_task(self.run_lua_code(lua, wait_response=False))

    def ui_status_payload(self) -> dict:
        # WebSocket alone is not "connected" for Hub — wait until slot auth completes.
        ap_connected = bool(
            getattr(self, "server") and self.server and getattr(self, "slot", None) is not None
        )
        received = getattr(self, "items_received", []) or []
        checked = getattr(self, "checked_locations", set()) or set()
        missing = getattr(self, "missing_locations", set()) or set()
        counts = self._tracker_item_counts() if self.electron_ui else {}
        in_logic_ids = self._tracker_in_logic_location_ids() if self.electron_ui else []
        start = ""
        if self._tracker_logic is not None:
            try:
                start = "/".join(self._tracker_logic.starting_node)
            except Exception:
                start = str(self._tracker_logic.starting_node)
        game_name = ""
        try:
            if self.slot is not None and getattr(self, "slot_info", None):
                info = self.slot_info.get(self.slot)
                if info is not None:
                    game_name = getattr(info, "game", None) or (info[1] if len(info) > 1 else "") or ""
        except Exception:
            game_name = self.game or ""
        if not game_name:
            game_name = self.game or ""
        return {
            "ap_connected": ap_connected,
            "game_connected": bool(self.game_connected),
            "slot": self.auth or "",
            "server": (str(self.server_address) if self.server_address else ""),
            "dread_ip": self.dread_ip,
            "game": game_name,
            "seed_name": getattr(self, "seed_name", None) or "",
            "scenario": self.current_scenario or "",
            "game_mode": self._game_mode or "UNKNOWN",
            "in_transition": self._in_transition(),
            "version": self.version or "",
            "layout_uuid": self.layout_uuid or "",
            # Counts for main UI pills (keep key names for compatibility).
            "items_received": len(received),
            "checked_locations": len(checked),
            "missing_locations": len(missing),
            "received_pickups": self.received_pickups,
            "inventory_index": self.inventory_index,
            "deathlink_enabled": bool(self.deathlink_enabled),
            "deaths_total": self.deaths_total,
            "deaths_self": self.deaths_self,
            "deaths_deathlink": self.deaths_deathlink,
            # Lists for built-in tracker window.
            "received_items": self._tracker_received_items(),
            "checked_location_ids": self._tracker_checked_location_ids(),
            "in_logic_location_ids": in_logic_ids,
            "in_logic_count": len(in_logic_ids),
            "logic_error": self._tracker_logic_error or "",
            "logic_item_count": len(counts),
            "logic_start": start,
        }

    def emit_ui_status(self) -> None:
        try:
            self.emit_ui("status", **self.ui_status_payload())
        except Exception as exc:
            logger.warning("emit_ui_status failed: %s", exc)
            if self.electron_ui:
                print(f"[tracker-logic] emit_ui_status failed: {exc}", flush=True)

    async def _ui_status_loop(self) -> None:
        ticks = 0
        while not self.exit_event.is_set():
            try:
                self.emit_ui_status()
                ticks += 1
                # Keep game inventory fresh for in-logic (start items live here).
                if self.game_connected and ticks % 3 == 0:
                    try:
                        await self.run_lua_code("RL.GetInventoryAndSend()", wait_response=False)
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("UI status loop error: %s", exc)
                if self.electron_ui:
                    print(f"[tracker-logic] status loop error: {exc}", flush=True)
            await asyncio.sleep(1.0)

    async def _electron_abort_connect(
        self, error: str, detail: str, *, event_type: str = "ap_error"
    ) -> None:
        """Surface a Hub error and tear down without deadlocking server_loop."""
        logger.error(detail)
        self.emit_ui(event_type, error=error, detail=detail, **self.ui_status_payload())
        self.emit_ui_status()
        # Must NOT await self.disconnect() here — disconnect waits on server_task,
        # and we are often called from inside server_loop (deadlock → UI stuck).
        self.disconnected_intentionally = True
        self.cancel_autoreconnect()
        self.exit_event.set()
        sock = getattr(getattr(self, "server", None), "socket", None)
        if sock is not None and not getattr(sock, "closed", True):
            try:
                await sock.close()
            except Exception:
                pass

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            # Hub/Electron has no stdin password prompt — surface a UI error instead of hanging.
            # Also covers InvalidPassword: CommonClient clears password then re-calls server_auth.
            if self.electron_ui:
                await self._electron_abort_connect(
                    "Password required",
                    "This room needs a password (missing or incorrect). Enter it in the "
                    "Password field on the connect screen, then Connect again.",
                    event_type="password_required",
                )
                return
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self._refresh_item_id_to_name()
            slot_data = args.get("slot_data") or {}
            self._slot_data = dict(slot_data) if isinstance(slot_data, dict) else {}
            extras = self._slot_data.get("patch_extras")
            self._patch_extras = dict(extras) if isinstance(extras, dict) else {}
            try:
                from worlds.metroid_dread.logic_options import coerce_logic_options

                self._slot_logic_options = coerce_logic_options(
                    self._slot_data.get("logic_options")
                ) or coerce_logic_options(
                    self._patch_extras.get("logic_options")
                )
            except Exception:
                self._slot_logic_options = {}
            self._logic_options_source = None
            if slot_data.get("death_link") and not self.deathlink_client_override:
                self.deathlink_enabled = True
                asyncio.create_task(self.update_death_link(True))
            start = slot_data.get("starting_location")
            if isinstance(start, dict):
                self._slot_starting_location = start
            try:
                self._slot_required_dna = int(slot_data.get("required_dna", 0) or 0)
            except Exception:
                self._slot_required_dna = 0
            # Rebuild logic with seed start / required DNA.
            self._tracker_logic = None
            self._tracker_logic_error = None
            self._in_logic_cache_key = None
            self._tracker_log_sig = None
            self.emit_ui("ap_connected", **self.ui_status_payload())
            self.emit_ui_status()
            # Average players don't have a local spoiler — ask the server for placements.
            if self._server_spoiler_task and not self._server_spoiler_task.done():
                self._server_spoiler_task.cancel()
            self._server_spoiler_task = asyncio.create_task(self.download_patch_spoiler())
            # Server checked_locations → collected map labels (after keys load / scout).
            self._schedule_map_icon_labels_push(force=True)
        elif cmd == "ReceivedItems":
            # Game sync is driven by items_received + ReceivedPickups index.
            self.emit_ui_status()
            # Own-world finds may clarify item names once locations_info / grants settle.
            self._schedule_map_icon_labels_push()
            # Offline / mid-session arrivals must kick catch-up immediately (do not
            # wait for the 1s main-loop tick or a later pickup ACK).
            if self.game_connected:
                asyncio.create_task(self.send_items_to_game(), name="ReceivedItemsGrant")
        elif cmd == "RoomInfo":
            if args.get("seed_name"):
                self.seed_name = args.get("seed_name")
            # seed_name is already included via ui_status_payload() — don't pass it twice.
            self.emit_ui(
                "room_info",
                password_required=bool(args.get("password")),
                **self.ui_status_payload(),
            )
        elif cmd == "DataPackage":
            self._refresh_item_id_to_name()
        elif cmd == "LocationInfo":
            if self._awaiting_patch_scouts:
                self.watcher_event.set()
            # Scout replies upgrade reveal names for collected/hinted checks.
            self._schedule_map_icon_labels_push()
        elif cmd == "RoomUpdate":
            if args.get("checked_locations") is not None:
                self._schedule_map_icon_labels_push(force=True)
        elif cmd in ("SetReply", "Retrieved"):
            # AP hints live in stored_data[_read_hints_{team}_{slot}].
            keys = args.get("keys") if cmd == "Retrieved" else None
            key = args.get("key") if cmd == "SetReply" else None
            hint_key = None
            if self.slot is not None and self.team is not None:
                hint_key = f"_read_hints_{self.team}_{self.slot}"
            if hint_key and (
                key == hint_key
                or (isinstance(keys, (list, tuple, set)) and hint_key in keys)
            ):
                self._schedule_map_icon_labels_push(force=True)

    async def download_patch_spoiler(self, force: bool = False) -> Optional[str]:
        """
        Scout all Dread locations from the live Archipelago server and write a
        synthetic spoiler the hub patcher can consume. No local AP zip required.
        """
        if self._server_spoiler_path and Path(self._server_spoiler_path).is_file() and not force:
            self.emit_ui(
                "patch_files_ready",
                spoiler_path=self._server_spoiler_path,
                source="server_cache",
                **self.ui_status_payload(),
            )
            return self._server_spoiler_path

        if not self.server or self.slot is None:
            msg = "Not connected to Archipelago — cannot download patch data."
            logger.warning(msg)
            self.emit_ui("patch_files_error", error=msg, **self.ui_status_payload())
            return None

        loc_ids = sorted(self.server_locations or (self.missing_locations | self.checked_locations))
        if not loc_ids:
            msg = "Server reported no locations for this slot."
            logger.error(msg)
            self.emit_ui("patch_files_error", error=msg, **self.ui_status_payload())
            return None

        self.emit_ui(
            "patch_files_progress",
            detail=f"Requesting {len(loc_ids)} placements from server…",
            **self.ui_status_payload(),
        )
        logger.info("Downloading patch data: scouting %d locations", len(loc_ids))

        # Clear prior scout cache for a clean rebuild when forced.
        if force:
            for lid in loc_ids:
                self.locations_info.pop(lid, None)

        self._awaiting_patch_scouts = True
        try:
            await self.send_msgs(
                [{"cmd": "LocationScouts", "locations": loc_ids, "create_as_hint": 0}]
            )

            # Wait until LocationInfo fills locations_info (chunked replies possible).
            deadline = asyncio.get_event_loop().time() + 45.0
            while asyncio.get_event_loop().time() < deadline:
                have = sum(1 for lid in loc_ids if lid in self.locations_info)
                if have >= len(loc_ids):
                    break
                if have and have % 25 == 0:
                    self.emit_ui(
                        "patch_files_progress",
                        detail=f"Received {have}/{len(loc_ids)} placements…",
                        **self.ui_status_payload(),
                    )
                try:
                    await asyncio.wait_for(self.watcher_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                self.watcher_event.clear()

            have = sum(1 for lid in loc_ids if lid in self.locations_info)
            if have < max(1, int(len(loc_ids) * 0.9)):
                msg = (
                    f"Server only returned {have}/{len(loc_ids)} location placements. "
                    "Try /download_patch again."
                )
                logger.error(msg)
                self.emit_ui("patch_files_error", error=msg, **self.ui_status_payload())
                return None

            our_name = self.player_names.get(self.slot) or self.auth or "DreadPlayer"

            def loc_lookup(location_id: int) -> str:
                return self.location_names.lookup_in_game(location_id)

            def item_lookup(item_id: int, player_id: int) -> str:
                try:
                    return self.item_names.lookup_in_slot(item_id, player_id)
                except Exception:
                    return self.item_names.lookup_in_game(item_id)

            placements = dread_server_spoiler.placements_from_locations_info(
                location_ids=loc_ids,
                locations_info=self.locations_info,
                location_name_lookup=loc_lookup,
                item_name_lookup=item_lookup,
                player_names=self.player_names,
                our_slot=self.slot,
                our_name=our_name,
            )
            if not placements:
                msg = "Scout succeeded but no placements could be decoded."
                logger.error(msg)
                self.emit_ui("patch_files_error", error=msg, **self.ui_status_payload())
                return None

            start = self._slot_starting_location or {}
            starting_path = (
                start.get("path")
                or "/".join(
                    str(start[k])
                    for k in ("region", "area", "node")
                    if start.get(k)
                )
                or ""
            )
            seed = getattr(self, "seed_name", None) or "server"
            text = dread_server_spoiler.build_synthetic_spoiler(
                player_name=our_name,
                seed_name=str(seed),
                starting_path=starting_path,
                placements=placements,
                patch_extras=self._patch_extras,
                player_names=self.player_names,
            )

            out_dir = Path(Utils.user_path("output", "_patcher_extract", f"server_{seed}"))
            out_path = out_dir / f"AP_{our_name}_server_Spoiler.txt"
            dread_server_spoiler.write_synthetic_spoiler(out_path, text)
            self._server_spoiler_path = str(out_path)

            logger.info(
                "Wrote server-built spoiler (%d placements) → %s",
                len(placements),
                out_path,
            )
            self.emit_ui(
                "patch_files_ready",
                spoiler_path=str(out_path),
                source="server",
                placement_count=len(placements),
                has_patch_extras=bool(self._patch_extras),
                **self.ui_status_payload(),
            )
            # LocationInfo is filled — refresh collected labels with real item names.
            self._schedule_map_icon_labels_push(force=True)
            return str(out_path)
        except Exception as exc:
            msg = f"Failed to download patch data from server: {exc}"
            logger.exception(msg)
            self.emit_ui("patch_files_error", error=msg, **self.ui_status_payload())
            return None
        finally:
            self._awaiting_patch_scouts = False

    def event_invalid_slot(self):
        msg = (
            "Invalid Slot — the server does not have a player named "
            f"{self.auth!r}.\n"
            "  • Use the exact slot name from your YAML / room player list\n"
            "  • Paste the room connection from the Archipelago host page "
            "(archipelago://… or host:port), not a random lobby"
        )
        # Avoid raising — that crashes the server loop mid-handshake and confuses the UI.
        if self.electron_ui:
            self.disconnected_intentionally = True
            self.cancel_autoreconnect()
            self.exit_event.set()
            self.emit_ui("ap_error", error="Invalid Slot", detail=msg, **self.ui_status_payload())
            self.emit_ui_status()
            sock = getattr(getattr(self, "server", None), "socket", None)
            if sock is not None and not getattr(sock, "closed", True):
                asyncio.create_task(sock.close())
            return
        logger.error(msg)
        self.emit_ui("ap_error", error="Invalid Slot", detail=msg, **self.ui_status_payload())
        self.emit_ui_status()

    def event_invalid_game(self):
        msg = (
            "Invalid Game — this slot is not Metroid Dread "
            "(or the room was generated without this AP world)."
        )
        if self.electron_ui:
            self.disconnected_intentionally = True
            self.cancel_autoreconnect()
            self.exit_event.set()
            self.emit_ui("ap_error", error="Invalid Game", detail=msg, **self.ui_status_payload())
            self.emit_ui_status()
            sock = getattr(getattr(self, "server", None), "socket", None)
            if sock is not None and not getattr(sock, "closed", True):
                asyncio.create_task(sock.close())
            return
        logger.error(msg)
        self.emit_ui("ap_error", error="Invalid Game", detail=msg, **self.ui_status_payload())
        self.emit_ui_status()

    def on_deathlink(self, data: dict):
        super().on_deathlink(data)
        if not self.deathlink_enabled:
            return
        source = data.get("source", "DeathLink")
        # Ignore own bounce (time filter can fail on JSON float) and any signal
        # that arrives while we already own this death episode. Re-killing here
        # would fire OnPlayerDead again → ODR HUD +2 and a second DeathLink.
        if self._deathlink_block_until_respawn or self.deathlink_sent_this_death:
            logger.debug(
                "DeathLink inbound ignored (%s) — episode already active", source
            )
            return
        my_name = self.player_names.get(self.slot) if self.slot is not None else None
        if my_name and source == my_name:
            logger.debug("DeathLink inbound ignored — own source %s", source)
            return
        # Friend killed us — death anim must not bounce another DeathLink.
        self._deathlink_begin_episode("inbound")
        self._death_episode_from_remote = True
        self._record_death("deathlink")
        asyncio.create_task(self.trigger_deathlink_kill(source))

    def death_counter_status(self) -> str:
        return (
            f"Deaths: total={self.deaths_total} "
            f"self={self.deaths_self} deathlink={self.deaths_deathlink}"
        )

    def _record_death(self, kind: str) -> None:
        self.deaths_total += 1
        if kind == "deathlink":
            self.deaths_deathlink += 1
        else:
            self.deaths_self += 1
        logger.info("[DEATHS] %s (%s)", self.death_counter_status(), kind)
        self.emit_ui(
            "death",
            kind=kind,
            deaths_total=self.deaths_total,
            deaths_self=self.deaths_self,
            deaths_deathlink=self.deaths_deathlink,
        )
        self.emit_ui_status()

    def _deathlink_begin_episode(
        self,
        reason: str,
        *,
        generation: Optional[int] = None,
        deaths: Optional[int] = None,
    ) -> None:
        """Suppress outbound DeathLinks until AP_DEATH respawn log.

        Log path and poll path share this latch. When generation/deaths are
        unknown (log path), claim at least poll_gen+1 so a later poll of the
        same death cannot re-send after a false early respawn clear.
        """
        self.deathlink_sent_this_death = True
        self._deathlink_block_until_respawn = True
        if generation is not None:
            self._death_poll_generation = max(self._death_poll_generation, generation)
            self._deathlink_handled_generation = max(
                self._deathlink_handled_generation, generation
            )
        else:
            # Log fired before poll saw the new gen — reserve the next slot.
            self._deathlink_handled_generation = max(
                self._deathlink_handled_generation,
                self._death_poll_generation + 1,
            )
        if deaths is not None:
            self._death_poll_death_count = max(self._death_poll_death_count, deaths)
            self._deathlink_handled_deaths = max(
                self._deathlink_handled_deaths, deaths
            )
        else:
            self._deathlink_handled_deaths = max(
                self._deathlink_handled_deaths, self._death_poll_death_count
            )
        logger.debug(
            "DeathLink episode begin (%s) handled_gen=%d handled_deaths=%d",
            reason,
            self._deathlink_handled_generation,
            self._deathlink_handled_deaths,
        )

    def _deathlink_end_episode(self, reason: str) -> None:
        self.deathlink_sent_this_death = False
        self._deathlink_block_until_respawn = False
        self._death_episode_from_remote = False
        logger.debug("DeathLink episode end (%s)", reason)

    async def trigger_deathlink_kill(self, source: str):
        if not self.game_connected:
            logger.warning("DeathLink received but not connected to Metroid Dread")
            return
        lua = bridge.format_deathlink_kill_lua(source)
        logger.info("[DEATHLINK] Triggering death in game from %s", source)
        try:
            await self.run_lua_code(lua)
        except Exception as e:
            logger.error("DeathLink kill failed: %s", e)

    # ----- packet framing (Randovania DreadExecutor) -----

    def _build_packet(self, packet_type: PacketType, data: Optional[bytes] = None) -> bytes:
        packet = bytearray([packet_type])
        if data is not None:
            if packet_type == PacketType.PACKET_REMOTE_LUA_EXEC:
                packet.extend(len(data).to_bytes(4, "little"))
            if packet_type in (PacketType.PACKET_REMOTE_LUA_EXEC, PacketType.PACKET_HANDSHAKE):
                packet.extend(data)
        return bytes(packet)

    async def _check_header(self):
        if self._socket is None:
            raise OSError("Dread socket closed")
        received_number = await asyncio.wait_for(self._socket.reader.read(1), timeout=30)
        if not received_number:
            raise OSError("Connection closed while reading request number")
        if received_number[0] != self._socket.request_number:
            raise DreadLuaException(
                f"Expected response {self._socket.request_number}, got {received_number[0]}"
            )

    async def _parse_packet(self, packet_type: int) -> Optional[bytes]:
        if self._socket is None:
            raise OSError("Dread socket closed")
        response = None

        if packet_type == PacketType.PACKET_MALFORMED:
            error_data = await asyncio.wait_for(self._socket.reader.read(9), timeout=15)
            # Game rejected a PACKET_REMOTE_LUA_EXEC (often oversized > buffer_size).
            # Do not tear down the socket — log and continue so paint/labels can recover.
            logger.error(
                "Dread malformed packet (oversized Lua?): %s — continuing read loop",
                error_data.hex(),
            )
            return None

        if packet_type == PacketType.PACKET_HANDSHAKE:
            await self._check_header()
            self._socket.request_number = (self._socket.request_number + 1) % 256
            return None

        if packet_type == PacketType.PACKET_REMOTE_LUA_EXEC:
            await self._check_header()
            self._socket.request_number = (self._socket.request_number + 1) % 256
            header = await asyncio.wait_for(self._socket.reader.read(4), timeout=15)
            is_success = bool(header[0])
            length = struct.unpack("<l", header[1:4] + b"\x00")[0]
            data = await asyncio.wait_for(self._socket.reader.read(length), timeout=15)
            if not is_success:
                logger.warning(
                    "Lua execution failed: %s", data.decode("utf-8", errors="ignore")
                )
                if self._lua_response_future and not self._lua_response_future.done():
                    self._lua_response_future.set_exception(DreadLuaException("Lua execution failed"))
                raise DreadLuaException("Lua execution failed")
            if self._lua_response_future and not self._lua_response_future.done():
                self._lua_response_future.set_result(data)
            return data

        # Async push packets: [type][u32 len][payload]
        length_data = await asyncio.wait_for(self._socket.reader.read(4), timeout=15)
        length = struct.unpack("<l", length_data)[0]
        data = await asyncio.wait_for(self._socket.reader.read(length), timeout=15)

        if packet_type == PacketType.PACKET_NEW_INVENTORY:
            await self._handle_inventory(data.decode("utf-8", errors="ignore"))
        elif packet_type == PacketType.PACKET_COLLECTED_INDICES:
            await self._handle_collected_locations(data)
        elif packet_type == PacketType.PACKET_RECEIVED_PICKUPS:
            await self._handle_received_pickups(data.decode("utf-8", errors="ignore"))
        elif packet_type == PacketType.PACKET_GAME_STATE:
            await self._handle_game_state(data.decode("utf-8", errors="ignore"))
        elif packet_type == PacketType.PACKET_LOG_MESSAGE:
            await self._handle_log_message(data.decode("utf-8", errors="ignore"))
        else:
            logger.warning("Unknown packet type: 0x%02x", packet_type)

        return response

    async def _read_response(self) -> Optional[bytes]:
        if not self._socket:
            return None
        packet_type_bytes = await asyncio.wait_for(self._socket.reader.read(1), timeout=None)
        if len(packet_type_bytes) == 0:
            raise OSError("Connection closed")
        return await self._parse_packet(packet_type_bytes[0])

    async def run_lua_code(
        self, code: str, *, wait_response: bool = False, timeout: float = 30.0
    ) -> Optional[bytes]:
        """
        Send Lua over PACKET_REMOTE_LUA_EXEC.

        Default is fire-and-forget so item grants are not blocked waiting on the
        game thread. Pass wait_response=True only when the caller needs the return
        value (bootstrap, death probe). While waiting, _run_code_lock is held so
        only one awaited EXEC is in flight at a time.
        """
        async with self._run_code_lock:
            if not self._socket:
                return None

            future: Optional[asyncio.Future] = None
            if wait_response:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._lua_response_future = future

            try:
                self._socket.writer.write(
                    self._build_packet(PacketType.PACKET_REMOTE_LUA_EXEC, code.encode("utf-8"))
                )
                await asyncio.wait_for(self._socket.writer.drain(), timeout=timeout)

                if future is None:
                    return None

                if self.read_task is None or self.read_task.done():
                    return await self._read_response()

                return await asyncio.wait_for(future, timeout=timeout)
            finally:
                if self._lua_response_future is future:
                    self._lua_response_future = None

    async def query_death_status(self) -> Optional[str]:
        response = await self.run_lua_code(
            "return RL.GetDeathPollStatus()", wait_response=True, timeout=2.0
        )
        if not response:
            return None
        return response.decode("ascii", errors="ignore")

    async def process_death_poll_status(self, status: str, *, source: str = "poll") -> None:
        """Handle RL.GetDeathPollStatus() — mode,health,max,deaths,pending,gen,wasalive,deathsent."""
        parts = status.split(",")
        if len(parts) < 8:
            logger.debug("DeathLink %s: malformed status %r", source, status)
            return

        mode = parts[0]
        try:
            health = float(parts[1])
            deaths = int(parts[3])
            pending = parts[4] == "1"
            generation = int(parts[5])
            death_sent_game = parts[7].strip().lower() == "true"
        except ValueError:
            logger.debug("DeathLink %s: could not parse status %r", source, status)
            return

        if deaths > self._death_poll_death_count:
            self._death_poll_death_count = deaths
        if generation > self._death_poll_generation:
            self._death_poll_generation = generation

        logger.debug(
            "DeathLink %s: mode=%s health=%.1f deaths=%d pending=%s gen=%d "
            "block=%s handled_gen=%d game_sent=%s",
            source,
            mode,
            health,
            deaths,
            pending,
            generation,
            self._deathlink_block_until_respawn,
            self._deathlink_handled_generation,
            death_sent_game,
        )

        # While an episode is open, never send. Keep absorbing gen/death ids so a
        # false early "respawn" cannot re-send this same death later.
        if self._deathlink_block_until_respawn or self.deathlink_sent_this_death:
            self._deathlink_handled_generation = max(
                self._deathlink_handled_generation, generation
            )
            self._deathlink_handled_deaths = max(
                self._deathlink_handled_deaths, deaths
            )
            return

        # Generation already claimed (log path reserves poll_gen+1) — never re-send
        # this death even if death-count advanced or episode was cleared early.
        if generation > 0 and generation <= self._deathlink_handled_generation:
            self._deathlink_handled_deaths = max(
                self._deathlink_handled_deaths, deaths
            )
            return

        # No generation signal: fall back to death-count watermark.
        if generation <= 0 and deaths <= self._deathlink_handled_deaths:
            return

        # Only treat a *new* death-count or generation as a sendable event.
        new_death = (
            generation > self._deathlink_handled_generation
            or deaths > self._deathlink_handled_deaths
        )
        if new_death and (pending or health <= 0 or death_sent_game):
            await self._handle_local_death(
                f"poll ({source})",
                generation=generation,
                deaths=deaths,
            )

    async def _handle_local_death(
        self,
        via: str,
        *,
        generation: Optional[int] = None,
        deaths: Optional[int] = None,
    ) -> None:
        async with self._deathlink_lock:
            if self._deathlink_block_until_respawn or self.deathlink_sent_this_death:
                # Inbound DeathLink already counted; ignore echo from death anim / log.
                # Absorb ids so poll cannot re-arm the same death after a false clear.
                if generation is not None:
                    self._deathlink_handled_generation = max(
                        self._deathlink_handled_generation, generation
                    )
                if deaths is not None:
                    self._deathlink_handled_deaths = max(
                        self._deathlink_handled_deaths, deaths
                    )
                logger.debug("DeathLink: local death ignored (%s) — episode active", via)
                return
            # Count every local death (even when DeathLink is off).
            self._record_death("self")
            # Claim BEFORE await so log path + poll path share one latch / one send.
            self._deathlink_begin_episode(via, generation=generation, deaths=deaths)
            if not self.deathlink_enabled:
                logger.info(
                    "Local death via %s (DeathLink off) — %s",
                    via,
                    self.death_counter_status(),
                )
                return
            logger.info("DeathLink: local death detected, sending... (via %s)", via)
            await self.send_death("died in Metroid Dread")

    async def _death_poll_loop(self) -> None:
        # Slow poll on purpose: DeathLink latency of ~1–2s is fine, and awaiting
        # GetDeathPollStatus under _run_code_lock must not starve RL.ReceivePickup.
        while self.game_connected:
            try:
                await asyncio.sleep(2.0)
                if not self.game_connected or not self.deathlink_enabled:
                    continue
                # Never contend with an in-flight item grant / popup cooldown.
                if self.in_cooldown or self._run_code_lock.locked():
                    continue
                status = await self.query_death_status()
                if status:
                    await self.process_death_poll_status(status)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Death poll error: %s", e)

    async def _map_icon_bank_watch_loop(self) -> None:
        """
        Poll OdrText.IsBankReady (via RL.MapIconBankStatus — passive, never
        LoadBank/EnsureBank) and force a fresh label push the instant the
        language bank flips ready.

        OdrText.SetLocalized soft-fails with reason=bank-not-ready until the
        game has populated its CLanguageManager BTXT dictionary. Relying only
        on the Lua-side Game.AddSF backoff retry or on unrelated game events
        (item grants, room changes) to eventually trigger another push left
        labels stuck on their patch-time default indefinitely once those
        stopped retrying. This loop is the dedicated "wait for ready, then
        apply" path; it is cheap (one read-only Lua round trip) and never
        touches the crashing EnsureBank/LoadBank natives.

        Note that IsBankReady and SetLocalized's own gate evaluate the SAME
        native predicate, so this loop can only ever help when readiness
        genuinely flips over time. Up to OdrText 0.1.10 it never did — the
        native side dereferenced the language-manager holder once instead of
        twice and so read a fixed non-dictionary triple forever, which no
        amount of retrying could move. That silent stall is why this loop logs
        the observed status (including the OdrText build) rather than waiting
        mutely: a permanently unready bank must be visible in the log.
        """
        delay = 1.5
        last_status: Optional[str] = None
        waiting_since: Optional[float] = None
        next_stall_warning = 30.0
        while self.game_connected:
            try:
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 5.0)
                if not self.game_connected or not self.map_icon_labels_enabled:
                    continue
                if self._run_code_lock.locked() or self.in_cooldown:
                    continue
                response = await self.run_lua_code(
                    "return tostring(RL.MapIconBankStatus())",
                    wait_response=True,
                    timeout=2.0,
                )
                if response is None:
                    continue
                status = response.decode("ascii", errors="ignore").strip()
                # "version|ready|reason"
                parts = status.split("|")
                ready = len(parts) >= 2 and parts[1] == "true"
                if status != last_status:
                    last_status = status
                    logger.info("Map icon language bank status: %s", status)
                if ready and not self._map_icon_bank_ready:
                    logger.info("Map icon language bank ready — reapplying labels")
                    self._map_icon_bank_ready = True
                    waiting_since = None
                    next_stall_warning = 30.0
                    delay = 5.0
                    await self.push_map_icon_labels(force=True)
                elif not ready:
                    self._map_icon_bank_ready = False
                    now = time.monotonic()
                    if waiting_since is None:
                        waiting_since = now
                    elif now - waiting_since >= next_stall_warning:
                        logger.warning(
                            "Map icon labels still blocked after %.0fs (%s) — "
                            "labels will stay at their patch-time default",
                            now - waiting_since,
                            status,
                        )
                        next_stall_warning *= 4
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.info("Map icon bank watch error: %s", exc)

    # ----- connection lifecycle -----

    @staticmethod
    def _classify_game_state_token(token: str) -> str:
        """
        Map a GAME_STATE token to MAINMENU | INGAME | TRANSITION | UNKNOWN.

        When INGAME, Lua sends the scenario id (s010_cave, …).
        Otherwise it sends the GameMode id (MAINMENU, or load/cutscene modes).
        """
        t = (token or "").strip()
        if not t:
            return "UNKNOWN"
        if t == "MAINMENU":
            return "MAINMENU"
        if t == "INGAME" or re.match(r"^s\d", t):
            return "INGAME"
        # STARTGAME / loading / cinematic / etc.
        return "TRANSITION"

    def _begin_transition_hold(self, seconds: float = 3.5, *, reason: str = "") -> None:
        """Block item grants briefly while the game settles after a mode/scenario change."""
        until = time.monotonic() + max(0.0, float(seconds))
        self._transition_until = max(self._transition_until, until)
        # Do not set in_cooldown here — that flag is for post-grant ACK waiting.
        # Transition blocking is handled by _in_transition() / _ready_for_item_grants().
        if reason:
            logger.info("Transition hold %.1fs (%s)", seconds, reason)
        else:
            logger.debug("Transition hold %.1fs", seconds)

    def _in_transition(self) -> bool:
        if self._game_mode == "TRANSITION":
            return True
        return time.monotonic() < self._transition_until

    def _ready_for_item_grants(self) -> bool:
        """True only when it is safe to push RL.ReceivePickup."""
        if self.in_cooldown or self._in_transition():
            return False
        if self._game_mode != "INGAME":
            return False
        if self.current_scenario in (None, "MAINMENU"):
            return False
        return True

    async def _wait_for_stable_game_mode(self, timeout: float = 45.0) -> str:
        """
        Poll Game.GetCurrentGameModeID until MAINMENU or INGAME.
        Avoids bootstrapping item sync mid menu↔ingame load.
        """
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline and self._socket:
            try:
                resp = await self.run_lua_code(
                    "local ok, mode = pcall(Game.GetCurrentGameModeID); "
                    "return ok and tostring(mode or '') or ''",
                    wait_response=True,
                    timeout=5.0,
                )
                mode = (resp or b"").decode("ascii", errors="ignore").strip()
                if mode and mode != last:
                    logger.info("Game mode poll: %r", mode)
                    last = mode

                if mode == "MAINMENU":
                    self._game_mode = "MAINMENU"
                    self.current_scenario = "MAINMENU"
                    self.in_cooldown = True
                    return "MAINMENU"
                if mode == "INGAME":
                    self._game_mode = "INGAME"
                    # Let the first in-world frame settle before grants.
                    self._begin_transition_hold(2.5, reason="entered INGAME after connect")
                    return "INGAME"

                # Mid-load / other modes — keep holding.
                self._game_mode = "TRANSITION"
                self._begin_transition_hold(1.5, reason=f"unstable mode {mode!r}")
            except Exception as exc:
                logger.debug("Game mode poll failed: %s", exc)
            await asyncio.sleep(1.0)

        logger.warning(
            "Timed out waiting for MAINMENU/INGAME (last mode=%r); continuing with hold",
            last,
        )
        self._begin_transition_hold(5.0, reason="stable-mode timeout")
        return self._game_mode

    async def connect_to_dread(self):
        async with self._connection_lock:
            if self._socket is not None:
                logger.info("Already connected to Dread — reconnecting to refresh bootstrap")
                await self._disconnect_internal()

            try:
                logger.info("Connecting to Dread at %s:%d", self.dread_ip, DREAD_PORT)
                reader, writer = await asyncio.open_connection(self.dread_ip, DREAD_PORT)
                self._socket = DreadSocketHolder(reader, writer, 1, 4096, 0)

                interests = ClientInterests.LOGGING | ClientInterests.MULTIWORLD
                writer.write(
                    self._build_packet(
                        PacketType.PACKET_HANDSHAKE, interests.to_bytes(1, "little")
                    )
                )
                await asyncio.wait_for(writer.drain(), timeout=30)
                await self._read_response()

                response = await self.run_lua_code(
                    "return string.format('%d,%d,%s,%s,%s', RL.Version, RL.BufferSize,"
                    "tostring(RL.Bootstrap), Init.sLayoutUUID, GameVersion)",
                    wait_response=True,
                )
                if not response:
                    raise DreadLuaException("No API details response")

                api_version, buffer_size, bootstrap, layout_uuid, version = response.decode(
                    "ascii"
                ).split(",")
                self._socket.api_version = int(api_version)
                self._socket.buffer_size = int(buffer_size)
                self.layout_uuid = layout_uuid
                self.version = version
                logger.info(
                    "Dread API %s buffer %s bootstrap=%s uuid=%s version=%s",
                    api_version,
                    buffer_size,
                    bootstrap,
                    layout_uuid,
                    version,
                )

                await self.bootstrap()

                # Drain EXEC reply before starting the background read loop.
                await self.run_lua_code(
                    'Game.AddSF(2.0, "RL.UpdateRDVClient", "")', wait_response=True
                )

                # Don't treat the link as fully live for item sync until the game
                # is on the title screen or fully in-world (not mid-load).
                stable = await self._wait_for_stable_game_mode(timeout=45.0)
                logger.info("Stable game mode for sync: %s", stable)
                if stable not in ("MAINMENU", "INGAME"):
                    # Connecting through TRANSITION/nil while keep-alive runs
                    # floods socket.send() errors and often ends in WinError 10053.
                    raise DreadLuaException(
                        f"Game not ready for sync (mode={stable!r}); "
                        "load a save / reach INGAME, then /connect_dread again"
                    )

                self.game_connected = True
                # Connect/disconnect arm in_cooldown as "not ready"; that is not an
                # in-flight grant. Clear so catch-up can run once ReceivedPickups +
                # collected-indices sync arrive (transition hold still gates grants).
                self.in_cooldown = False
                self._death_poll_generation = 0
                self._death_poll_death_count = 0
                self._deathlink_handled_generation = 0
                self._deathlink_handled_deaths = 0
                self._deathlink_end_episode("connect")
                self.keep_alive_task = asyncio.create_task(self._send_keep_alive())
                self.read_task = asyncio.create_task(self._read_loop())
                self.death_poll_task = asyncio.create_task(self._death_poll_loop())
                self._map_icon_bank_ready = False
                self._map_icon_bank_watch_task = asyncio.create_task(
                    self._map_icon_bank_watch_loop()
                )

                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_PLAYING}])
                logger.info("Successfully connected to Metroid Dread")
                write_dread_session_header(
                    dread_ip=self.dread_ip,
                    game_connected=True,
                    electron_ui=bool(self.electron_ui),
                    dread_version=self.version or "",
                    layout_uuid=self.layout_uuid or "",
                    reason="connected",
                )
                # Inventory / map only when already in-world; wait out settle hold
                # so VisitBoundsSafe / OdrText are not slammed mid-TRANSITION.
                if self._game_mode == "INGAME":
                    self._reachable_areas_sig = None
                    self._map_icon_labels_sig = None
                    self._map_icon_sprites_sig = None
                    self._map_icon_globals_sig = None
                    self.ensure_map_icon_keys(force=True)
                    asyncio.create_task(self._push_map_after_connect_hold())
                self.emit_ui("game_connected", **self.ui_status_payload())
                self.emit_ui_status()

            except Exception as e:
                err = str(e).lower()
                logger.error("Failed to connect to Dread: %s", e)
                write_dread_session_header(
                    dread_ip=self.dread_ip,
                    game_connected=False,
                    electron_ui=bool(self.electron_ui),
                    dread_version=self.version or "",
                    layout_uuid=self.layout_uuid or "",
                    reason="connect_failed",
                )
                if "refused" in err or "10061" in err or "errno 111" in err:
                    logger.error(
                        "Could not connect to %s:%d (connection refused). Common causes:\n"
                        "  • Ryujinx/Dread not running, or mod not enabled\n"
                        "  • Randovania Game Connection already holding :6969 "
                        "(exlaunch accepts only one client — disconnect it first)\n"
                        "  • Export lacked remote Lua: keep Randovania cosmetic "
                        "'Enable automatic item tracker' ON for solo AP seeds, "
                        "re-export so exefs/subsdk9 is installed\n"
                        "  • Game still booting — wait until title screen (RL.Init)\n"
                        "Run: python verify_dread_remote_connection.py",
                        self.dread_ip,
                        DREAD_PORT,
                    )
                await self._cleanup_socket()
                self.game_connected = False
                self.emit_ui("game_error", error=str(e), **self.ui_status_payload())
                self.emit_ui_status()

    async def bootstrap(self):
        """Upload Randovania-compatible sync bootstrap (chunked to buffer size)."""
        assert self._socket is not None
        chunks = bridge.build_bootstrap_chunks(self._socket.buffer_size)
        logger.info("Sending %d bootstrap chunk(s)", len(chunks))
        for i, code in enumerate(chunks):
            await self.run_lua_code(code, wait_response=True)
            logger.debug("Bootstrap chunk %d/%d ok (%d bytes)", i + 1, len(chunks), len(code))
        logger.info("Bootstrap complete")

    async def _send_keep_alive(self):
        while self.game_connected and self._socket:
            try:
                await asyncio.sleep(2)
                if not self._socket:
                    break
                self._socket.writer.write(self._build_packet(PacketType.PACKET_KEEP_ALIVE))
                await asyncio.wait_for(self._socket.writer.drain(), timeout=30)
            except Exception as e:
                logger.warning("Keep-alive failed: %s", e)
                await self.disconnect_dread()
                break

    async def _read_loop(self):
        while self.game_connected and self._socket:
            try:
                if self._socket is None:
                    break
                await self._read_response()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._socket is None or not self.game_connected:
                    break
                logger.error("Read loop error: %s", e)
                await self.disconnect_dread()
                break

    async def _cleanup_socket(self):
        socket = self._socket
        self._socket = None
        if socket is not None:
            try:
                socket.writer.close()
                await socket.writer.wait_closed()
            except Exception:
                pass

    async def _disconnect_internal(self):
        """Tear down socket/tasks without AP status updates (used for reconnect)."""
        self.game_connected = False
        self.in_cooldown = True
        self.received_pickups = None
        self.inventory_index = None
        self._collected_indices_synced = False
        self.game_reported_locations.clear()
        self._game_mode = "UNKNOWN"
        self._transition_until = 0.0
        self.current_scenario = None

        if self.death_poll_task:
            self.death_poll_task.cancel()
            self.death_poll_task = None
        if self._map_icon_bank_watch_task:
            self._map_icon_bank_watch_task.cancel()
            self._map_icon_bank_watch_task = None
        self._map_icon_bank_ready = False
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            self.keep_alive_task = None
        if self.read_task:
            self.read_task.cancel()
            self.read_task = None

        await self._cleanup_socket()

    async def disconnect_dread(self):
        was_connected = self.game_connected
        await self._disconnect_internal()
        if was_connected:
            logger.info("Disconnected from Metroid Dread")
            try:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_CONNECTED}])
            except Exception:
                pass
            self.emit_ui("game_disconnected", **self.ui_status_payload())
            self.emit_ui_status()

    async def disconnect(self, allow_autoreconnect: bool = False):
        await self.disconnect_dread()
        await super().disconnect(allow_autoreconnect)

    # ----- game → AP handlers -----

    async def _handle_inventory(self, json_string: str):
        try:
            data = json.loads(json_string)
            self.inventory_index = data.get("index")
            inv = data.get("inventory")
            if isinstance(inv, list):
                try:
                    new_amounts = [int(x or 0) for x in inv]
                except Exception:
                    new_amounts = []
                if new_amounts != self._game_inventory_amounts:
                    self._game_inventory_amounts = new_amounts
                    # Do not clear cache here: cache key is derived from logic
                    # counts. Debounce UI emit so rapid inventory packets cannot
                    # run sync reachability on the asyncio event loop every tick.
                    self._schedule_tracker_ui_refresh()
            logger.debug(
                "Inventory index=%s amounts=%s",
                self.inventory_index,
                len(self._game_inventory_amounts),
            )
        except Exception as e:
            logger.error("Failed to parse inventory: %s (%r)", e, json_string)

    def _location_display_name(self, location_id: int) -> str:
        try:
            return self.location_names.lookup_in_game(location_id)
        except Exception:
            return f"Location {location_id}"

    async def _handle_collected_locations(self, data: bytes):
        """Parse locations:<bitfield> — bit N = Randovania pickup index N."""
        prefix = b"locations:"
        if not data.startswith(prefix):
            logger.warning("Unknown collected-indices format: %r", data[:32])
            return

        self._collected_indices_synced = True
        pending: List[tuple[int, int]] = []  # (pickup_index, ap_location_id)
        index = 0
        for byte in data[len(prefix) :]:
            for bit in range(8):
                if byte & (1 << bit):
                    location_id = bridge.ap_location_for_pickup_index(index)
                    is_boss = index >= 137  # dread_special_pickups.json (EMMI/boss deaths)
                    if location_id is None:
                        if is_boss:
                            logger.warning(
                                "Boss/EMMI pickup index %s set in-game but unmapped to an AP location",
                                index,
                            )
                        else:
                            logger.debug("Unmapped pickup index %s (game bit set)", index)
                    elif location_id in self.locations_checked:
                        # Re-add on every poll (game_reported_locations is cleared on
                        # each reconnect, but locations_checked persists) so tracker/UI
                        # state relying on game_reported_locations does not lose
                        # already-collected locations after a reconnect.
                        self.game_reported_locations.add(location_id)
                        if is_boss:
                            logger.debug(
                                "Boss/EMMI pickup index %s already checked (id=%s)",
                                index,
                                location_id,
                            )
                    elif location_id not in self.missing_locations:
                        # Server already has this check; keep local state in sync.
                        self.locations_checked.add(location_id)
                        self.game_reported_locations.add(location_id)
                        if is_boss:
                            logger.info(
                                "Boss/EMMI pickup index %s already on server (id=%s, %s) — no LocationCheck resent",
                                index,
                                location_id,
                                self._location_display_name(location_id),
                            )
                        else:
                            logger.debug(
                                "Pickup index %s already checked on server (id=%s)",
                                index,
                                location_id,
                            )
                    else:
                        if is_boss:
                            logger.info(
                                "Boss/EMMI collected in-game: pickup index %s → %s (id=%s) — will send LocationCheck",
                                index,
                                self._location_display_name(location_id),
                                location_id,
                            )
                        pending.append((index, location_id))
                index += 1

        if not pending:
            # May have been waiting on this sync before granting remote / catch-up items.
            await self.send_items_to_game()
            # Still sync collected labels for already-checked bits (reconnect / catch-up).
            # Force: early connect apply often soft-fails before the language bank is ready.
            self._schedule_map_icon_labels_push(force=True)
            return

        to_send = [location_id for _, location_id in pending]
        # Mark reported BEFORE await: LocationChecks yield the event loop and the
        # server often replies with ReceivedItems in the same burst. If we wait to
        # record game_reported_locations until after that await, send_items_to_game
        # can re-grant the local pickup (progressive double-advance) before skip sees it.
        for _, location_id in pending:
            self.game_reported_locations.add(location_id)
        sent = await self.check_locations(to_send)
        for pickup_index, location_id in pending:
            if location_id not in sent:
                if pickup_index >= 137:
                    logger.warning(
                        "Boss/EMMI pickup index %s (%s) was NOT sent as LocationCheck "
                        "(not connected or missing_locations mismatch)",
                        pickup_index,
                        self._location_display_name(location_id),
                    )
                continue
            self.locations_checked.add(location_id)
            name = self._location_display_name(location_id)
            logger.info(
                "Checked location: %s (id=%s, pickup index %s)",
                name,
                location_id,
                pickup_index,
            )

        if sent:
            logger.info(
                "Sent LocationChecks to AP server (%d): %s",
                len(sent),
                ", ".join(self._location_display_name(loc_id) for loc_id in sorted(sent)),
            )
        elif pending:
            logger.warning(
                "Game reported %d new pickup(s) but none were sent to the AP server "
                "(not connected yet or missing_locations mismatch?)",
                len(pending),
            )
        # Fire-and-forget labels; never serialize behind item grants.
        self._schedule_map_icon_labels_push(force=True)
        await self.send_items_to_game()

    async def _handle_received_pickups(self, count_str: str):
        try:
            count = int(count_str)
        except ValueError:
            logger.error("Bad received-pickups payload: %r", count_str)
            return

        self.received_pickups = count
        # Always release grant-ACK cooldown here. Transition / MAINMENU gating is
        # enforced by _ready_for_item_grants(); refusing to clear during settle
        # hold deadlocks offline catch-up when the first sync ACK arrives mid-hold
        # and no further ReceivedPickups packet is sent until the next room load.
        self.in_cooldown = False
        logger.debug("Received pickups from game: %s", count)
        await self.send_items_to_game()

    async def _handle_log_message(self, message: str):
        logger.info("[DREAD] %s", message)
        if message.startswith("AP_CHECK:"):
            # Surfaced from MarkLocationCollected for boss/EMMI (and other) marks.
            logger.info("Location mark from game: %s", message)
        if "AP_DEATH: Player died" in message:
            await self._handle_local_death("log")
            # Lua also schedules ReapplyLastMapIconLabels; Python re-push is a safety net.
            self._schedule_map_icon_labels_push(force=True)
        elif "AP_DEATH: Player respawned" in message:
            self._deathlink_end_episode("log-respawn")
            self._schedule_map_icon_labels_push(force=True)

    async def _handle_game_state(self, state_data: str):
        parts = state_data.split(";")
        scenario = parts[0]
        has_beaten = len(parts) > 1 and parts[1] == "true"
        prev_scenario = self.current_scenario
        prev_mode = self._game_mode
        classified = self._classify_game_state_token(scenario)
        self._game_mode = classified
        self.current_scenario = scenario

        if classified == "MAINMENU":
            self.in_cooldown = True
            self.received_pickups = None
            self.inventory_index = None
            self._collected_indices_synced = False
            self.game_reported_locations.clear()
            logger.debug("Returned to main menu; reset sync state")
        elif classified == "TRANSITION":
            # Between title and in-game (or other non-world modes).
            self._begin_transition_hold(
                4.0, reason=f"game mode {scenario!r} (was {prev_mode})"
            )
            logger.info("Game in transition mode %r — holding item sync", scenario)
        else:
            # INGAME (scenario id like s010_cave)
            logger.debug("Game state: %s", state_data)
            left_menu = prev_mode == "MAINMENU" or prev_scenario == "MAINMENU"
            scenario_changed = bool(prev_scenario) and prev_scenario != scenario
            if left_menu or scenario_changed or prev_mode == "TRANSITION":
                self._begin_transition_hold(
                    3.5,
                    reason=(
                        f"enter/load world {scenario!r} "
                        f"(prev_scenario={prev_scenario!r} prev_mode={prev_mode})"
                    ),
                )
            # RL.UpdateRDVClient / scenario load: re-push reachability so the new
            # area's map paints without waiting for another inventory tick.
            # force=True: MAINMENU→INGAME must paint even if sig matches a prior
            # session, and the scheduler waits out the 3.5s enter-world hold.
            if scenario != prev_scenario and self.reachable_minimap_enabled:
                if left_menu or scenario_changed or prev_mode == "TRANSITION":
                    self._reachable_areas_sig = None
                self._schedule_reachable_map_push(force=True)
            # Mirror reachable reapply for collected map-icon labels.
            if scenario != prev_scenario and self.map_icon_labels_enabled:
                self._schedule_map_icon_labels_push(force=True)

        if has_beaten and not self.finished_game:
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.finished_game = True
            logger.info("Victory detected (game beaten)")

    # ----- AP → game item delivery (RL.ReceivePickup) -----

    async def send_items_to_game(self):
        """
        Grant the next AP item when the game reports it is ready.
        Matches Randovania MercuryConnector.receive_remote_pickups indexing.
        """
        if not self.game_connected or not self._socket:
            return
        if self.received_pickups is None or self.inventory_index is None:
            return
        if not self._collected_indices_synced:
            # Avoid granting before we know which local pickups the save already applied.
            return
        if not self._ready_for_item_grants():
            return
        if self.received_pickups >= len(self.items_received):
            return

        self.in_cooldown = True
        item = self.items_received[self.received_pickups]
        await self._send_item_to_game(item)

    def _refresh_item_id_to_name(self) -> None:
        """Merge local Items.py names with server datapackage (local fills gaps)."""
        names = dict(bridge.ap_item_id_to_name())
        if self.game:
            try:
                for item_id, name in self.item_names[self.game].items():
                    if not name.startswith("Unknown"):
                        names[item_id] = name
            except Exception:
                pass
        self.item_id_to_name = names

    def _resolve_item_name(self, item_id: int) -> str:
        if item_id in self.item_id_to_name:
            return self.item_id_to_name[item_id]
        if self.game:
            try:
                name = self.item_names.lookup_in_game(item_id)
                if not name.startswith("Unknown"):
                    return name
            except Exception:
                pass
        local_name = bridge.ap_item_id_to_name().get(item_id)
        if local_name:
            return local_name
        return f"Item {item_id}"

    def _is_solo_world(self) -> bool:
        """
        True when this room has exactly one real player.

        Counts distinct player slots from slot_info (populated from the
        Connected packet), excluding the always-present slot 0 "Archipelago"
        pseudo-slot and item-link group slots (SlotType.group) — neither is
        an actual second player. Falls back to player_names (also from the
        Connected packet, but team-filtered) if slot_info is unavailable.
        """
        slot_info = getattr(self, "slot_info", None) or {}
        player_slots = {
            slot
            for slot, info in slot_info.items()
            if slot != 0 and getattr(info, "type", SlotType.player) == SlotType.player
        }
        if player_slots:
            return len(player_slots) <= 1
        player_names = getattr(self, "player_names", None) or {}
        fallback_slots = {slot for slot in player_names if slot != 0}
        return len(fallback_slots) <= 1

    def _should_skip_local_inworld_grant(self, item: NetworkItem) -> bool:
        """True when direct-patch already applied this pickup in-game (solo or reported local)."""
        return bridge.should_skip_local_inworld_grant(
            item.player,
            item.location,
            self.slot,
            self._is_solo_world(),
            self.game_reported_locations,
            self.locations_checked,
        )

    def _inventory_already_has_unique_resources(self, resources) -> bool:
        """True when granting these resources would be a Lua no-op (reconnect dedup)."""
        return bridge.inventory_grant_would_be_noop(
            self._game_inventory_amounts,
            resources,
        )

    async def _send_item_to_game(self, item: NetworkItem):
        item_name = self._resolve_item_name(item.item)
        assert self.received_pickups is not None and self.inventory_index is not None

        # Direct patch leaves real resources on local (own) pickups. Collecting
        # already grants in-world; ReceivedItems must not re-apply or progressives
        # advance twice. Still advance ReceivedPickups so reconnect indexing works.
        if self._should_skip_local_inworld_grant(item):
            logger.info(
                "Skipping duplicate local grant for %s "
                "(location=%s already collected in-game; idx=%s)",
                item_name,
                item.location,
                self.received_pickups,
            )
            lua = bridge.format_skip_local_pickup_lua(self.received_pickups)
            try:
                await self.run_lua_code(lua, wait_response=False)
            except Exception as e:
                logger.error("Failed to advance ReceivedPickups after local skip: %s", e)
                self.in_cooldown = False
            return

        player_name = self.player_names.get(item.player, f"Player {item.player}")

        if bridge.is_dna_item(item_name):
            message = f"Received {item_name} from {player_name}."
            lua = bridge.format_dna_receive_lua(
                message,
                self.received_pickups,
                self.inventory_index,
            )
            logger.info(
                "Granting DNA via GrantNextArtifact: %s (idx=%s inv=%s)",
                message,
                self.received_pickups,
                self.inventory_index,
            )
            try:
                await self.run_lua_code(lua, wait_response=False)
            except Exception as e:
                logger.error("Failed to send DNA to game: %s", e)
                self.in_cooldown = False
            return

        resources = bridge.get_item_resources(item_name, item_id=item.item)
        if not resources:
            logger.warning("No Dread mapping for AP item %s (%s); skipping grant", item.item, item_name)
            # Still advance game counter with ITEM_NONE so sync does not stall
            resources = [[{"item_id": "ITEM_NONE", "quantity": 0}]]

        # Reconnect race: ReceivedPickups can lag while unique upgrades are already
        # in the inventory array (seen as Morph Ball RL.ReceivePickup again).
        if self._inventory_already_has_unique_resources(resources):
            logger.info(
                "Skipping duplicate inventory grant for %s "
                "(already owned in-game; idx=%s inv=%s)",
                item_name,
                self.received_pickups,
                self.inventory_index,
            )
            lua = bridge.format_skip_local_pickup_lua(self.received_pickups)
            try:
                await self.run_lua_code(lua, wait_response=False)
            except Exception as e:
                logger.error("Failed to advance ReceivedPickups after owned skip: %s", e)
                self.in_cooldown = False
            return

        parent = bridge.parent_for_resources(resources)
        progression = bridge.resources_to_lua_progression(resources)
        message = f"Received {item_name} from {player_name}."
        lua = bridge.format_receive_pickup_lua(
            message,
            parent,
            progression,
            self.received_pickups,
            self.inventory_index,
        )
        logger.info(
            "Granting via RL.ReceivePickup: %s (idx=%s inv=%s)",
            message,
            self.received_pickups,
            self.inventory_index,
        )
        try:
            # Fire-and-forget: do not await EXEC (death poll / other waiters must
            # not serialize behind grant replies). Read loop consumes the reply.
            await self.run_lua_code(lua, wait_response=False)
        except Exception as e:
            logger.error("Failed to send item to game: %s", e)
            self.in_cooldown = False

    # ----- /give debug command (local-only testing grant) -----

    async def debug_give_item(self, requested_name: str) -> None:
        """
        Grant an item locally for testing, outside of multiworld sync.

        Fuzzy-matches `requested_name` against known AP Dread item names and
        applies the resulting resources through the same OnPickedUp handler
        real pickups use — but it never touches ReceivedPickups/InventoryIndex
        and never sends a LocationCheck. Debug-only; do not call this from
        anywhere in the normal ReceivedItems / send_items_to_game path.
        """
        if not self.game_connected or not self._socket:
            logger.warning("/give: not connected to Metroid Dread")
            return

        resolved_name, suggestions = bridge.resolve_debug_item_name(requested_name)
        if resolved_name is None:
            if suggestions:
                logger.warning(
                    "/give: no item matches '%s'. Did you mean: %s?",
                    requested_name,
                    ", ".join(suggestions),
                )
            else:
                logger.warning("/give: no item matches '%s'", requested_name)
            return

        resources = bridge.get_item_resources(resolved_name)
        has_real_resource = bridge.is_dna_item(resolved_name) or any(
            res.get("item_id") not in (None, "ITEM_NONE", bridge.DNA_DYNAMIC_ITEM_ID)
            and int(res.get("quantity") or 0) > 0
            for stage in (resources or [])
            for res in stage
        )
        if not resources or not has_real_resource:
            logger.warning(
                "/give: '%s' is a known item but has no in-game resource to grant "
                "(e.g. a pure logic/filler item) — nothing was applied",
                resolved_name,
            )
            return

        lua = bridge.format_debug_give_lua(resolved_name, resources)
        logger.info(
            "/give: granting '%s' locally (debug only; no LocationCheck, no ReceivedItems sync)",
            resolved_name,
        )
        try:
            await self.run_lua_code(lua, wait_response=False)
        except Exception as e:
            logger.error("/give: failed to grant '%s': %s", resolved_name, e)

    def run_gui(self):
        from kvui import GameManager

        class MetroidDreadManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago"),
                ("MetroidDread", "Dread"),
            ]
            base_title = "Archipelago Metroid Dread Client"

        self.ui = MetroidDreadManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


async def main(args):
    dread_ip = getattr(args, "dread_ip", None) or "127.0.0.1"
    electron_ui = bool(getattr(args, "electron", False))
    # Default-on diagnostic file for Remote Lua / reachable-map troubleshooting.
    setup_dread_diagnostic_logging(dread_ip=dread_ip, electron_ui=electron_ui)

    ctx = MetroidDreadContext(args.connect, args.password)
    if getattr(args, "name", None):
        ctx.auth = args.name
        ctx.username = args.name
    ctx.electron_ui = electron_ui
    if ctx.electron_ui:
        # Prefer text/CLI path; Electron owns the UI.
        # Don't load RDV logic during startup emit (slow); status loop will compute it.
        ctx.emit_ui(
            "starting",
            ap_connected=False,
            game_connected=False,
            received_items=[],
            checked_location_ids=[],
            in_logic_location_ids=[],
            in_logic_count=0,
        )
        ctx._ui_status_task = asyncio.create_task(ctx._ui_status_loop(), name="UIStatus")

    ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")

    ctx.dread_ip = dread_ip

    auto_dread = bool(getattr(args, "auto_dread", False))
    if ctx.electron_ui and not getattr(args, "no_auto_dread", False):
        auto_dread = True
    if getattr(args, "no_auto_dread", False):
        auto_dread = False
    if auto_dread:
        # Don't block UI/CLI on connect failure — attempt in background after a tick
        asyncio.create_task(ctx.connect_to_dread())

    if gui_enabled and not ctx.electron_ui:
        ctx.run_gui()
    ctx.run_cli()

    while not ctx.exit_event.is_set():
        await asyncio.sleep(1)
        if ctx.game_connected:
            await ctx.send_items_to_game()

    if ctx._ui_status_task:
        ctx._ui_status_task.cancel()
    await ctx.disconnect_dread()
    await ctx.shutdown()


def launch():
    import colorama

    parser = get_base_parser(description="Metroid Dread Client for Archipelago")
    parser.add_argument(
        "--dread-ip",
        default="127.0.0.1",
        help="IP address of Ryujinx running patched Metroid Dread",
    )
    parser.add_argument("--name", default=None, help="Slot name to connect as")
    parser.add_argument(
        "--electron",
        action="store_true",
        help="Emit @@APUI@@ JSON status lines for the Electron client UI",
    )
    parser.add_argument(
        "--auto-dread",
        action="store_true",
        help="Connect to Dread on launch",
    )
    parser.add_argument(
        "--no-auto-dread",
        action="store_true",
        help="Do not auto-connect to Dread (even with --electron)",
    )
    parser.add_argument("url", nargs="?", help="archipelago:// connection url")
    args = parser.parse_args()
    args = handle_url_arg(args, parser=parser)

    colorama.init()
    asyncio.run(main(args))
    colorama.deinit()


if __name__ == "__main__":
    launch()

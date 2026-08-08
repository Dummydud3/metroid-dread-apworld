#!/usr/bin/env python3
"""
Verify that a Ryujinx Dread mod can accept Archipelago / Randovania on TCP 6969.

Checks:
  1. patcher.json enable_remote_lua
  2. exefs/subsdk9 + main.npdm (open-dread-rando-exlaunch)
  3. romfs init.lc present
  4. Whether something is currently listening on 6969
  5. Optional live TCP connect attempt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
from pathlib import Path

DEFAULT_MOD = Path.home() / "AppData/Roaming/Ryujinx/mods/contents/010093801237c000"
PORT = 6969


def check_mod(mod_root: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    patcher = mod_root / "patcher.json"
    if not patcher.is_file():
        results.append(("patcher.json", False, f"missing: {patcher}"))
        return results

    data = json.loads(patcher.read_text(encoding="utf-8"))
    enabled = bool(data.get("enable_remote_lua"))
    results.append(
        (
            "enable_remote_lua",
            enabled,
            "true" if enabled else "FALSE — re-export with auto-tracker ON (or use ap_to_patcher)",
        )
    )
    results.append(
        (
            "mod_category",
            data.get("mod_category") == "romfs",
            f"{data.get('mod_category')!r} (need romfs/exlaunch for subsdk9)",
        )
    )

    # Randovania writes under DreadRandovania/; some tools write flat.
    candidates = [
        mod_root / "DreadRandovania",
        mod_root,
    ]
    exefs = next((c / "exefs" for c in candidates if (c / "exefs").is_dir()), None)
    romfs = next((c / "romfs" for c in candidates if (c / "romfs").is_dir()), None)

    if exefs is None:
        results.append(("exefs/", False, "not found under mod root or DreadRandovania/"))
    else:
        subsdk = exefs / "subsdk9"
        npdm = exefs / "main.npdm"
        results.append(("exefs/subsdk9", subsdk.is_file(), str(subsdk)))
        results.append(("exefs/main.npdm", npdm.is_file(), str(npdm)))

    if romfs is None:
        results.append(("romfs/", False, "not found"))
    else:
        init_lc = romfs / "system" / "scripts" / "init.lc"
        results.append(("romfs/.../init.lc", init_lc.is_file(), str(init_lc)))
        replacements = romfs / "replacements.json"
        results.append(("romfs/replacements.json", replacements.is_file(), str(replacements)))

    return results


def port_listening(host: str = "127.0.0.1", port: int = PORT) -> bool:
    """True if a TCP connect succeeds (game accepts a new client)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def port_bound_locally(port: int = PORT) -> bool:
    """True if any process has the port in LISTEN (Windows netstat)."""
    import subprocess

    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    except Exception:
        return False
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" in line.upper() and needle in line:
            return True
    return False


async def try_handshake(host: str, port: int) -> str:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
    except Exception as e:
        return f"CONNECT FAILED: {e}"

    try:
        # PACKET_HANDSHAKE + MULTIWORLD interest (same as MetroidDreadClient / DreadExecutor)
        writer.write(b"1" + (2).to_bytes(1, "little"))
        await asyncio.wait_for(writer.drain(), timeout=5)
        resp = await asyncio.wait_for(reader.read(1024), timeout=5)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        if resp:
            return f"HANDSHAKE OK ({len(resp)} byte response)"
        return "CONNECTED but empty handshake response"
    except Exception as e:
        return f"CONNECTED but handshake failed: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mod",
        type=Path,
        default=DEFAULT_MOD,
        help=f"Ryujinx mod folder (default: {DEFAULT_MOD})",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-connect", action="store_true", help="Skip live TCP probe")
    args = parser.parse_args()

    print(f"Mod folder: {args.mod}")
    print()

    if not args.mod.is_dir():
        print(f"[FAIL] Mod folder does not exist: {args.mod}")
        return 1

    ok_all = True
    for name, ok, detail in check_mod(args.mod):
        status = "OK  " if ok else "FAIL"
        if not ok:
            ok_all = False
        print(f"  [{status}] {name}: {detail}")

    print()
    bound = port_bound_locally(args.port)
    accepting = port_listening(args.host, args.port)
    print(f"  [{'OK  ' if bound else 'FAIL'}] OS reports LISTEN on :{args.port}: "
          f"{'yes' if bound else 'no'}")
    print(f"  [{'OK  ' if accepting else 'FAIL'}] New TCP connect to {args.host}:{args.port}: "
          f"{'accepted' if accepting else 'refused/failed'}")

    if bound and not accepting:
        print()
        print("  NOTE: Port is bound but new connects fail. open-dread-rando-exlaunch only")
        print("  Accept()s one client at a time. If Randovania Game Connection is attached,")
        print("  Archipelago gets 'connection refused' until you disconnect Randovania.")

    if not args.no_connect and accepting:
        print()
        result = asyncio.run(try_handshake(args.host, args.port))
        print(f"  Live probe: {result}")

    print()
    if not ok_all:
        print("Mod is missing remote-Lua pieces. Re-export from Randovania with:")
        print("  - Cosmetic: Enable automatic item tracker = ON")
        print("  - Output: Ryujinx / romfs (exlaunch)")
        print("Or use dread_patcher_gui / ap_to_patcher (sets enable_remote_lua=true).")
        return 2

    if not bound:
        print("Mod looks good, but nothing is listening.")
        print("  1. Enable the DreadRandovania mod in Ryujinx")
        print("  2. Boot Metroid Dread and wait until title/boot finishes (RL.Init runs in init)")
        return 3

    if bound and not accepting:
        print("Socket is up but busy — disconnect Randovania, then /connect_dread.")
        return 4

    print("Remote connector looks ready for Archipelago (/connect_dread).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

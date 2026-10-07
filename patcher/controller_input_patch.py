"""Extend ODR's HID reader to all eight Pro Controller slots plus handheld.

ODR replaces Game.IsDebugPadButtonPressed with an Npad button-mask reader.
Its stock reader combines FullKey slot 0 and Handheld slot 32; normal Dread
input can use another slot, so pause-map actions must include those slots too.
"""

import struct
from pathlib import Path

# Map build IDs to Lua input helpers and controller readers.
# Include the 256-byte NSO header in IPS32 offsets.
BUILDS = {
    "49161D9CCBC15DF944D0B6278A3C446C006B0BE8":
        (0x10525F0, 0x11F3630, 0x11F3640, 0x1060730),  # Game version 1.0.0.
    "646761F643AFEBB379EDD5E6A5151AF2CEF93DC1":
        (0x10943A0, 0x12393D0, 0x12393E0, 0x10A25F0),  # Game version 2.1.0.
}

# Save registers and read controller IDs 0 through 7.
# Combine their buttons with handheld ID 32 and return the mask to Lua.
# Store controller state on the stack; adjust call addresses below.
_READER = bytes.fromhex(
    "fd7bbaa9fd030091f35301a9f51300f9f30300aa140080d215008052"
    "f52b00b9e0c30091e1a3009106840694e81f40f9940208aab5060011"
    "bf22007103ffff5408048052e82b00b9e0c30091e1a3009100840694"
    "e81f40f9810208aae00313aa3838009420008052f51340f9f35341a9"
    "fd7bc6a8c0035fd6"
)
_STOCK_READERS = {
    "49161D9CCBC15DF944D0B6278A3C446C006B0BE8": bytes.fromhex(
        "fd7bb8a9fd030091f30b00f9f30300aa00048052e1a30091ff2b00b9e02f00b9"
        "e0c3009107840694e1b30091e063019108840694e11f40f9e03340f9210000aa"
        "e00313aa3f380094200080d2f30b40f9fd7bc8a8c0035fd6"
    ),
    "646761F643AFEBB379EDD5E6A5151AF2CEF93DC1": bytes.fromhex(
        "fd7bb8a9fd030091f30b00f9f30300aa00048052e1a30091ff2b00b9e02f00b9"
        "e0c3009103940694e1b30091e063019104940694e11f40f9e03340f9210000aa"
        "e00313aa83380094200080d2f30b40f9fd7bc8a8c0035fd6"
    ),
}


def reader_code(build_id: str) -> bytes:
    base, fullkey, handheld, pushinteger = BUILDS[build_id]
    code = bytearray(_READER)
    for offset, target in ((40, fullkey), (80, handheld), (96, pushinteger)):
        delta = target - (base + offset)
        assert delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27)
        struct.pack_into("<I", code, offset, 0x94000000 | ((delta // 4) & 0x3FFFFFF))
    return bytes(code)


def extend_controller_reader(data: bytes, build_id: str) -> bytes:
    """Replace only the recognized ODR record; preserve all other IPS records."""
    if not data.startswith(b"IPS32"):
        raise ValueError("Expected an ODR IPS32 patch")
    target = BUILDS[build_id][0] + 0x100
    reader = reader_code(build_id)
    out = bytearray(b"IPS32")
    pos = 5
    found = False
    while data[pos:pos + 4] != b"EEOF":
        start = pos
        if pos + 6 > len(data):
            raise ValueError("Truncated IPS32 record")
        offset = int.from_bytes(data[pos:pos + 4], "big")
        size = int.from_bytes(data[pos + 4:pos + 6], "big")
        pos += 6
        if size == 0:
            pos += 3  # Read the repeat count and byte; current ODR records do not use this.
        else:
            pos += size
        if pos > len(data):
            raise ValueError("Truncated IPS32 payload")
        if offset == target:
            payload = data[start + 6:pos]
            if found or payload not in (_STOCK_READERS[build_id], reader):
                raise ValueError("Unrecognized ODR controller reader; refusing to overwrite")
            found = True
            out.extend(offset.to_bytes(4, "big") + len(reader).to_bytes(2, "big") + reader)
        else:
            if offset < target + len(reader) and offset + size > target:
                raise ValueError("Another IPS record overlaps the controller reader")
            out.extend(data[start:pos])
    if not found:
        raise ValueError("ODR controller reader record is missing")
    out.extend(data[pos:])
    return bytes(out)


def install_controller_input_patch(patch_dir: Path) -> int:
    updated = []
    for build_id in BUILDS:
        path = patch_dir / (build_id + ".ips")
        if path.is_file():
            updated.append((path, extend_controller_reader(path.read_bytes(), build_id)))
    if not updated:
        raise ValueError(f"No supported ODR controller IPS patches in {patch_dir}")
    # Check all game versions before writing any files.
    for path, data in updated:
        path.write_bytes(data)
    return len(updated)

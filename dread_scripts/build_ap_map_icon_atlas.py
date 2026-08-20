"""
Paint custom Archipelago cells into unused slots of ODR's minimap icons.bctex.

ODR ships textures/system/minimap/icons/icons.bctex via add_custom_files with
progressive/DNA/unknown cells. We start from that atlas and stamp:

  (row=5, col=10) â€” AP cluster logo (foreign / unknown revealed items)
  (row=5, col=11) â€” green in-logic unknown "?" (reachable uncollected checks)

finalize_mod installs the result over ODR's romfs copy.

Only the target cells' BC3 blocks are rewritten; every other texel keeps the
original ODR compression.

Usage:
  py -3.11 dread_scripts/build_ap_map_icon_atlas.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
import py_tegra_swizzle
import texture2ddecoder
from PIL import Image, ImageDraw
from quicktex import RawTexture
from quicktex.s3tc.bc3 import BC3Encoder

from mercury_engine_data_structures.exporters.raw_texture import RawTexture as MedsRawTexture
from mercury_engine_data_structures.formats.bctex import (
    BCTEX_Dread,
    Bctex,
    BlockType,
    XTX_Tegra_Format,
)
from mercury_engine_data_structures.game_check import Game

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
OUT_BCTEX = ASSETS / "icons.bctex"
OUT_PREVIEW = ASSETS / "ap_logo_cell_preview.png"
OUT_IN_LOGIC_PREVIEW = ASSETS / "ap_in_logic_question_preview.png"

# Atlas cells (row, col) â€” must stay in sync with dread_map_icon_labels.py.
AP_LOGO_CELL: Tuple[int, int] = (5, 10)
IN_LOGIC_UNKNOWN_CELL: Tuple[int, int] = (5, 11)

CELL_SIZE = 128
AP_TEAL = (48, 105, 130, 255)
AP_LIGHT = (120, 200, 220, 255)
BC3_BLOCK = 16  # bytes per 4x4

CellStamp = Tuple[int, int, Image.Image]  # row, col, rgba cell


def _find_odr_icons() -> Path:
    candidates = []
    try:
        from open_dread_rando.files import files_path

        candidates.append(
            Path(
                files_path().joinpath(
                    "romfs", "textures", "system", "minimap", "icons", "icons.bctex"
                )
            )
        )
    except Exception:
        pass
    candidates.append(
        Path.home()
        / "AppData"
        / "Roaming"
        / "Python"
        / "Python310"
        / "site-packages"
        / "open_dread_rando"
        / "files"
        / "romfs"
        / "textures"
        / "system"
        / "minimap"
        / "icons"
        / "icons.bctex"
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Could not locate open_dread_rando files/romfs/.../icons.bctex"
    )


def div_round_up(n: int, d: int) -> int:
    return (n + d - 1) // d


def _crop_ap_cluster(logo: Image.Image) -> Image.Image:
    rgba = logo.convert("RGBA")
    arr = np.array(rgba)
    mask = (arr[:, :, 0] + arr[:, :, 1] + arr[:, :, 2]) > 40
    cols = np.where(mask.any(axis=0))[0]
    rows = np.where(mask.any(axis=1))[0]
    if len(cols) == 0 or len(rows) == 0:
        raise RuntimeError("AP logo appears empty")
    left = int(cols[0])
    top = int(rows[0])
    bottom = int(rows[-1]) + 1
    height = bottom - top
    right = min(left + height, rgba.width)
    return rgba.crop((left, top, right, bottom))


def render_ap_cell(logo_path: Path, size: int = CELL_SIZE) -> Image.Image:
    """Fit the full-color AP cluster logo into one atlas cell (preserve RGBA)."""
    cell = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if logo_path.is_file():
        cluster = _crop_ap_cluster(Image.open(logo_path))
    else:
        # Fallback doodle if the logo file is missing (still multi-color-ish teal).
        cluster = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cluster)
        cx, cy, r = 32, 32, 10
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=AP_TEAL)
        for i in range(6):
            ang = math.radians(60 * i - 90)
            x = cx + int(18 * math.cos(ang))
            y = cy + int(18 * math.sin(ang))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=AP_TEAL)

    arr = np.array(cluster.convert("RGBA"))
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3].astype(np.int16)
    lum = rgb.max(axis=2)
    visible = (alpha > 8) & (lum > 20)
    out = np.zeros_like(arr)
    # Keep source colors (same approach as the green in-logic "?" cell).
    out[visible] = arr[visible]
    out[visible, 3] = 255
    cluster = Image.fromarray(out, "RGBA")
    pad = 18
    fitted = cluster.resize((size - 2 * pad, size - 2 * pad), Image.Resampling.LANCZOS)
    cell.paste(fitted, (pad, pad), fitted)
    return cell


def render_in_logic_question_cell(src_path: Path, size: int = CELL_SIZE) -> Image.Image:
    """Fit the green in-logic '?' PNG into one atlas cell; key out near-black."""
    cell = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if not src_path.is_file():
        raise FileNotFoundError(f"missing in-logic question art: {src_path}")
    rgba = Image.open(src_path).convert("RGBA")
    arr = np.array(rgba)
    # Source ships with a solid black matte outside the circle â€” treat as alpha.
    rgb = arr[:, :, :3].astype(np.int16)
    lum = rgb.max(axis=2)
    alpha = arr[:, :, 3]
    visible = (alpha > 8) & (lum > 18)
    out = np.zeros_like(arr)
    out[visible] = arr[visible]
    out[visible, 3] = 255
    icon = Image.fromarray(out, "RGBA")
    # Crop to opaque content so padding is even.
    ys, xs = np.where(visible)
    if len(xs) == 0 or len(ys) == 0:
        raise RuntimeError("in-logic question art appears empty")
    cropped = icon.crop(
        (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    )
    pad = 10
    fitted = cropped.resize((size - 2 * pad, size - 2 * pad), Image.Resampling.NEAREST)
    cell.paste(fitted, (pad, pad), fitted)
    return cell


def encode_bc3_rgba(img: Image.Image) -> bytes:
    rgba = img.convert("RGBA")
    # BC3 encoder needs multiples of 4.
    w, h = rgba.size
    pad_w = max(4, (w + 3) // 4 * 4)
    pad_h = max(4, (h + 3) // 4 * 4)
    if pad_w != w or pad_h != h:
        padded = Image.new("RGBA", (pad_w, pad_h), (0, 0, 0, 0))
        padded.paste(rgba, (0, 0))
        rgba = padded
    arr = np.ascontiguousarray(np.array(rgba), dtype=np.uint8)
    raw = RawTexture.frombytes(arr.tobytes(), rgba.width, rgba.height)
    return BC3Encoder(8).encode(raw).tobytes()


def deswizzle_surface(data: bytes, width: int, height: int, block_height_mip0: int) -> bytes:
    fmt = XTX_Tegra_Format.BC3_UNORM
    width_blks = div_round_up(width, fmt.block_width)
    height_blks = div_round_up(height, fmt.block_height)
    mip_height_in_blocks = height_blks
    mip_block_height = py_tegra_swizzle.mip_block_height(
        mip_height_in_blocks, block_height_mip0
    )
    height_log2 = math.floor(math.log2(mip_block_height)) if mip_block_height > 0 else 0
    height_mip0 = 1 << max(min(height_log2, 5), 0)
    return py_tegra_swizzle.deswizzle_block_linear(
        width_blks, height_blks, 1, data, height_mip0, fmt.bytes_per_pixel
    )


def swizzle_surface(data: bytes, width: int, height: int, block_height_mip0: int) -> bytes:
    fmt = XTX_Tegra_Format.BC3_UNORM
    width_blks = div_round_up(width, fmt.block_width)
    height_blks = div_round_up(height, fmt.block_height)
    mip_height_in_blocks = height_blks
    mip_block_height = py_tegra_swizzle.mip_block_height(
        mip_height_in_blocks, block_height_mip0
    )
    height_log2 = math.floor(math.log2(mip_block_height)) if mip_block_height > 0 else 0
    height_mip0 = 1 << max(min(height_log2, 5), 0)
    return py_tegra_swizzle.swizzle_block_linear(
        width_blks, height_blks, 1, data, height_mip0, fmt.bytes_per_pixel
    )


def paste_cell_bc3(
    linear: bytearray,
    width: int,
    height: int,
    cell_row: int,
    cell_col: int,
    cell_px: int,
    cell_bc3: bytes,
) -> None:
    """Overwrite one atlas cell in deswizzled BC3 linear storage."""
    bw = div_round_up(width, 4)
    cell_bw = cell_px // 4
    cell_bh = cell_px // 4
    base_bx = cell_col * cell_bw
    base_by = cell_row * cell_bh
    if base_bx + cell_bw > bw or base_by + cell_bh > div_round_up(height, 4):
        return  # cell outside this mip
    expected = cell_bw * cell_bh * BC3_BLOCK
    if len(cell_bc3) < expected:
        raise ValueError(f"cell bc3 too small: {len(cell_bc3)} < {expected}")
    for by in range(cell_bh):
        for bx in range(cell_bw):
            src = (by * cell_bw + bx) * BC3_BLOCK
            dst = ((base_by + by) * bw + (base_bx + bx)) * BC3_BLOCK
            linear[dst : dst + BC3_BLOCK] = cell_bc3[src : src + BC3_BLOCK]


def patch_atlas(src: Path, stamps: Sequence[CellStamp]) -> bytes:
    parsed = Bctex.parse(src.read_bytes(), target_game=Game.DREAD)
    meds = MedsRawTexture(parsed)
    arr = meds.textures[0]
    fmt = XTX_Tegra_Format.BC3_UNORM
    block_height_mip0 = py_tegra_swizzle.block_height_mip0(
        div_round_up(arr.height, fmt.block_height)
    )

    # Original swizzled blob from the DATA block.
    blocks = parsed.raw.data.xtx.blocks
    data_blk = next(blk for blk in blocks if blk.block_type == BlockType.DATA.name)
    swizzled_all = bytearray(data_blk.data)
    tex_info = next(blk for blk in blocks if blk.block_type == BlockType.TEXTURE.name).data
    mip_count = int(tex_info.mip_count)
    slice_size = int(tex_info.slice_size)

    offset = 0
    for level in range(mip_count):
        mip_w = max(1, arr.width >> level)
        mip_h = max(1, arr.height >> level)
        mip_size = py_tegra_swizzle.get_swizzled_surface_size(
            mip_w,
            mip_h,
            1,
            py_tegra_swizzle.PyBlockDim(fmt.block_width, fmt.block_height, fmt.block_depth),
            block_height_mip0,
            fmt.bytes_per_pixel,
        )
        mip_swiz = bytes(swizzled_all[offset : offset + mip_size])
        linear = bytearray(deswizzle_surface(mip_swiz, mip_w, mip_h, block_height_mip0))

        cell_px = CELL_SIZE >> level
        if cell_px >= 4:
            for cell_row, cell_col, cell_img in stamps:
                cell_rgba = cell_img.resize((cell_px, cell_px), Image.Resampling.LANCZOS)
                cell_bc3 = encode_bc3_rgba(cell_rgba)
                paste_cell_bc3(
                    linear, mip_w, mip_h, cell_row, cell_col, cell_px, cell_bc3
                )
            new_swiz = swizzle_surface(bytes(linear), mip_w, mip_h, block_height_mip0)
            if len(new_swiz) != mip_size:
                raise RuntimeError(
                    f"mip{level} swizzle size mismatch {len(new_swiz)} != {mip_size}"
                )
            swizzled_all[offset : offset + mip_size] = new_swiz
        offset += mip_size

    if offset > slice_size:
        raise RuntimeError(f"wrote past slice_size: {offset} > {slice_size}")

    data_blk.data = bytes(swizzled_all)
    return BCTEX_Dread.build(parsed.raw)


def _cell_opaque_count(atlas: Image.Image, row: int, col: int) -> int:
    x0, y0 = col * CELL_SIZE, row * CELL_SIZE
    preview = atlas.crop((x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE))
    arr = np.array(preview)
    return int((arr[:, :, 3] > 10).sum())


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    src = _find_odr_icons()
    print(f"[INFO] source atlas: {src}")
    # Prefer the vendored full-color cluster logo in assets/; fall back to AP data/icon.png.
    logo_path = ASSETS / "ap_logo_fullcolor.png"
    if not logo_path.is_file():
        logo_path = ROOT.parent.parent / "data" / "icon.png"
    if not logo_path.is_file():
        logo_path = (
            ROOT.parent.parent
            / "WebHostLib"
            / "static"
            / "static"
            / "branding"
            / "header-logo.png"
        )
    in_logic_path = ASSETS / "ap_in_logic_question.png"
    print(f"[INFO] logo: {logo_path} exists={logo_path.is_file()}")
    print(f"[INFO] in-logic ?: {in_logic_path} exists={in_logic_path.is_file()}")

    ap_cell = render_ap_cell(logo_path)
    ap_cell.save(OUT_PREVIEW)
    il_cell = render_in_logic_question_cell(in_logic_path)
    il_cell.save(OUT_IN_LOGIC_PREVIEW)

    stamps: List[CellStamp] = [
        (AP_LOGO_CELL[0], AP_LOGO_CELL[1], ap_cell),
        (IN_LOGIC_UNKNOWN_CELL[0], IN_LOGIC_UNKNOWN_CELL[1], il_cell),
    ]
    out_bytes = patch_atlas(src, stamps)
    OUT_BCTEX.write_bytes(out_bytes)

    # Verify stamped cells decode with content; a free neighbor stays empty.
    parsed = Bctex.parse(out_bytes, target_game=Game.DREAD)
    mip = MedsRawTexture(parsed).textures[0].members[0].mip0()
    bgra = texture2ddecoder.decode_bc3(mip.data, mip.width, mip.height)
    atlas = Image.frombytes("RGBA", (mip.width, mip.height), bgra, "raw", "BGRA")

    ap_r, ap_c = AP_LOGO_CELL
    il_r, il_c = IN_LOGIC_UNKNOWN_CELL
    ap_preview = atlas.crop(
        (ap_c * CELL_SIZE, ap_r * CELL_SIZE, (ap_c + 1) * CELL_SIZE, (ap_r + 1) * CELL_SIZE)
    )
    ap_preview.save(ASSETS / "ap_logo_cell_roundtrip.png")
    il_preview = atlas.crop(
        (il_c * CELL_SIZE, il_r * CELL_SIZE, (il_c + 1) * CELL_SIZE, (il_r + 1) * CELL_SIZE)
    )
    il_preview.save(ASSETS / "ap_in_logic_question_roundtrip.png")

    neighbor_opaque = _cell_opaque_count(atlas, 5, 12)
    print(
        f"[OK] wrote {OUT_BCTEX} ({len(out_bytes)} bytes); "
        f"AP(5,10) opaque={_cell_opaque_count(atlas, ap_r, ap_c)} "
        f"IL?(5,11) opaque={_cell_opaque_count(atlas, il_r, il_c)} "
        f"neighbor(5,12) opaque={neighbor_opaque}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

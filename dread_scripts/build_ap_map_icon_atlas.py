"""
Paint the Archipelago logo into an unused cell of ODR's minimap icons.bctex.

ODR ships textures/system/minimap/icons/icons.bctex via add_custom_files with
progressive/DNA/unknown cells. We start from that atlas, stamp the AP cluster
logo into empty cell (row=5, col=10), and write a drop-in replacement that
finalize_mod installs over ODR's romfs copy.

Only the target cell's BC3 blocks are rewritten; every other texel keeps the
original ODR compression.

Usage:
  py -3.11 dread_scripts/build_ap_map_icon_atlas.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

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
CELL_ROW = 5
CELL_COL = 10
CELL_SIZE = 128
AP_TEAL = (48, 105, 130, 255)
AP_LIGHT = (120, 200, 220, 255)
BC3_BLOCK = 16  # bytes per 4x4


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
    cell = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if logo_path.is_file():
        cluster = _crop_ap_cluster(Image.open(logo_path))
    else:
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
    out[visible, 0] = AP_TEAL[0]
    out[visible, 1] = AP_TEAL[1]
    out[visible, 2] = AP_TEAL[2]
    out[visible, 3] = 255
    if visible.any():
        bright = visible & (lum > int(lum[visible].mean()))
        out[bright, 0] = AP_LIGHT[0]
        out[bright, 1] = AP_LIGHT[1]
        out[bright, 2] = AP_LIGHT[2]
    cluster = Image.fromarray(out, "RGBA")
    pad = 18
    fitted = cluster.resize((size - 2 * pad, size - 2 * pad), Image.Resampling.LANCZOS)
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


def patch_atlas(src: Path, cell_img: Image.Image) -> bytes:
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
            cell_rgba = cell_img.resize((cell_px, cell_px), Image.Resampling.LANCZOS)
            cell_bc3 = encode_bc3_rgba(cell_rgba)
            paste_cell_bc3(
                linear, mip_w, mip_h, CELL_ROW, CELL_COL, cell_px, cell_bc3
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


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    src = _find_odr_icons()
    print(f"[INFO] source atlas: {src}")
    logo_path = (
        ROOT.parent.parent
        / "WebHostLib"
        / "static"
        / "static"
        / "branding"
        / "header-logo.png"
    )
    print(f"[INFO] logo: {logo_path} exists={logo_path.is_file()}")
    cell = render_ap_cell(logo_path)
    cell.save(OUT_PREVIEW)

    out_bytes = patch_atlas(src, cell)
    OUT_BCTEX.write_bytes(out_bytes)

    # Verify the stamped cell decodes with content; neighbors stay intact.
    parsed = Bctex.parse(out_bytes, target_game=Game.DREAD)
    mip = MedsRawTexture(parsed).textures[0].members[0].mip0()
    bgra = texture2ddecoder.decode_bc3(mip.data, mip.width, mip.height)
    atlas = Image.frombytes("RGBA", (mip.width, mip.height), bgra, "raw", "BGRA")
    x0, y0 = CELL_COL * CELL_SIZE, CELL_ROW * CELL_SIZE
    preview = atlas.crop((x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE))
    preview.save(ASSETS / "ap_logo_cell_roundtrip.png")
    neighbor = atlas.crop((x0 + CELL_SIZE, y0, x0 + 2 * CELL_SIZE, y0 + CELL_SIZE))
    arr = np.array(preview)
    narr = np.array(neighbor)
    print(
        f"[OK] wrote {OUT_BCTEX} ({len(out_bytes)} bytes); "
        f"cell opaque={(arr[:, :, 3] > 10).sum()} "
        f"neighbor(5,11) opaque={(narr[:, :, 3] > 10).sum()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

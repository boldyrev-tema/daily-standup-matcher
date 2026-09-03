"""Generates AppIcon.icns for the unified app from the project's own design
tokens (second_screen.html/etc: --page-bg rgba(19,18,23,.86), --accent-text
#D6C8FF, --live #54C77A) instead of py2app's default placeholder icon.

Draws one 1024x1024 master (supersampled 4x for antialiasing, same
reasoning as menubar.py's tray icon — PIL's drawing primitives don't
antialias on their own), exports the standard macOS .iconset sizes, and
shells out to `iconutil` (bundled with macOS) to build the .icns.

Run: venv/bin/python3 make_app_icon.py
"""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from menubar import draw_waveform

MASTER = 1024
SUPERSAMPLE = 2  # 2048px working canvas — plenty for a crisp 1024 result
BIG = MASTER * SUPERSAMPLE

# Exact hex values from second_screen.html/column.html/polosa.html's own
# :root tokens — not reinvented.
BG_TOP = (30, 28, 36)       # a touch lighter than --page-bg for gradient depth
BG_BOTTOM = (16, 15, 20)    # close to rgba(19,18,23)
ACCENT = (214, 200, 255)    # --accent-text: #D6C8FF
LIVE_DOT = (84, 199, 122)   # --live: #54C77A

ICONSET_SIZES = [16, 32, 128, 256, 512]


def _squircle_mask(size: int, radius: float) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def build_master() -> Image.Image:
    img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Vertical gradient background, same dark-glass family as the in-app tokens.
    for y in range(BIG):
        t = y / BIG
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (BIG, y)], fill=(r, g, b, 255))

    # macOS "squircle" convention: roughly 22-23% corner radius at full bleed.
    radius = int(BIG * 0.225)
    mask = _squircle_mask(BIG, radius)
    bg = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    bg.paste(img, (0, 0), mask)
    img = bg
    draw = ImageDraw.Draw(img)

    # Same waveform glyph as the tray icon (menubar.draw_waveform) — one
    # abstract, language-independent mark instead of a Cyrillic letter (per
    # the user's own note), shared so the Dock icon and the menu-bar icon
    # read as the same product.
    draw_waveform(draw, BIG / 2, BIG / 2, BIG * 0.85, ACCENT)

    # Live-dot accent, bottom-right — the same green the product itself uses
    # for "currently listening", a real signature of this app, not a
    # generic decoration.
    dot_r = BIG * 0.075
    cx, cy = BIG * 0.78, BIG * 0.78
    draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=LIVE_DOT + (255,))

    return img.resize((MASTER, MASTER), Image.LANCZOS)


def main():
    master = build_master()

    iconset_dir = Path("AppIcon.iconset")
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir()

    for size in ICONSET_SIZES:
        master.resize((size, size), Image.LANCZOS).save(iconset_dir / f"icon_{size}x{size}.png")
        master.resize((size * 2, size * 2), Image.LANCZOS).save(iconset_dir / f"icon_{size}x{size}@2x.png")

    subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", "AppIcon.icns"], check=True)
    shutil.rmtree(iconset_dir)
    print("Wrote AppIcon.icns")


if __name__ == "__main__":
    main()

"""Image -> braille studio renderer.

Renders a PIL.Image into braille-character art. Supports three methods:
  - "tonal":   Floyd-Steinberg dither of grayscale (dark pixel -> raised dot).
  - "contour": edge map only (Sobel/Canny) -> dots only on contours.
  - "hybrid":  union of tonal + contour dots.

If the image is RGBA (a subject cutout), bg_blank forces transparent pixels
to stay blank so the portrait has no background.

Core dot bitmap + aspect logic adapted from /tmp/aa.py.
"""

from PIL import Image, ImageOps, ImageEnhance
import numpy as np

try:
    import cv2
    _HAVE_CV2 = True
except Exception:  # pragma: no cover - cv2 expected present, but stay safe
    _HAVE_CV2 = False

# 2-wide x 4-tall dot cell. Each entry: (dx, dy, bit) -> Unicode braille bit.
BR_DOTS = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (0, 3, 0x40),
           (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80)]


def _dot_grid_size(w, h, width):
    """Return (px, py) dot-grid dimensions for `width` braille cells.

    px = width*2 dots wide; py keeps the image aspect (py = round(px*h/w)),
    snapped down to a multiple of 4 so it fills whole cells.
    """
    px = width * 2
    py = max(4, int(round(px * h / w)))
    py -= py % 4
    return px, py


def _alpha_mask(img, px, py):
    """Boolean mask at dot-grid resolution: True where pixel is foreground.

    Returns None if the image has no usable alpha channel.
    """
    if img.mode not in ("RGBA", "LA") and "A" not in img.getbands():
        return None
    a = img.convert("RGBA").split()[-1]
    a = a.resize((px, py), Image.LANCZOS)
    arr = np.asarray(a, dtype=np.uint8)
    # alpha < 16 -> background
    return arr >= 16


def _to_gray_array(img, px, py, contrast, brightness, invert, autoc):
    """Adjusted grayscale as uint8 ndarray at dot-grid resolution."""
    im = img.convert("RGB")
    if autoc:
        im = ImageOps.autocontrast(im, cutoff=1)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    if brightness != 1.0:
        im = ImageEnhance.Brightness(im).enhance(brightness)
    if invert:
        im = ImageOps.invert(im)
    g = im.convert("L").resize((px, py), Image.LANCZOS)
    return np.asarray(g, dtype=np.uint8)


def _tonal_dots(img, px, py, contrast, brightness, invert):
    """Floyd-Steinberg dithered bitmap. True = raised dot (was dark pixel)."""
    im = img.convert("RGB")
    im = ImageOps.autocontrast(im, cutoff=1)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    if brightness != 1.0:
        im = ImageEnhance.Brightness(im).enhance(brightness)
    if invert:
        im = ImageOps.invert(im)
    g = im.convert("L").resize((px, py), Image.LANCZOS).convert("1")  # FS dither
    arr = np.asarray(g, dtype=np.uint8)  # 0 = black, 255 = white
    return arr == 0  # black -> raised dot


def _edge_dots(img, px, py, contrast, brightness, invert, edge):
    """Edge map. True = dot on a contour. `edge` in 0..1 controls strength."""
    gray = _to_gray_array(img, px, py, contrast, brightness, invert, autoc=True)
    e = max(0.0, min(1.0, edge))
    if _HAVE_CV2:
        # Higher edge -> lower thresholds -> more edges detected.
        lo = int(120 - 100 * e)   # e=0 -> 120, e=1 -> 20
        hi = int(220 - 140 * e)   # e=0 -> 220, e=1 -> 80
        lo = max(1, lo)
        hi = max(lo + 1, hi)
        edges = cv2.Canny(gray, lo, hi)
        return edges > 0
    # numpy Sobel fallback
    gx = np.zeros_like(gray, dtype=np.float32)
    gy = np.zeros_like(gray, dtype=np.float32)
    f = gray.astype(np.float32)
    gx[:, 1:-1] = f[:, 2:] - f[:, :-2]
    gy[1:-1, :] = f[2:, :] - f[:-2, :]
    mag = np.sqrt(gx * gx + gy * gy)
    if mag.max() > 0:
        mag = mag / mag.max() * 255.0
    thresh = 120 - 110 * e  # e=0 -> 120, e=1 -> 10
    return mag >= thresh


_BLANK = chr(0x2800)  # empty braille cell


def trim_blank_margins(art):
    """Crop fully-blank rows/columns from the edges of a braille string.

    Lossless: only uniform `U+2800` margins are removed, so the portrait keeps
    its resolution and content but sits flush to its bounding box (faster to
    render, no empty framing). Returns "" if the art is entirely blank.
    """
    rows = [r for r in art.split("\n")]
    w = max((len(r) for r in rows), default=0)
    rows = [r.ljust(w, _BLANK) for r in rows]
    blank_row = [all(c == _BLANK for c in r) for r in rows]
    top, bot = 0, len(rows)
    while top < bot and blank_row[top]:
        top += 1
    while bot > top and blank_row[bot - 1]:
        bot -= 1
    rows = rows[top:bot]
    if not rows:
        return ""
    left, right = 0, w
    while left < right and all(r[left] == _BLANK for r in rows):
        left += 1
    while right > left and all(r[right - 1] == _BLANK for r in rows):
        right -= 1
    return "\n".join(r[left:right] for r in rows)


def to_braille(img, width=56, method="tonal", contrast=1.0, brightness=1.0,
               edge=0.0, invert=False, bg_blank=True):
    """Render a PIL.Image to a braille-character string.

    Args:
        img: PIL.Image. RGBA = subject cutout (transparent bg).
        width: number of braille cells per line (each cell = 2 dots wide).
        method: "tonal" | "contour" | "hybrid".
        contrast, brightness: PIL ImageEnhance factors (1.0 = unchanged).
        edge: 0..1, contour/hybrid edge strength (higher = more edges).
        invert: invert tones (ImageOps.invert).
        bg_blank: if RGBA, keep transparent (alpha<16) pixels blank.

    Returns:
        Multi-line string of braille characters (U+2800..U+28FF).
    """
    if img is None:
        return ""
    w, h = img.size
    if w == 0 or h == 0:
        return ""
    width = max(1, int(width))
    px, py = _dot_grid_size(w, h, width)

    method = (method or "tonal").lower()
    if method == "tonal":
        dots = _tonal_dots(img, px, py, contrast, brightness, invert)
    elif method == "contour":
        dots = _edge_dots(img, px, py, contrast, brightness, invert, edge)
    elif method == "hybrid":
        tonal = _tonal_dots(img, px, py, contrast, brightness, invert)
        edges = _edge_dots(img, px, py, contrast, brightness, invert, edge)
        dots = tonal | edges
    else:
        raise ValueError("method must be tonal|contour|hybrid, got %r" % method)

    if bg_blank:
        mask = _alpha_mask(img, px, py)
        if mask is not None:
            dots = dots & mask  # blank out background

    rows = py // 4
    out = []
    for cy in range(rows):
        line = []
        base_y = cy * 4
        for cx in range(width):
            base_x = cx * 2
            v = 0
            for dx, dy, bit in BR_DOTS:
                if dots[base_y + dy, base_x + dx]:
                    v |= bit
            line.append(chr(0x2800 + v))
        out.append("".join(line))
    return trim_blank_margins("\n".join(out))

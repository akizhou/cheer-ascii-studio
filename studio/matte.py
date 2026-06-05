"""Background matting / cutout for the image -> braille studio.

cutout(img, engine="rembg") -> RGBA with background made transparent.
compose(rgba, bg="none")    -> keep alpha ("none") or flatten onto white/black.

The "rembg" engine uses the u2net model; on ANY failure it falls back to a
GrabCut-based cutout so the studio still produces a usable matte offline.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

# Lazily-initialised, cached rembg session (created on first successful use).
_REMBG_SESSION = None


def _get_session():
    """Return a cached rembg session, creating it lazily. May raise."""
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session
        _REMBG_SESSION = new_session("u2net")
    return _REMBG_SESSION


def _to_rgba(img) -> Image.Image:
    """Coerce a PIL image (any mode) to RGBA."""
    if img.mode != "RGBA":
        return img.convert("RGBA")
    return img


def grabcut_cutout(img) -> Image.Image:
    """Background removal via cv2.grabCut seeded with a centred foreground rect.

    Returns an RGBA PIL image with the background made transparent. This is the
    offline fallback for the rembg engine and is also useful on its own.
    """
    import cv2

    rgb = img.convert("RGB")
    arr = np.array(rgb)  # H x W x 3, RGB
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]

    # Seed rect: centred box covering the bulk of the frame, leaving a margin
    # that grabCut treats as definite background.
    mx = max(1, int(round(w * 0.08)))
    my = max(1, int(round(h * 0.08)))
    rect = (mx, my, max(1, w - 2 * mx), max(1, h - 2 * my))

    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(bgr, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    except Exception:
        # If grabCut itself fails, fall back to "everything inside rect is fg".
        mask[:] = cv2.GC_BGD
        mask[my:h - my, mx:w - mx] = cv2.GC_FGD

    # Foreground = probable or definite foreground.
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

    # Guard against a degenerate (all-background) result: keep the seed rect.
    if fg.max() == 0:
        fg[my:h - my, mx:w - mx] = 255

    rgba = np.dstack([arr, fg])  # arr is RGB; alpha appended
    return Image.fromarray(rgba, mode="RGBA")


def cutout(img, engine: str = "rembg") -> Image.Image:
    """Return an RGBA image with the background made transparent.

    engine="rembg" uses the u2net model; on ANY failure it transparently falls
    back to grabcut_cutout. Any other engine value goes straight to grabcut.
    """
    if engine == "rembg":
        try:
            from rembg import remove
            session = _get_session()
            out = remove(img, session=session)
            return _to_rgba(out)
        except Exception:
            # Any failure (missing model, import error, runtime error) -> fallback.
            return grabcut_cutout(img)
    return grabcut_cutout(img)


def compose(rgba, bg: str = "none") -> Image.Image:
    """Compose an RGBA cutout against a background.

    bg="none"  -> return the RGBA image unchanged (alpha preserved).
    bg="white" -> flatten onto white, returning RGB.
    bg="black" -> flatten onto black, returning RGB.
    """
    rgba = _to_rgba(rgba)
    if bg == "none":
        return rgba
    if bg == "white":
        color = (255, 255, 255)
    elif bg == "black":
        color = (0, 0, 0)
    else:
        raise ValueError(f"unknown bg {bg!r}; expected one of none/white/black")
    background = Image.new("RGB", rgba.size, color)
    background.paste(rgba, mask=rgba.split()[3])
    return background

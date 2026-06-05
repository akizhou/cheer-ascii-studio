"""Concurrent image downloader for the braille studio.

Ported from /tmp/dl.py: download a list of URLs concurrently, validate each as a
real image with PIL (verify + minimum dimension + acceptable mode), keep the
valid ones on disk and return their local paths. Invalid/too-small/broken
downloads are deleted.

Side-effect free at import time: no network or filesystem access happens until
``fetch`` is called.
"""

from __future__ import annotations

import os
import hashlib
import urllib.request
import concurrent.futures as cf

from PIL import Image

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

_MIN_BYTES = 3000
_OK_MODES = ("RGB", "RGBA", "L", "P")


def _fetch_one(index, url, out_dir, min_dim):
    """Download a single URL, validate it, return local path or None.

    Filename is a hash of the URL (not a positional index) so repeated harvests
    accumulate distinct images instead of overwriting 0.img/1.img each time, and
    a URL already on disk is skipped (idempotent re-harvest)."""
    name = hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ".img"
    path = os.path.join(out_dir, name)
    if os.path.exists(path):
        return path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < _MIN_BYTES:
            return None
        with open(path, "wb") as f:
            f.write(data)
        # verify() must run on a fresh handle, then reopen to read size/mode.
        Image.open(path).verify()
        with Image.open(path) as im:
            w, h = im.size
            mode = im.mode
        if min(w, h) >= min_dim and mode in _OK_MODES:
            return path
        os.remove(path)
        return None
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def fetch(urls, out_dir, max_workers=12, min_dim=400):
    """Download ``urls`` concurrently into ``out_dir`` and return valid paths.

    Each URL is downloaded with a browser User-Agent and a 20s timeout.
    Downloads under 3000 bytes are skipped. A download is kept only if PIL can
    verify it as an image, its smaller side is >= ``min_dim``, and its mode is
    one of RGB/RGBA/L/P. Invalid files are removed. ``out_dir`` is created if
    missing. Returned paths preserve input order.
    """
    urls = [u for u in urls if u]
    os.makedirs(out_dir, exist_ok=True)
    if not urls:
        return []

    results = [None] * len(urls)
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_fetch_one, i, u, out_dir, min_dim): i
            for i, u in enumerate(urls)
        }
        for fut in cf.as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()

    return [p for p in results if p]

"""Cheer ASCII Studio -- local FastAPI backend + static JS frontend.

Run:  ./run.sh   (= uvicorn server:app)   then open http://localhost:8000
Wraps the studio/* modules; the responsive UI lives in static/index.html.
"""
import io
import os
import glob
import json
import base64
import hashlib
import shutil
import pathlib

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

from studio import download, matte, braille

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
LIVE = pathlib.Path.home() / ".claude" / "cheer-gallery"

app = FastAPI()
# local tool + browser-extension importer: allow any origin (localhost only anyway)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------- path / state helpers -------------------------
def sdir(subject: str) -> pathlib.Path:
    if not subject or "/" in subject or ".." in subject:
        raise HTTPException(400, "bad subject")
    d = DATA / subject
    for sub in ("candidates", "crops", "gallery"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def discover_subjects() -> list[str]:
    if not DATA.exists():
        return []
    return sorted(p.name for p in DATA.iterdir() if p.is_dir() and not p.name.startswith("."))


def safe_path(subject: str, kind: str, name: str) -> pathlib.Path:
    if kind not in ("candidates", "crops", "gallery") or "/" in name or ".." in name:
        raise HTTPException(400, "bad path")
    return sdir(subject) / kind / name


def load_state(subject: str) -> dict:
    p = sdir(subject) / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def save_state(subject: str, st: dict):
    (sdir(subject) / "state.json").write_text(json.dumps(st, indent=2))


def candidates(subject: str):
    d = sdir(subject) / "candidates"
    fs = []
    for ext in ("*.img", "*.png", "*.jpg", "*.jpeg", "*.webp"):
        fs += glob.glob(str(d / ext))
    return sorted(os.path.basename(f) for f in fs)


def _crop_img(path: str, crop):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    l, t, r, b = crop
    box = (max(0, int(l * w)), max(0, int(t * h)), min(w, int(r * w)), min(h, int(b * h)))
    if box[2] <= box[0] or box[3] <= box[1]:
        box = (0, 0, w, h)
    return im.crop(box)


# rembg cutout is the slow step; cache the RGBA matte on (path, crop).
_CUT = {}


def cutout_cached(path: str, crop):
    key = (path, tuple(round(x, 4) for x in crop))
    if key not in _CUT:
        if len(_CUT) > 48:
            _CUT.pop(next(iter(_CUT)))
        _CUT[key] = matte.cutout(_crop_img(path, crop))
    return _CUT[key]


def png_data_url(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ------------------------------ models ------------------------------
class Urls(BaseModel):
    subject: str; urls: list[str]

class Convert(BaseModel):
    subject: str; name: str
    crop: list[float] = [0.0, 0.0, 1.0, 1.0]  # l,t,r,b fractions of the original image
    method: str = "hybrid"; width: int = 72
    contrast: float = 1.25; brightness: float = 1.0; edge: float = 0.5
    bg: str = "none"; invert: bool = False; remove_bg: bool = True

class Keep(BaseModel):
    subject: str; name: str; braille: str

class NameReq(BaseModel):
    subject: str; name: str

class SubjectReq(BaseModel):
    subject: str

class ImportImg(BaseModel):
    subject: str; data_url: str = ""; url: str = ""


# ------------------------------ routes ------------------------------
@app.get("/api/subjects")
def subjects():
    return {"subjects": discover_subjects()}


@app.get("/api/state")
def state(subject: str):
    return {"state": load_state(subject), "candidates": candidates(subject)}


@app.get("/thumb")
def thumb(subject: str, kind: str, name: str, w: int = 320):
    p = safe_path(subject, kind, name)
    if not p.exists():
        raise HTTPException(404, "not found")
    im = Image.open(p).convert("RGB")
    im.thumbnail((w, w * 2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.post("/api/import_urls")
def import_urls(u: Urls):
    got = download.fetch(u.urls, str(sdir(u.subject) / "candidates"))
    return {"added": len(got), "candidates": candidates(u.subject)}


@app.post("/api/upload")
async def upload(subject: str = Form(...), files: list[UploadFile] = File(...)):
    cd = sdir(subject) / "candidates"
    n = 0
    for f in files:
        try:
            (cd / f"manual_{os.path.basename(f.filename)}").write_bytes(await f.read())
            n += 1
        except Exception:
            pass
    return {"added": n, "candidates": candidates(subject)}


@app.post("/api/convert")
def convert(c: Convert):
    p = str(safe_path(c.subject, "candidates", c.name))
    crop = c.crop if (c.crop and len(c.crop) == 4) else [0.0, 0.0, 1.0, 1.0]
    if c.remove_bg:
        base = matte.compose(cutout_cached(p, crop), bg=c.bg)
        bg_blank = (c.bg == "none")
    else:
        base = _crop_img(p, crop)  # keep the background
        bg_blank = False
    art = braille.to_braille(base, width=c.width, method=c.method, contrast=c.contrast,
                             brightness=c.brightness, edge=c.edge, invert=c.invert,
                             bg_blank=bg_blank)
    return {"braille": art, "img": png_data_url(base.convert("RGBA"))}


@app.post("/api/keep")
def keep(k: Keep):
    stem = pathlib.Path(k.name).stem
    (sdir(k.subject) / "gallery" / f"{stem}.txt").write_text(k.braille + "\n")
    st = load_state(k.subject)
    st.setdefault("decisions", {})[k.name] = "kept"
    save_state(k.subject, st)
    return {"ok": True}


@app.post("/api/discard")
def discard(r: NameReq):
    stem = pathlib.Path(r.name).stem
    g = sdir(r.subject) / "gallery" / f"{stem}.txt"
    if g.exists():
        g.unlink()
    st = load_state(r.subject)
    st.setdefault("decisions", {})[r.name] = "discarded"
    save_state(r.subject, st)
    return {"ok": True}


@app.get("/api/gallery")
def gallery(subject: str):
    items = []
    for g in sorted(glob.glob(str(sdir(subject) / "gallery" / "*.txt"))):
        items.append({"name": os.path.basename(g), "braille": pathlib.Path(g).read_text()})
    return {"items": items}


@app.post("/api/remove")
def remove(r: NameReq):
    if "/" in r.name or ".." in r.name:
        raise HTTPException(400, "bad name")
    g = sdir(r.subject) / "gallery" / r.name
    if g.exists():
        g.unlink()
    return {"ok": True}


@app.post("/api/export")
def export(r: SubjectReq):
    src = sorted(glob.glob(str(sdir(r.subject) / "gallery" / "*.txt")))
    dst = LIVE / r.subject
    dst.mkdir(parents=True, exist_ok=True)
    for old in glob.glob(str(dst / "*.txt")):
        os.remove(old)
    for g in src:
        shutil.copy(g, dst / os.path.basename(g))
    return {"copied": len(src), "dest": str(dst)}


@app.get("/api/ping")
def ping():
    return {"ok": True}


@app.post("/api/import_image")
def import_image(r: ImportImg):
    """Receive an image from the browser extension (base64 data_url preferred, or a
    url for server-side download) and save it as a candidate for the subject."""
    cd = sdir(r.subject) / "candidates"
    raw = None
    if r.data_url and "," in r.data_url:
        try:
            raw = base64.b64decode(r.data_url.split(",", 1)[1])
        except Exception:
            raw = None
    if raw is None:
        if r.url:
            got = download.fetch([r.url], str(cd), min_dim=200)
            return {"ok": bool(got), "count": len(candidates(r.subject))}
        raise HTTPException(400, "no image data")
    try:
        Image.open(io.BytesIO(raw)).verify()
        w, h = Image.open(io.BytesIO(raw)).size
    except Exception:
        raise HTTPException(400, "not an image")
    if min(w, h) < 200:
        return {"ok": False, "reason": "too small (%dx%d)" % (w, h),
                "count": len(candidates(r.subject))}
    name = "ext_" + hashlib.md5(raw).hexdigest()[:16] + ".img"
    (cd / name).write_bytes(raw)
    return {"ok": True, "name": name, "count": len(candidates(r.subject))}


# static frontend (mounted last so /api/* and /thumb win)
@app.get("/")
def index():
    return FileResponse(str(ROOT / "static" / "index.html"))


app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
